# Checkpoints and Transactions

AgentSmithy automatically saves snapshots of your project state while working with the AI agent. This allows you to rollback changes and restore previous versions of files.

## Core Concepts

### Checkpoints

A **checkpoint** is a Git commit that contains a complete snapshot of your project state at a specific point in time. Each dialog stores its checkpoints in an isolated Git repository.

**Location:** `.agentsmithy/dialogs/<dialog_id>/checkpoints/.git`

### Transactions

A **transaction** groups multiple file operations into a single checkpoint. Instead of creating a separate checkpoint for each modified file, all changes within a single AI response are grouped into one checkpoint.

**Example:**
```
User: "Create a TODO app with main.py, models.py and tests.py"

AI executes:
  write_to_file: main.py
  write_to_file: models.py  
  write_to_file: tests.py

Result: ONE checkpoint "Transaction: 3 files"
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

### Transaction Checkpoints

Each time the AI modifies files, a transaction is created:

1. **Begin transaction** — before executing the first file modification tool
2. **Track changes** — each `write_to_file`, `replace_in_file`, `delete_file` is registered
3. **Commit transaction** — after successful execution of all tools, one checkpoint is created

Commit message is auto-generated:
```
Transaction: 3 files
write: src/main.py
replace: src/utils.py
delete: src/old.py
```

### Which Operations Create Checkpoints

✅ **Create checkpoints:**
- `write_to_file` — create/overwrite file
- `replace_in_file` — edit file (diff)
- `delete_file` — delete file

❌ **Do NOT create checkpoints:**
- `run_command` — command execution (even if the command modifies files)
- `read_file` — read-only
- `list_files` — read-only
- `search_files` — search-only
- Other read-only tools

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

**Important:** After restoration, a new checkpoint is created, so the restore itself can be undone!

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

# Create checkpoint
checkpoint = tracker.create_checkpoint("My checkpoint")
# → CheckpointInfo(commit_id="abc123...", message="My checkpoint")

# Transactions
tracker.begin_transaction()
tracker.track_file_change("file1.py", "write")
tracker.track_file_change("file2.py", "replace")
checkpoint = tracker.commit_transaction()

# List checkpoints
checkpoints = tracker.list_checkpoints()
# → [CheckpointInfo(...), CheckpointInfo(...), ...]

# Restore
tracker.restore_checkpoint("abc123...")
```

### Tool Integration

Tools automatically use transactions:

```python
# write_file.py
tracker = VersioningTracker(project_root, dialog_id)
tracker.start_edit([file_path])

try:
    file_path.write_text(content)
except:
    tracker.abort_edit()
    raise
else:
    tracker.finalize_edit()
    
    # If transaction is active - only register
    if tracker.is_transaction_active():
        tracker.track_file_change(rel_path, "write")
    else:
        # Otherwise create checkpoint immediately
        checkpoint = tracker.create_checkpoint(f"write_to_file: {rel_path}")
```

### ToolExecutor Manages Transactions

```python
# tool_executor.py (simplified)
async def _process_streaming(messages):
    # ...AI generates tool_calls...
    
    # Begin transaction before executing tools
    if self._versioning_tracker:
        self._versioning_tracker.begin_transaction()
    
    transaction_success = False
    try:
        for tool_call in accumulated_tool_calls:
            # Execute tools (they register changes themselves)
            result = await self.tool_manager.run_tool(name, **args)
        
        transaction_success = True
    finally:
        # Commit or abort transaction
        if self._versioning_tracker and self._versioning_tracker.is_transaction_active():
            if transaction_success:
                checkpoint = self._versioning_tracker.commit_transaction()
            else:
                self._versioning_tracker.abort_transaction()
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

## Limitations

1. **Visible files only**
   - Hidden files (`.gitignore`, `.env`) are excluded
   - Directories from `.gitignore` are excluded

2. **Repository size**
   - Each checkpoint = full project snapshot
   - Git deduplicates identical files, but storage grows
   - Recommendation: periodically delete old dialogs

3. **Dialog isolation**
   - Each dialog has its own Git repository
   - Checkpoints from one dialog are not visible in another

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

Old checkpoints (one per file):
- Remain unchanged
- New checkpoints created using new logic (one per transaction)

## Examples

### Simple File Edit

```python
# User: "Fix the bug in utils.py"

# AI executes:
Transaction begins
  → replace_in_file: utils.py
Transaction commits
  → Checkpoint: "Transaction: 1 files\nreplace: utils.py"
```

### Multiple File Creation

```python
# User: "Create REST API with routes, models, and tests"

# AI executes:
Transaction begins
  → write_to_file: api/routes.py
  → write_to_file: api/models.py
  → write_to_file: tests/test_api.py
Transaction commits
  → Checkpoint: "Transaction: 3 files\nwrite: api/routes.py\nwrite: api/models.py\nwrite: tests/test_api.py"
```

### Restore Workflow

```python
# 1. User makes changes through AI
Checkpoint A: Initial snapshot
Checkpoint B: Transaction - created 3 files
Checkpoint C: Transaction - modified 1 file

# 2. User decides to undo last change
POST /api/dialogs/{id}/restore
{"checkpoint_id": "B"}

# 3. System restores to checkpoint B
All files restored to state at checkpoint B
Creates Checkpoint D: "Restored to checkpoint B"

# 4. User can still go back to C if needed
POST /api/dialogs/{id}/restore
{"checkpoint_id": "C"}
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
