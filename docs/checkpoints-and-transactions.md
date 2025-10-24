# Checkpoints and Approval Sessions

AgentSmithy automatically saves snapshots of your project state while working with the AI agent. Changes accumulate in work sessions that can be approved or discarded.

## Core Concepts

### Sessions and Approval

Each dialog manages changes through an approval workflow:

- **Approved state** - stable, verified version of your project
- **Work sessions** - accumulate changes that can be approved or discarded

**Location:** `.agentsmithy/dialogs/<dialog_id>/`

**Workflow:**
```
1. Work Session (session_1):
   User: "Create a TODO app"
   → Checkpoints accumulate in current session
   → AI creates files, makes changes
   
2. Approve:
   → Lock in all changes from session_1
   → Start new session_2
   
3. Continue working:
   → Checkpoints accumulate in session_2
   → Can approve or reset at any time
```

### Checkpoints

A **checkpoint** is a snapshot of your project state at a specific point in time. Checkpoints are created BEFORE the AI processes each user message.

**Example:**
```
session_1:
  Checkpoint: "Before user message: Create TODO app"
  → AI creates main.py, models.py, tests.py
  Checkpoint: "Before user message: Add tests"
  → AI creates test files

Approve → lock in session_1 changes → start session_2
```

## Automatic Checkpoint Creation

### Initial Snapshot

When creating a new dialog, an **initial checkpoint** (initial snapshot) is automatically created — a snapshot of the project before starting work with the AI.

```python
# Creating a dialog
dialog_id = project.create_dialog(title="My Feature")

# Automatically creates initial checkpoint
# Saved in metadata: dialog["initial_checkpoint"] = "abc123..."
```

### Per-Message Checkpoints

Each time the user submits a message, a checkpoint is automatically created BEFORE the AI starts processing:

1. **User submits message** — e.g., "Create a TODO app"
2. **Create checkpoint** — snapshot of current project state (BEFORE AI makes changes)
3. **AI processes request** — executes tools, modifies files
4. **User can rollback** — restore to the checkpoint to undo all AI changes

Commit message is auto-generated:
```
Before user message: Create a TODO app with 3 files
```

### When Are Checkpoints Created

✅ **Checkpoints are created:**
- **Before each user message** — automatic snapshot before AI processes the request
- **When creating a dialog** — initial snapshot of project state

❌ **Checkpoints are NOT created:**
- After individual tool executions (`write_to_file`, `replace_in_file`, etc.)
- During tool execution
- For read-only operations (`read_file`, `list_files`, `search_files`)
- For `run_command` (even if the command modifies files)

**Rationale:** One checkpoint per user message provides clean rollback points. To undo all changes from an AI response, restore to the checkpoint attached to the user message that triggered it.

## SSE Events for Checkpoints

### user Event

Sent when the user submits a message. A checkpoint is automatically created BEFORE the AI processes the request, capturing the project state before any changes.

```json
{
  "type": "user",
  "content": "Create a TODO app with 3 files",
  "checkpoint": "a1b2c3d4e5f6789abc",
  "dialog_id": "01J..."
}
```

**Purpose:** 
- Checkpoint represents the state BEFORE AI makes any changes
- Allows rolling back the entire AI response by restoring to this checkpoint
- Checkpoint ID is also stored in history for the user message

### file_edit Event

Sent immediately when a file is modified by a tool. This is a **control signal** for the UI to know which files to refresh/redraw.

```json
{
  "type": "file_edit",
  "file": "/abs/path/to/file.py",
  "diff": "--- a/...\n+++ b/...\n...",
  "dialog_id": "01J..."
}
```

**Purpose:**
- UI notification to refresh/redraw the file
- Provides diff for display (optional)
- Does NOT include checkpoint (checkpoint is on user message)

## Session Management API

### Get Session Status

```http
GET /api/dialogs/{dialog_id}/session
```

Get current session status and approval state.

**Response (with unapproved changes):**
```json
{
  "active_session": "session_2",
  "session_ref": "refs/heads/session_2",
  "has_unapproved": true,
  "last_approved_at": "2025-10-24T12:00:00Z"
}
```

**Response (all approved, no active session):**
```json
{
  "active_session": null,
  "session_ref": null,
  "has_unapproved": false,
  "last_approved_at": "2025-10-24T12:00:00Z"
}
```

### Approve Session

```http
POST /api/dialogs/{dialog_id}/approve
Content-Type: application/json

{
  "message": "Feature complete"  // optional
}
```

Approves all changes in the current session and starts a new session.

**Response:**
```json
{
  "approved_commit": "87cfd2cc7a0f1acd696fea7a73617ec700b6b919",
  "new_session": "session_2",
  "commits_approved": 5
}
```

**What happens:**
- Current session changes are locked in as approved
- Session marked as completed
- New session created from approved state
- Files indexed in RAG remain synced

### Reset to Approved

```http
POST /api/dialogs/{dialog_id}/reset
```

Discards all unapproved changes in the current session and returns to the last approved state.

**Response:**
```json
{
  "reset_to": "87cfd2cc7a0f1acd696fea7a73617ec700b6b919",
  "new_session": "session_2"
}
```

**What happens:**
- Current session discarded
- New session created from approved state
- Files restored to approved state
- RAG reindexed with approved file versions

### Restore to Checkpoint

```http
POST /api/dialogs/{dialog_id}/restore
Content-Type: application/json

{
  "checkpoint_id": "87cfd2cc7a0f1acd696fea7a73617ec700b6b919"
}
```

Restores files to a specific checkpoint state. Creates a new checkpoint after restore.

**Response:**
```json
{
  "restored_to": "87cfd2cc7a0f1acd696fea7a73617ec700b6b919",
  "new_checkpoint": "a5b8e3f..."
}
```

**Important:** 
- After restoration, a new checkpoint is created, so the restore itself can be undone
- Files indexed in RAG are automatically reindexed with restored contents

## Internal Architecture (Technical)

### Directory Structure

```
/project_root/
  .agentsmithy/
    dialogs/
      <dialog_id>/
        checkpoints/              # Internal checkpoint storage
          .git/                   # Git repository (implementation detail)
            refs/heads/
              main                # Approved state
              session_1           # Merged session (kept for recovery)
              session_2           # Active session
          metadata.json           # Checkpoint metadata
        journal.sqlite            # Dialog history + sessions table
```

### Branch Structure (Internal)

Git is used internally for efficient checkpoint management:

```
main          ← approved state (stable)
  |
  ├─ session_1  ← merged (status: merged)
  ├─ session_2  ← merged (status: merged)
  └─ session_3  ← current work (status: active)
```

### VersioningTracker API

```python
from agentsmithy.services.versioning import VersioningTracker

tracker = VersioningTracker(project_root, dialog_id)

# Create checkpoint in active session (automatic before user messages)
checkpoint = tracker.create_checkpoint("Before user message: ...")
# → CheckpointInfo(commit_id="abc123...", message="...")

# Approve current session
tracker.approve_all(message="Feature complete")
# → Locks in changes, creates new session

# Reset to approved state
tracker.reset_to_approved()
# → Discards current session, creates new from approved state

# Restore to specific checkpoint
tracker.restore_checkpoint("abc123...")
```

### Tool Integration

Tools use `start_edit()` / `finalize_edit()` for rollback protection:

```python
# write_file.py (simplified)
tracker = VersioningTracker(project_root, dialog_id)
tracker.start_edit([file_path])

try:
    file_path.write_text(content)
except:
    tracker.abort_edit()  # Restore file on error
    raise
else:
    tracker.finalize_edit()  # Cleanup
    
    # Note: Checkpoints are created before user messages, not by tools
```

### ChatService Creates Checkpoints

```python
# chat_service.py (simplified)
def _append_user_and_prepare_context(query, ...):
    # Create checkpoint BEFORE adding user message
    tracker = VersioningTracker(project_root, dialog_id)
    checkpoint = tracker.create_checkpoint(f"Before user message: {query[:50]}")
    
    # Add user message to history with checkpoint
    history.add_user_message(query, checkpoint=checkpoint.commit_id)
    
    # Emit SSE event
    yield EventFactory.user(content=query, checkpoint=checkpoint.commit_id)
```

## Metadata Storage

### Dialog Index

```json
{
  "dialogs": [
    {
      "id": "abc123...",
      "title": "My Feature",
      "created_at": "2025-10-23T15:00:00Z",
      "updated_at": "2025-10-23T16:30:00Z",
      "active_session": "session_2",
      "last_approved_at": "2025-10-23T16:00:00Z"
    }
  ],
  "current_dialog_id": "abc123..."
}
```

### Sessions Table (SQLite)

```sql
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_name TEXT UNIQUE,     -- "session_1", "session_2", etc.
    ref_name TEXT,                -- "refs/heads/session_1"
    status TEXT,                  -- "active", "merged", "abandoned"
    created_at TEXT,
    closed_at TEXT,               -- When merged or abandoned
    approved_commit TEXT,         -- Merge commit ID (for merged sessions)
    checkpoints_count INTEGER,
    branch_exists BOOLEAN DEFAULT 1
);

CREATE TABLE dialog_branches (
    branch_type TEXT PRIMARY KEY, -- "main" or "session"
    ref_name TEXT,
    head_commit TEXT,
    valid BOOLEAN
);
```

### File Edits Table (SQLite)

```sql
CREATE TABLE dialog_file_edits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dialog_id TEXT,
    file TEXT,                    -- File path
    diff TEXT,                    -- Unified diff (compressed via zlib)
    checkpoint TEXT,              -- Git commit ID
    created_at TEXT,
    message_index INTEGER,        -- Link to message in history
    INDEX(dialog_id, created_at)
);
```

## Best Practices

### For Frontend Developers

1. **Show approve/reset actions**
   - Display "Approve Session" button to merge changes into main
   - Display "Reset to Approved" to discard current work

2. **Indicate approved state**
   - Show if there are unapproved changes in current session
   - Optionally show session history (session_1 approved, session_2 active, etc.)

3. **Checkpoint visibility**
   - Checkpoints are attached to user messages in history
   - Use for "restore to here" functionality

### For Tool Developers

1. **Use `tracker.start_edit()` / `finalize_edit()`**
   - Ensures rollback on error

2. **DON't create checkpoints in tools**
   - Checkpoints are created automatically before user messages
   - Tools just modify files

## File Filtering

### Automatic Exclusions

Checkpoints automatically respect your project's `.gitignore` file. If a `.gitignore` exists, all patterns in it are excluded from checkpoints.

**Example `.gitignore`:**
```gitignore
node_modules/
dist/
build/
*.log
.env
```

All files matching these patterns will be excluded from checkpoints.

### Hardcoded Exclusions

In addition to `.gitignore`, the following are always excluded:

- **Hidden files and directories:** anything starting with `.`
- **Build artifacts:** `dist/`, `build/`, `target/`
- **Dependencies:** `node_modules/`, `venv/`, `.venv/`, `__pycache__/`
- **Binary files:** `*.pyc`, `*.pyo`, `*.so`, `*.dylib`, `*.dll`
- **AgentSmithy state:** `.agentsmithy/`

### Benefits

- **Smaller checkpoints:** Excludes unnecessary files (dependencies, build artifacts)
- **Faster operations:** Less files to scan and track
- **No conflicts:** Avoids tracking files that shouldn't be in version control
- **Respect project conventions:** Uses your existing `.gitignore` rules

## RAG Integration

### Automatic File Indexing

When the AI works with files, they are automatically indexed in the project's RAG vector store:

**Indexed on:**
- `read_file` - when reading a file
- `write_to_file` - when creating or overwriting a file
- `replace_in_file` - when editing a file

**Removed from index on:**
- `delete_file` - when deleting a file

**How it works:**
- File content is split into chunks (default 1000 chars)
- Chunks are embedded using OpenAI embeddings
- Stored in ChromaDB under `.agentsmithy/rag/chroma_db/`

This allows the AI to retrieve relevant file context through semantic similarity search.

### Restore and RAG Consistency

**Two-tier synchronization approach:**

#### 1. Immediate reindexing (when we know exactly what changed)

When files are modified through known operations:
- **Restore checkpoint** → reindex specific restored files
- **write_to_file** → index the written file
- **replace_in_file** → reindex the edited file
- **delete_file** → remove from RAG

This provides fast updates for known file changes.

#### 2. Full sync before processing (catch-all)

Before processing each user message, all indexed files are verified:
- File hash is calculated and compared with stored hash in RAG
- Files with mismatched hashes are automatically reindexed
- Files that no longer exist are removed from RAG

This catches changes made outside of tools:
- Files modified via `run_command`
- Manual edits by the user
- Any other external modifications

**Hash-based verification:** Each file in RAG stores an MD5 hash of its content in metadata. This allows detecting any discrepancies between indexed content and actual file state.

**Example workflow:**
```
1. User: "Read main.py" 
   → File indexed in RAG with hash
   
2. User: "Modify main.py" 
   → AI uses replace_in_file → File reindexed in RAG with new hash
   
3. User: Restore to earlier checkpoint
   → main.py reverted on disk → Reindexed in RAG
   
4. User manually edits config.py (outside tools)
   
5. User: "Add logging"
   → Before processing: Full sync detects config.py hash mismatch
   → config.py reindexed
   → AI proceeds with accurate context from RAG
```

This two-tier approach ensures the AI always has accurate file context, regardless of how files were modified.

## Limitations

1. **File filtering**
   - Follows `.gitignore` patterns using standard gitignore matching rules
   - Directory patterns (`dir/`) match the directory and all contents
   - Glob patterns (`*.log`) work as expected

2. **Storage size**
   - Each checkpoint = full project snapshot
   - Identical files are deduplicated, but storage grows
   - Old sessions are kept for recovery (can be cleaned up)
   - Recommendation: periodically delete old dialogs

3. **Dialog isolation**
   - Each dialog has its own checkpoint storage
   - Sessions from one dialog are not visible in another

4. **Best-effort restore**
   - Files that cannot be written during restore (e.g., in use by running process) are skipped
   - Restore logs which files were skipped
   - Most files will be restored successfully

5. **RAG indexing scope**
   - Only files explicitly read by the AI are indexed
   - RAG is not a complete project index
   - Reindexing on restore only updates files that were previously indexed

6. **Session storage**
   - Old sessions are kept for recovery but hidden
   - Merged/abandoned sessions marked in database
   - Can be cleaned up manually if needed

## Debugging (Advanced)

### Inspect Internal Storage

The checkpoint storage uses Git internally. For advanced debugging:

```bash
cd /path/to/project/.agentsmithy/dialogs/<dialog_id>/checkpoints/

# List all branches
git branch -a

# Show commits in main (approved)
git log main --oneline

# Show commits in active session
git log session_2 --oneline

# Show what's not approved yet
git log main..session_2 --oneline

# Compare approved vs current work
git diff main session_2

# Show merge commits (approvals)
git log --merges main --oneline

# Visualize branch structure
git log --all --graph --oneline
```

### Logs

```python
from agentsmithy.utils.logger import agent_logger

agent_logger.info("Created checkpoint in session",
    session="session_2",
    checkpoint_id=checkpoint.commit_id[:8],
    message=checkpoint.message[:50]
)
```

## Migration for Existing Dialogs

Dialogs created before sessions implementation:
- Will have all commits in a single unnamed branch
- On first use, `main` branch will be created from HEAD
- First session (`session_1`) will be created from `main`
- Old checkpoints remain accessible

## Examples

### Session Workflow

```
Session 1 (active):
  User: "Create a TODO app"
  → Checkpoint: "Before user message: Create a TODO app"
  → AI creates main.py, models.py, tests.py
  
  User: "Add database"
  → Checkpoint: "Before user message: Add database"
  → AI adds db.py
  
  User approves:
  POST /api/dialogs/{id}/approve
  {"message": "Initial TODO app"}
  
  Result:
  - session_1 changes locked in as approved
  - session_1 status → "merged"
  - session_2 created (active)

Session 2 (active):
  User: "Add authentication"
  → Checkpoint: "Before user message: Add authentication"
  → AI adds auth.py
  
  User decides to discard:
  POST /api/dialogs/{id}/reset
  
  Result:
  - session_2 status → "abandoned"
  - session_3 created (back to approved state)
```

### Restore to Checkpoint

```
Current state:
  Approved: [locked in changes]
  session_2 (active):
    - Checkpoint A: "Before: Add feature X"
    - Checkpoint B: "Before: Add feature Y"
    - Checkpoint C: "Before: Fix bug"

User wants to undo Checkpoint C:
  POST /api/dialogs/{id}/restore
  {"checkpoint_id": "<checkpoint_B>"}
  
Result:
  - Files restored to Checkpoint B state
  - New Checkpoint D created: "Restored to <checkpoint_B>"
  - Changes from Checkpoint C undone
  - Still in session_2 (not approved)
```

## Performance Considerations

### Storage

- Each checkpoint stores full project state
- Identical files are deduplicated automatically
- Typical overhead: ~10-50MB per dialog for medium projects
- Large projects (1000+ files): consider cleanup strategy

### Speed

- Checkpoint creation: O(n) where n = number of files in project
- Typical time: 50-200ms for projects with <500 files
- Restore: O(m) where m = number of files in checkpoint
- Typical time: 30-150ms

### Optimization Tips

1. **Add files to .gitignore**
   - Exclude `node_modules/`, `venv/`, build artifacts
   - Reduces checkpoint size and creation time

2. **Clean old dialogs**
   - Each dialog is independent
   - Deleting dialog removes its entire checkpoint repository

3. **Monitor disk usage**
   - Check `.agentsmithy/dialogs/` periodically
   - Large size indicates need for cleanup
