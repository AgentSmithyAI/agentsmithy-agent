# Checkpoints and Transactions

AgentSmithy automatically saves snapshots of your project state while working with the AI agent. This allows you to rollback changes and restore previous versions of files.

## Core Concepts

### Checkpoints

A **checkpoint** is a Git commit that contains a complete snapshot of your project state at a specific point in time. Each dialog stores its checkpoints in an isolated Git repository.

**Location:** `.agentsmithy/dialogs/<dialog_id>/checkpoints/.git`

**Key principle:** Checkpoints are created BEFORE the AI processes each user message, not after. This provides clean rollback points - you can undo an entire AI response by restoring to the checkpoint from the user message that triggered it.

**Example:**
```
User: "Create a TODO app with main.py, models.py and tests.py"
  → Checkpoint created: snapshot BEFORE AI starts work
  
AI executes:
  write_to_file: main.py
  write_to_file: models.py  
  write_to_file: tests.py

Result: All changes can be undone by restoring to the checkpoint
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

## Checkpoint Management API

### List Checkpoints

```http
GET /api/dialogs/{dialog_id}/checkpoints
```

**Response:**
```json
{
  "dialog_id": "abc123...",
  "checkpoints": [
    {
      "commit_id": "1dd9c64b1618bcfab943c2bfc0542032fd96afd2",
      "message": "Initial snapshot before dialog: My Feature"
    },
    {
      "commit_id": "87cfd2cc7a0f1acd696fea7a73617ec700b6b919",
      "message": "Transaction: 3 files\nwrite: main.py\nwrite: models.py\nwrite: tests.py"
    },
    {
      "commit_id": "f7c93285cef5c892da0ffdf48dc929860b9e0ef2",
      "message": "Transaction: 1 files\nreplace: main.py"
    }
  ],
  "initial_checkpoint": "1dd9c64b1618bcfab943c2bfc0542032fd96afd2"
}
```

### Restore to Checkpoint

```http
POST /api/dialogs/{dialog_id}/restore
Content-Type: application/json

{
  "checkpoint_id": "87cfd2cc7a0f1acd696fea7a73617ec700b6b919"
}
```

**Response:**
```json
{
  "restored_to": "87cfd2cc7a0f1acd696fea7a73617ec700b6b919",
  "new_checkpoint": "a5b8e3f..."
}
```

**Important:** 
- After restoration, a new checkpoint is created, so the restore itself can be undone!
- Files that were indexed in the RAG vector store will be automatically reindexed with their restored contents
- This ensures the AI model gets accurate file context from RAG similarity search

### Reset Dialog to Initial State

```http
POST /api/dialogs/{dialog_id}/reset
```

Restores the project to the initial checkpoint (state before dialog started).

**Response:**
```json
{
  "restored_to": "1dd9c64b1618bcfab943c2bfc0542032fd96afd2",
  "new_checkpoint": "c9d2e4a..."
}
```

## Internal Architecture

### Directory Structure

```
/project_root/
  .agentsmithy/
    dialogs/
      <dialog_id>/
        checkpoints/              # Git repository for checkpoints
          .git/                   # Git objects, commits
          metadata.json           # Additional metadata
        journal.sqlite            # Dialog history + file_edits table
```

### VersioningTracker API

```python
from agentsmithy.services.versioning import VersioningTracker

tracker = VersioningTracker(project_root, dialog_id)

# Create checkpoint (done automatically before user messages)
checkpoint = tracker.create_checkpoint("Before user message: ...")
# → CheckpointInfo(commit_id="abc123...", message="...")

# List checkpoints
checkpoints = tracker.list_checkpoints()
# → [CheckpointInfo(...), CheckpointInfo(...), ...]

# Restore to checkpoint
tracker.restore_checkpoint("abc123...")
```

**Note:** Transactions (`begin_transaction`, `track_file_change`, `commit_transaction`) are available in the API for advanced use cases, but the standard flow creates checkpoints only before user messages.

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
      "initial_checkpoint": "1dd9c64b..."
    }
  ],
  "current_dialog_id": "abc123..."
}
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

### For UI Developers

1. **Show checkpoints in dialog history**
   - Display "Restore to here" button next to each file_edit event
   
2. **Group changes by transactions**
   - If multiple file_edits have the same checkpoint → it's one transaction

3. **Add "Reset Dialog" button**
   - Quick restore to initial checkpoint

### For Tool Developers

1. **Use `tracker.start_edit()` / `finalize_edit()`**
   - Ensures rollback on error

2. **Check `is_transaction_active()`**
   - If transaction is active → only register changes
   - If not → create checkpoint immediately

3. **DON'T create checkpoints in `run_command`**
   - Commands can do anything, not all changes need tracking

## File Filtering and .gitignore Support

### Automatic Exclusions

Checkpoints automatically respect your project's `.gitignore` file. If a `.gitignore` exists, all patterns in it are honored when creating checkpoints.

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

1. **Git-like behavior**
   - Follows `.gitignore` patterns using standard gitignore matching rules
   - Directory patterns (`dir/`) match the directory and all contents
   - Glob patterns (`*.log`) work as expected

2. **Repository size**
   - Each checkpoint = full project snapshot
   - Git deduplicates identical files, but storage grows
   - Recommendation: periodically delete old dialogs

3. **Dialog isolation**
   - Each dialog has its own Git repository
   - Checkpoints from one dialog are not visible in another

4. **Best-effort restore**
   - Files that cannot be written during restore (e.g., in use by running process) are skipped
   - Restore logs which files were skipped
   - Most files will be restored successfully

5. **RAG indexing scope**
   - Only files explicitly read by the AI are indexed
   - RAG is not a complete project index
   - Reindexing on restore only updates files that were previously indexed

## Debugging

### Inspect Repository Manually

```bash
cd /path/to/project/.agentsmithy/dialogs/<dialog_id>/checkpoints/

# List commits
git log --oneline

# Show checkpoint contents
git show <commit_id>

# Compare two checkpoints
git diff <commit1> <commit2>
```

### Logs

```python
from agentsmithy.utils.logger import agent_logger

agent_logger.info("Created transaction checkpoint",
    checkpoint_id=checkpoint.commit_id[:8],
    message=checkpoint.message[:50]
)
```

## Migration for Existing Dialogs

Dialogs created before transaction implementation:
- Will not have `initial_checkpoint` in metadata
- Checkpoints are created from the first change after update

Old checkpoints (one per file, if applicable from previous versions):
- Remain unchanged
- New checkpoints created using new logic (one per user message)

## Examples

### Simple Conversation Flow

```
1. User: "Fix the bug in utils.py"
   → Checkpoint A: "Before user message: Fix the bug..."
   
2. AI executes: replace_in_file: utils.py
   → file_edit event (UI refreshes utils.py)
   
3. User: "Also add tests"
   → Checkpoint B: "Before user message: Also add tests"
   
4. AI executes: write_to_file: tests/test_utils.py
   → file_edit event (UI shows new test file)
```

### Restore Workflow

```
Dialog history:
  Checkpoint 0: Initial snapshot (dialog creation)
  Checkpoint 1: Before "Create REST API" → AI created 3 files
  Checkpoint 2: Before "Add authentication" → AI modified 2 files
  Checkpoint 3: Before "Fix bug" → AI modified 1 file

User decides to undo "Fix bug":
  POST /api/dialogs/{id}/restore
  {"checkpoint_id": "<checkpoint_2>"}
  
Result:
  - Project restored to state after "Add authentication"
  - All changes from "Fix bug" are undone
  - Checkpoint 4 created: "Restored to checkpoint <checkpoint_2>"
  - Restore is reversible (can go back to checkpoint 3)
```

## Performance Considerations

### Storage

- Each checkpoint stores full project state in Git objects
- Git's object storage deduplicates identical blobs
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
