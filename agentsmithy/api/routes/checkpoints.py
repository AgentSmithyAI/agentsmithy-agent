"""Checkpoint management API routes.

Provides endpoints to:
- List all checkpoints for a dialog
- Restore project state to a specific checkpoint
- Reset dialog to initial checkpoint
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from agentsmithy.api.deps import get_project
from agentsmithy.core.background_tasks import get_background_manager
from agentsmithy.core.project import Project
from agentsmithy.services.versioning import VersioningTracker
from agentsmithy.utils.logger import get_logger

logger = get_logger("api.checkpoints")

router = APIRouter(prefix="/api/dialogs", tags=["checkpoints"])


async def _reindex_files_background(
    project: Project, dialog_id: str, restored_files: list[str]
) -> None:
    """Background task to reindex restored files in RAG.

    Args:
        project: Project instance
        dialog_id: Dialog ID for logging
        restored_files: List of file paths to reindex
    """
    try:
        vector_store = project.get_vector_store()
        reindexed_count = await vector_store.reindex_files(restored_files)

        if reindexed_count > 0:
            logger.info(
                "Reindexed restored files in RAG (background)",
                dialog_id=dialog_id,
                reindexed=reindexed_count,
                total_restored=len(restored_files),
            )
    except Exception as rag_err:
        # Log but don't fail - this is best-effort background operation
        logger.warning(
            "Failed to reindex files in RAG (background)",
            dialog_id=dialog_id,
            error=str(rag_err),
        )


class CheckpointResponse(BaseModel):
    """Single checkpoint metadata."""

    commit_id: str = Field(..., description="Checkpoint ID")
    message: str = Field(..., description="Checkpoint message")


class CheckpointsListResponse(BaseModel):
    """List of checkpoints for a dialog."""

    dialog_id: str
    checkpoints: list[CheckpointResponse]
    initial_checkpoint: str | None = Field(
        None, description="Initial checkpoint ID from dialog metadata"
    )


class RestoreRequest(BaseModel):
    """Request to restore to a specific checkpoint."""

    checkpoint_id: str = Field(..., description="Checkpoint ID to restore to")


class RestoreResponse(BaseModel):
    """Response after restoring to a checkpoint."""

    restored_to: str = Field(..., description="Checkpoint ID that was restored")
    new_checkpoint: str = Field(
        ..., description="New checkpoint ID created after restore"
    )


class ApproveRequest(BaseModel):
    """Request to approve current session."""

    message: str | None = Field(None, description="Optional approval message")


class ApproveResponse(BaseModel):
    """Response after approving a session."""

    approved_commit: str = Field(..., description="Approved checkpoint ID")
    new_session: str = Field(..., description="New active session name")
    commits_approved: int = Field(..., description="Number of checkpoints approved")


class ResetResponse(BaseModel):
    """Response after resetting to approved state."""

    reset_to: str = Field(..., description="Checkpoint ID of approved state")
    new_session: str = Field(..., description="New active session name")


class SessionStatusResponse(BaseModel):
    """Response with current session status."""

    active_session: str | None = Field(
        None, description="Name of active session (null if no unapproved changes)"
    )
    session_ref: str | None = Field(
        None, description="Reference of active session (null if no unapproved changes)"
    )
    has_unapproved: bool = Field(
        ..., description="Whether there are unapproved changes"
    )
    last_approved_at: str | None = Field(None, description="Timestamp of last approval")


@router.get("/{dialog_id}/checkpoints", response_model=CheckpointsListResponse)
async def list_checkpoints(
    dialog_id: str,
    project: Project = Depends(get_project),  # noqa: B008
) -> CheckpointsListResponse:
    """List all checkpoints for a dialog in chronological order.

    Returns:
        CheckpointsListResponse with list of checkpoints and initial checkpoint ID
    """
    try:
        tracker = VersioningTracker(str(project.root), dialog_id)
        checkpoints = tracker.list_checkpoints()

        # Get initial checkpoint from dialog metadata
        initial_checkpoint_id = None
        try:
            index = project.load_dialogs_index()
            for dialog in index.get("dialogs", []):
                if dialog.get("id") == dialog_id:
                    initial_checkpoint_id = dialog.get("initial_checkpoint")
                    break
        except Exception:
            pass

        return CheckpointsListResponse(
            dialog_id=dialog_id,
            checkpoints=[
                CheckpointResponse(commit_id=cp.commit_id, message=cp.message)
                for cp in checkpoints
            ],
            initial_checkpoint=initial_checkpoint_id,
        )
    except Exception as e:
        logger.error("Failed to list checkpoints", dialog_id=dialog_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{dialog_id}/session", response_model=SessionStatusResponse)
async def get_session_status(
    dialog_id: str,
    project: Project = Depends(get_project),  # noqa: B008
) -> SessionStatusResponse:
    """Get current session status for a dialog.

    Returns information about the active session and approval state.

    Args:
        dialog_id: Dialog ID

    Returns:
        SessionStatusResponse with active session info
    """
    try:
        from agentsmithy.db.sessions import get_active_session

        # Get active session from database
        db_path = project.get_dialog_dir(dialog_id) / "journal.sqlite"
        active_session = get_active_session(db_path) or "session_1"

        # Check if there are unapproved changes
        # 1. Compare committed trees between main and session
        # 2. Check for uncommitted changes in working directory
        tracker = VersioningTracker(str(project.root), dialog_id)
        repo = tracker.ensure_repo()

        has_unapproved = False

        # Check uncommitted changes first (files on disk vs last checkpoint)
        if tracker.has_uncommitted_changes():
            has_unapproved = True
        # Check committed but unapproved changes (session vs main)
        elif tracker.MAIN_BRANCH in repo.refs:
            session_ref = tracker._get_session_ref(active_session)
            if session_ref in repo.refs:
                main_head = repo.refs[tracker.MAIN_BRANCH]
                session_head = repo.refs[session_ref]

                # Compare trees (file contents), not commit SHAs
                main_commit = repo[main_head]
                session_commit = repo[session_head]
                main_tree = getattr(main_commit, "tree", None)
                session_tree = getattr(session_commit, "tree", None)

                # If trees are different, there are committed but unapproved changes
                has_unapproved = main_tree != session_tree

        # Get last approved timestamp from dialog metadata
        last_approved_at = None
        try:
            index = project.load_dialogs_index()
            for dialog in index.get("dialogs", []):
                if dialog.get("id") == dialog_id:
                    last_approved_at = dialog.get("last_approved_at")
                    break
        except Exception:
            pass

        # If no unapproved changes, return null for session info
        if has_unapproved:
            return SessionStatusResponse(
                active_session=active_session,
                session_ref=f"refs/heads/{active_session}",
                has_unapproved=True,
                last_approved_at=last_approved_at,
            )
        else:
            return SessionStatusResponse(
                active_session=None,
                session_ref=None,
                has_unapproved=False,
                last_approved_at=last_approved_at,
            )
    except Exception as e:
        logger.error("Failed to get session status", dialog_id=dialog_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{dialog_id}/restore", response_model=RestoreResponse)
async def restore_checkpoint(
    dialog_id: str,
    request: RestoreRequest,
    project: Project = Depends(get_project),  # noqa: B008
) -> RestoreResponse:
    """Restore project state to a specific checkpoint.

    This will:
    1. Restore all files to the state they were in at the checkpoint
    2. Create a new checkpoint after the restore (so restore itself is reversible)
    3. Schedule RAG reindexing in the background (non-blocking)

    Args:
        dialog_id: Dialog ID
        request: Restore request with checkpoint_id

    Returns:
        RestoreResponse with restored checkpoint ID and new checkpoint ID
    """
    try:
        tracker = VersioningTracker(str(project.root), dialog_id)

        # Verify checkpoint exists
        checkpoints = tracker.list_checkpoints()
        checkpoint_ids = [cp.commit_id for cp in checkpoints]
        if request.checkpoint_id not in checkpoint_ids:
            raise HTTPException(
                status_code=404,
                detail=f"Checkpoint {request.checkpoint_id} not found in dialog {dialog_id}",
            )

        # Restore to checkpoint (best-effort, skips locked files)
        restored_files = []
        try:
            restored_files = await asyncio.to_thread(
                tracker.restore_checkpoint, request.checkpoint_id
            )
            logger.info(
                "Restored to checkpoint",
                dialog_id=dialog_id,
                checkpoint_id=request.checkpoint_id[:8],
                files_restored=len(restored_files),
            )
        except Exception as restore_err:
            # Log but don't fail - restore is best-effort
            logger.warning(
                "Restore completed with errors (some files may be skipped)",
                dialog_id=dialog_id,
                error=str(restore_err),
            )

        # Schedule RAG reindexing in background (tracked by manager for graceful shutdown)
        if restored_files:
            bg_manager = get_background_manager()
            bg_manager.create_thread_task(
                _reindex_files_background(project, dialog_id, restored_files),
                name=f"reindex_restore_{dialog_id[:8]}",
            )
            logger.debug(
                "Scheduled RAG reindexing in background",
                dialog_id=dialog_id,
                files_count=len(restored_files),
            )

        # Create new checkpoint after restore (makes restore reversible)
        new_checkpoint = await asyncio.to_thread(
            tracker.create_checkpoint,
            f"Restored to checkpoint {request.checkpoint_id[:8]}",
        )

        return RestoreResponse(
            restored_to=request.checkpoint_id,
            new_checkpoint=new_checkpoint.commit_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to restore checkpoint", dialog_id=dialog_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{dialog_id}/approve", response_model=ApproveResponse)
async def approve_session(
    dialog_id: str,
    project: Project = Depends(get_project),  # noqa: B008
    request: ApproveRequest = Body(default=ApproveRequest(message=None)),  # noqa: B008
) -> ApproveResponse:
    """Approve current session and lock in all changes.

    This will:
    1. Lock in all changes from current session as approved
    2. Mark session as 'merged' in database
    3. Create a new active session from approved state

    Args:
        dialog_id: Dialog ID
        request: Approve request with optional message

    Returns:
        ApproveResponse with approved commit ID and new session name
    """
    try:
        tracker = VersioningTracker(str(project.root), dialog_id)

        # Approve session
        result = tracker.approve_all(message=request.message)

        # Update dialog metadata with new session and approval timestamp
        from datetime import datetime

        now = datetime.utcnow().isoformat()
        project.upsert_dialog_meta(
            dialog_id,
            active_session=result["new_session"],
            last_approved_at=now,
        )

        logger.info(
            "Approved session",
            dialog_id=dialog_id,
            approved_commit=result["approved_commit"][:8],
            new_session=result["new_session"],
            commits_approved=result["commits_approved"],
        )

        return ApproveResponse(**result)
    except Exception as e:
        logger.error("Failed to approve session", dialog_id=dialog_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{dialog_id}/reset", response_model=ResetResponse)
async def reset_to_approved(
    dialog_id: str,
    project: Project = Depends(get_project),  # noqa: B008
) -> ResetResponse:
    """Reset current session to approved state.

    This will:
    1. Discard current session (mark as 'abandoned' in database)
    2. Create new session from approved state
    3. Restore files to approved state
    4. Schedule RAG reindexing in the background (non-blocking)

    Args:
        dialog_id: Dialog ID

    Returns:
        ResetResponse with reset commit ID and new session name
    """
    try:
        tracker = VersioningTracker(str(project.root), dialog_id)

        # Reset to approved
        result = await asyncio.to_thread(tracker.reset_to_approved)

        # Update dialog metadata with new session
        project.upsert_dialog_meta(
            dialog_id,
            active_session=result["new_session"],
        )

        # Restore files to approved state
        restored_files = []
        try:
            restored_files = await asyncio.to_thread(
                tracker.restore_checkpoint, result["reset_to"]
            )
            logger.info(
                "Reset to approved state",
                dialog_id=dialog_id,
                reset_to=result["reset_to"][:8],
                new_session=result["new_session"],
                files_restored=len(restored_files),
            )
        except Exception as restore_err:
            logger.warning(
                "Reset completed with errors (some files may be skipped)",
                dialog_id=dialog_id,
                error=str(restore_err),
            )

        # Schedule RAG reindexing in background (tracked by manager for graceful shutdown)
        if restored_files:
            bg_manager = get_background_manager()
            bg_manager.create_thread_task(
                _reindex_files_background(project, dialog_id, restored_files),
                name=f"reindex_reset_{dialog_id[:8]}",
            )
            logger.debug(
                "Scheduled RAG reindexing after reset in background",
                dialog_id=dialog_id,
                files_count=len(restored_files),
            )
        return ResetResponse(**result)
    except Exception as e:
        logger.error("Failed to reset to approved", dialog_id=dialog_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e
