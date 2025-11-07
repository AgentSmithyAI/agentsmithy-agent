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
  "session": "session_1",
  "dialog_id": "01J..."
}
```

**Purpose:** 
- Checkpoint represents the state BEFORE AI makes any changes
- Session indicates which work session this checkpoint belongs to
- Allows rolling back the entire AI response by restoring to this checkpoint
- Checkpoint and session IDs are also stored in history for the user message

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

## History Endpoint

The `/api/dialogs/{dialog_id}/history` endpoint returns the dialog history as a list of events. User messages include both `checkpoint` and `session` fields:

```http
GET /api/dialogs/{dialog_id}/history?limit=20
```

**Response:**
```json
{
  "events": [
    {
      "type": "user",
      "content": "Create a TODO app",
      "checkpoint": "a1b2c3d4e5f6789abc",
      "session": "session_1",
      "idx": 0
    },
    {
      "type": "chat",
      "content": "I'll create the app...",
      "idx": 1
    },
    {
      "type": "user",
      "content": "Add authentication",
      "checkpoint": "b2c3d4e5f6789abc12",
      "session": "session_2",
      "idx": 2
    }
  ],
  "has_more": false,
  "cursor": null
}
```

**Fields:**
- `checkpoint` - Checkpoint ID for this user message
- `session` - Session name when checkpoint was created (e.g., "session_1", "session_2")
- Session changes after each approve operation

## Checkpoints API

### List All Checkpoints

```http
GET /api/dialogs/{dialog_id}/checkpoints
```

Get all checkpoints for a dialog in chronological order.

**Response:**
```json
{
  "dialog_id": "abc123",
  "checkpoints": [
    {
      "commit_id": "a1b2c3d4e5f6789abc",
      "message": "Before user message: Create TODO app"
    },
    {
      "commit_id": "b2c3d4e5f6789abc12",
      "message": "Before user message: Add authentication"
    },
    {
      "commit_id": "c3d4e5f6789abc123",
      "message": "Before user message: Add tests"
    }
  ],
  "initial_checkpoint": "a1b2c3d4e5f6789abc"
}
```

**Fields:**
- `dialog_id` - Dialog identifier
- `checkpoints` - Array of all checkpoints in chronological order (oldest first)
  - `commit_id` - Full commit SHA for the checkpoint
  - `message` - Human-readable checkpoint message
- `initial_checkpoint` - ID of the very first checkpoint (snapshot before any AI changes)

**Use cases:**
- Display checkpoint history in UI
- Allow user to browse and restore to any checkpoint
- Show when the initial snapshot was created

## Session Management API

### Get Session Status

```http
GET /api/dialogs/{dialog_id}/session
```

Get current session status and approval state, including detailed list of changed files.

**Response (with unapproved changes):**
```json
{
  "active_session": "session_2",
  "session_ref": "refs/heads/session_2",
  "has_unapproved": true,
  "last_approved_at": "2025-10-24T12:00:00Z",
  "changed_files": [
    {
      "path": "src/main.py",
      "status": "modified",
      "additions": 15,
      "deletions": 3,
      "diff": "--- a/src/main.py\n+++ b/src/main.py\n@@ -1,5 +1,5 @@\n def main():\n-    print('old')\n+    print('new')\n     return 0",
      "base_content": "def main():\n    print('old')\n    return 0",
      "is_binary": false,
      "is_too_large": false
    },
    {
      "path": "src/new_feature.py",
      "status": "added",
      "additions": 42,
      "deletions": 0,
      "diff": null,
      "base_content": null,
      "is_binary": false,
      "is_too_large": false
    },
    {
      "path": "old_file.py",
      "status": "deleted",
      "additions": 0,
      "deletions": 28,
      "diff": null,
      "base_content": "# old file content...",
      "is_binary": false,
      "is_too_large": false
    }
  ]
}
```

**Response (all approved, no active session):**
```json
{
  "active_session": null,
  "session_ref": null,
  "has_unapproved": false,
  "last_approved_at": "2025-10-24T12:00:00Z",
  "changed_files": []
}
```

**Changed Files Details:**
- `path`: File path relative to project root
- `status`: Change type (`FileChangeStatus` enum):
  - `"added"` - File was created
  - `"modified"` - File was changed
  - `"deleted"` - File was removed
- `additions`: Number of lines added (0 for binary files or staged-only files)
- `deletions`: Number of lines deleted (0 for binary files or staged-only files)
- `diff`: Unified diff text with proper headers (`--- a/path`, `+++ b/path`) for modified files (null for added/deleted/binary/staged-only files)
- `base_content`: Original file content from base checkpoint (main). Null for:
  - Added files (didn't exist in base)
  - Binary files
  - Files exceeding 1MB size limit
- `is_binary`: Boolean flag indicating if file is binary (contains null bytes)
- `is_too_large`: Boolean flag indicating if file exceeds 1MB size limit

**Note**: `changed_files` includes both:
1. **Committed changes** (checkpointed but not approved) - includes full statistics, diffs, and base content
2. **Staged changes** (prepared but not checkpointed) - includes statistics, diffs, and base content

**Use Case for `base_content`:**
Client applications already have access to modified file content (current state). The `base_content` field provides the original content from the base checkpoint, enabling clients to visualize changes without needing to apply patches or maintain separate copies of file states.

**Unified Diff Format:**
The `diff` field now contains properly formatted unified diff with standard headers:
```diff
--- a/src/main.py
+++ b/src/main.py
@@ -1,5 +1,5 @@
 def main():
-    print('old')
+    print('new')
     return 0
```

This format is compatible with standard diff parsing libraries and includes:
- File path headers (`--- a/path` and `+++ b/path`) on separate lines
- Hunk headers (`@@ -a,b +c,d @@`)
- Context lines (prefixed with space)
- Added lines (prefixed with `+`)
- Removed lines (prefixed with `-`)

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

Tools use `start_edit()` / `finalize_edit()` for rollback protection and `stage_file()` to track agent-created files:

```python
# write_file.py (simplified)
tracker = VersioningTracker(project_root, dialog_id)
tracker.start_edit([file_path])

try:
    file_path.write_text(content)
    
    # Stage file immediately - force-add to staging area
    # This ensures file is included in next checkpoint even if ignored
    tracker.stage_file(file_path)
except:
    tracker.abort_edit()  # Restore file on error
    raise
else:
    tracker.finalize_edit()  # Cleanup
    
    # Note: Checkpoints are created before user messages, not by tools
```

**What `stage_file()` does:**
- Adds file to Git staging area (index)
- Equivalent to `git add -f` - force-adds even if file matches ignore patterns
- Staged files are included in next checkpoint
- Staging area is cleared after checkpoint creation

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

In addition to `.gitignore`, the following are always excluded from checkpoints:

**AgentSmithy state:**
- `.agentsmithy/` - internal state and checkpoints
- `chroma_db/` - RAG vector store

**Version control:**
- `.git/`, `.svn/`, `.hg/`

**Python:**
- `.venv/`, `venv/`, `env/`, `.env/` - virtual environments
- `__pycache__/`, `*.pyc`, `*.pyo`, `*.pyd` - bytecode
- `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.tox/`
- `.coverage`, `coverage/`, `htmlcov/` - test coverage
- `*.egg-info/`, `dist/`, `build/`, `.eggs/`
- `.ipynb_checkpoints/`, `.hypothesis/`, `.nox/`, `.benchmarks/`

**JavaScript/TypeScript:**
- `node_modules/` - dependencies
- `.next/`, `.nuxt/`, `.cache/`, `.parcel-cache/`
- `dist/`, `build/`, `out/`, `.output/`
- `coverage/`, `.nyc_output/`

**Rust:**
- `target/` - build output
- `Cargo.lock` - only for libraries

**Go:**
- `vendor/` - dependencies

**C/C++:**
- `*.o`, `*.a`, `*.so`, `*.dylib`, `*.dll`, `*.exe`

**Java:**
- `target/`, `build/` - build output
- `*.class`, `*.jar`, `*.war`

**IDEs and editors:**
- `.idea/`, `.vscode/`, `*.swp`, `*.swo`, `.DS_Store`

**Logs:**
- `*.log`, `logs/`, `npm-debug.log*`, `yarn-debug.log*`

**OS:**
- `.DS_Store`, `Thumbs.db`, `desktop.ini`

See `DEFAULT_EXCLUDES` in `agentsmithy/services/versioning.py` for the complete list.

### Benefits

- **Smaller checkpoints:** Excludes unnecessary files (dependencies, build artifacts)
- **Faster operations:** Less files to scan and track
- **No conflicts:** Avoids tracking files that shouldn't be in version control
- **Respect project conventions:** Uses your existing `.gitignore` rules

## Staging Area and Force-Add

### How Agent-Created Files Are Tracked

When the AI agent explicitly creates or modifies files using tools like `write_file` or `replace_in_file`, these files are **staged immediately** to Git's staging area (index), even if they match ignore patterns.

**Example:**
```python
# Agent creates a file in an ignored directory
write_file(".venv/config.py", content)
→ File is staged to .git/index immediately (equivalent to git add -f)
→ Will be included in next checkpoint even though .venv/ is in DEFAULT_EXCLUDES
```

### Checkpoint Creation with Staging

When a checkpoint is created:

1. **Scan working directory** - Add all files EXCEPT those matching ignore patterns
2. **Merge staging area** - Add staged files even if they match ignore patterns
3. **Commit tree** - Create checkpoint with all files
4. **Clear staging area** - Remove staged entries after successful commit

**Storage:** `.agentsmithy/dialogs/<dialog_id>/checkpoints/.git/index`

### Restore and Staging Cleanup

When restoring to a checkpoint:

1. **Collect files to delete from two sources:**
   - Files in HEAD checkpoint tree
   - Files in staging area (uncommitted but agent-created)

2. **Delete files** in `(HEAD_files ∪ staged_files - target_files)`

3. **Restore files** from target checkpoint tree

4. **Clear staging area** - Remove all staged entries after restore

5. **Clean up empty directories**

**Example scenario:**
```
Checkpoint 1: main.py, README.md

Agent creates: .github/workflows/ci.yaml
→ File staged to index (but no checkpoint created yet)

User resets to Checkpoint 1:
→ .github/workflows/ci.yaml deleted (staged but not in checkpoint 1)
→ Staging area cleared
→ has_unapproved: false ✅
```

### Why Staging Area?

**Before (tracked_files.json):**
- Custom JSON file tracked agent-created files
- Required manual sync logic
- Non-standard approach

**After (Git staging area):**
- Uses standard Git index mechanism
- Equivalent to `git add -f` for force-adding ignored files
- Consistent with Git semantics
- Automatically cleared after checkpoint/restore

**Rationale:** If agent explicitly calls `write_file(".venv/config.py")`, it's intentional (not an artifact), so it should be included in checkpoints despite matching ignore patterns.

## File Change Scenarios

This section covers all scenarios of file creation, modification, and deletion, and how the system handles each case.

### File Operation Methods

Files can be changed in two ways:

1. **Via agent tools** - `write_file`, `replace_in_file`, `delete_file`
2. **Via commands or user** - `run_command` with `rm`, manual edits, shell operations

The key difference: **Tool operations stage files to Git index, command operations don't.**

### Scenario 1: File Created via Tool

```python
write_file("app.py", content)
```

**What happens:**
1. File written to disk
2. `tracker.stage_file("app.py")` - added to Git index (staging area)
3. **Before checkpoint:** `get_staged_files()` shows `status: "added"`
4. **Checkpoint created:** File scanned from workdir + merged from index → included in checkpoint
5. **Restore:** File will be deleted if not in target checkpoint

**Edge case (ignored files):**
```python
write_file(".venv/config.py", content)  # .venv/ in .gitignore
```
- Staging ensures file is included despite .gitignore
- Without staging, file would be skipped by workdir scan

### Scenario 2: File Created via Command

```bash
run_command("echo 'test' > temp.txt")
```

**What happens:**
1. File written to disk by command
2. **NOT staged** (command tools don't call tracker methods)
3. **Before checkpoint:** `get_staged_files()` shows `status: "added"` (detected by workdir scan vs HEAD)
4. **Checkpoint created:** File found by workdir scan → included in checkpoint
5. **Restore:** File will be deleted if not in target checkpoint

**Edge case (ignored files):**
```bash
run_command("mkdir .venv && echo 'config' > .venv/config.py")
```
- ❌ **Will NOT be included in checkpoint** (matches .gitignore)
- This is expected behavior - we don't track artifacts created by commands
- Only agent-explicit file creation (via tools) forces inclusion

### Scenario 3: File Modified via Tool

```python
replace_in_file("main.py", old, new)
```

**What happens:**
1. File modified on disk
2. `tracker.stage_file("main.py")` - updated in Git index
3. **Before checkpoint:** `get_staged_files()` shows `status: "modified"` with diff
4. **Checkpoint created:** Modified content included
5. **Restore:** File reverted to target checkpoint version

### Scenario 4: File Modified via Command

```bash
run_command("sed -i 's/old/new/g' main.py")
```

**What happens:**
1. File modified by command
2. **NOT staged**
3. **Before checkpoint:** `get_staged_files()` - file **NOT shown** (not in index, but see below)
4. **Checkpoint created:** Modified content detected by workdir scan → included
5. **Restore:** File reverted to target checkpoint version

**Important:** Modified files created by commands are detected during checkpoint creation (workdir scan), but NOT shown in `get_staged_files()` until checkpoint is created. After checkpoint, the change is visible as diff between checkpoints.

### Scenario 5: File Deleted via Tool

```python
delete_file("old.py")
```

**What happens:**
1. File removed from disk
2. `tracker.stage_file_deletion("old.py")` - removed from Git index
3. **Before checkpoint:** `get_staged_files()` shows `status: "deleted"` with base_content
4. **Checkpoint created:** File absent from workdir + absent from index → NOT in checkpoint
5. **Restore:** File will be restored if present in target checkpoint

**Why stage_file_deletion needed:**
- Only for edge case: file was staged (via tool) but then deleted before checkpoint
- Example: `write_file("temp.py")` → `delete_file("temp.py")` → no checkpoint yet
- Without staging deletion, file would remain in index and appear as "added" despite not existing

### Scenario 6: File Deleted via Command

```bash
run_command("rm old.py")
# or
run_command("rm -rf src/")
```

**What happens:**
1. File(s) removed from disk by command
2. **NOT staged for deletion** (command tools don't call tracker)
3. **Before checkpoint:** `get_staged_files()` shows `status: "deleted"` - detected by comparing HEAD vs workdir
4. **Checkpoint created:** File absent from workdir scan → NOT in checkpoint
5. **Restore:** File will be restored if present in target checkpoint

**This works for:**
- Single file deletion: `rm file.py`
- Directory deletion: `rm -rf directory/`
- Bulk operations: `find . -name "*.tmp" -delete`
- Manual deletion by user

**Detection mechanism:**
```
1. Get files from HEAD checkpoint
2. Get files from working directory
3. Diff: files in HEAD but not in workdir = deleted
```

### Session Status API

`GET /api/dialogs/{id}/session` shows ALL changes before checkpoint creation:

```json
{
  "changed_files": [
    {
      "path": "new.py",
      "status": "added",
      "additions": 42,
      "deletions": 0
    },
    {
      "path": "main.py",
      "status": "modified",
      "additions": 15,
      "deletions": 3,
      "diff": "unified diff...",
      "base_content": "original content..."
    },
    {
      "path": "old.py",
      "status": "deleted",
      "additions": 0,
      "deletions": 28,
      "base_content": "deleted file content..."
    }
  ]
}
```

**What's included:**
- ✅ Files staged via tools (in index)
- ✅ Files created/deleted via commands (detected by workdir vs HEAD diff)
- ❌ Files modified via commands (not detectable until checkpoint - workdir content doesn't have "previous version")

### Checkpoint Creation

When creating a checkpoint:

1. **Scan working directory** - Find all non-ignored files
2. **Merge staging area** - Add staged files even if ignored
3. **Build tree** - Create Git tree with all files
4. **Commit** - Save snapshot

**Result:**
- Created files: present in tree
- Modified files: present with new content
- Deleted files: **absent from tree** (automatically excluded)

### Restore Process

When restoring to a checkpoint:

1. **Compare trees** - Diff current HEAD vs target checkpoint
2. **Delete files** - Remove files present in HEAD but not in target
3. **Restore files** - Write files from target checkpoint
4. **Handle modified** - Overwrite with target versions

**Examples:**

```
Checkpoint A: [main.py, utils.py, config.py]
Checkpoint B: [main.py, utils.py]           # config.py deleted

Restore A→B: Delete config.py
Restore B→A: Restore config.py from checkpoint A tree
```

### What Can Go Wrong

**Problem 1: Ignored files created via command**
```bash
run_command("mkdir build && echo 'output' > build/result.txt")
```
- ❌ `build/result.txt` won't be in checkpoint (matches ignore patterns)
- ✅ **Expected behavior** - build artifacts shouldn't be tracked
- 🔧 **Solution:** If file is important, create it via `write_file` tool

**Problem 2: Large file modifications**
```python
# File is 5MB, modified externally
run_command("./process_data.py input.csv")  # Modifies input.csv
```
- Modified file will be in checkpoint (full 5MB)
- Session API won't show the modification until checkpoint
- 🔧 **Solution:** This is expected - checkpoints are full snapshots

**Problem 3: Race condition with external processes**
```bash
run_command("npm install")  # Creates node_modules/
# Checkpoint happens while npm is still running
```
- Checkpoint might capture partial state
- 🔧 **Solution:** Ensure commands complete before checkpoint (they do by default)

**Problem 4: Symbolic links**
```bash
run_command("ln -s /etc/config app/config")
```
- Symlinks are not followed or tracked
- 🔧 **Solution:** Copy file content instead of creating symlink

### Summary Table

| Operation | Method | Staged? | In get_staged_files? | In Checkpoint? | Ignored files? |
|-----------|--------|---------|---------------------|----------------|----------------|
| Create | Tool | ✅ | ✅ added | ✅ | ✅ Force-included |
| Create | Command | ❌ | ✅ added | ✅ | ❌ Skipped |
| Modify | Tool | ✅ | ✅ modified | ✅ | ✅ If already tracked |
| Modify | Command | ❌ | ❌ | ✅ | ✅ If already tracked |
| Delete | Tool | ✅ removed | ✅ deleted | ❌ | ✅ Works for any file |
| Delete | Command | ❌ | ✅ deleted | ❌ | ✅ Works for any file |

**Key insight:** Staging is only needed for **ignored files created via tools**. For everything else, workdir scanning handles detection and checkpoint creation automatically.

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
