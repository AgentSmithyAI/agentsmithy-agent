"""Checkpoint management API routes.

Provides endpoints to:
- List all checkpoints for a dialog
- Restore project state to a specific checkpoint
- Reset dialog to initial checkpoint
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentsmithy.api.deps import get_project
from agentsmithy.core.project import Project
from agentsmithy.services.versioning import VersioningTracker
from agentsmithy.utils.logger import get_logger

logger = get_logger("api.checkpoints")

router = APIRouter(prefix="/api/dialogs", tags=["checkpoints"])


class CheckpointResponse(BaseModel):
    """Single checkpoint metadata."""

    commit_id: str = Field(..., description="Git commit ID")
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

    checkpoint_id: str = Field(..., description="Checkpoint commit ID to restore to")


class RestoreResponse(BaseModel):
    """Response after restoring to a checkpoint."""

    restored_to: str = Field(..., description="Checkpoint ID that was restored")
    new_checkpoint: str = Field(
        ..., description="New checkpoint ID created after restore"
    )


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
            restored_files = tracker.restore_checkpoint(request.checkpoint_id)
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

        # Sync RAG with actual file state (check hashes and reindex if needed)
        try:
            vector_store = project.get_vector_store()
            sync_stats = await vector_store.sync_files_if_needed()

            if sync_stats["reindexed"] > 0 or sync_stats["removed"] > 0:
                logger.info(
                    "Synced RAG after restore",
                    dialog_id=dialog_id,
                    checked=sync_stats["checked"],
                    reindexed=sync_stats["reindexed"],
                    removed=sync_stats["removed"],
                )
        except Exception as rag_err:
            # Don't fail restore if RAG sync fails
            logger.warning(
                "Failed to sync RAG after restore",
                dialog_id=dialog_id,
                error=str(rag_err),
            )

        # Create new checkpoint after restore (makes restore reversible)
        new_checkpoint = tracker.create_checkpoint(
            f"Restored to checkpoint {request.checkpoint_id[:8]}"
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


@router.post("/{dialog_id}/reset", response_model=RestoreResponse)
async def reset_dialog(
    dialog_id: str,
    project: Project = Depends(get_project),  # noqa: B008
) -> RestoreResponse:
    """Reset dialog to its initial checkpoint (before any changes).

    This is a convenience endpoint that restores to the initial checkpoint
    created when the dialog was first started.

    Args:
        dialog_id: Dialog ID

    Returns:
        RestoreResponse with initial checkpoint ID and new checkpoint ID

    Raises:
        HTTPException: If initial checkpoint not found
    """
    try:
        # Get initial checkpoint from metadata
        index = project.load_dialogs_index()
        initial_checkpoint_id = None
        for dialog in index.get("dialogs", []):
            if dialog.get("id") == dialog_id:
                initial_checkpoint_id = dialog.get("initial_checkpoint")
                break

        if not initial_checkpoint_id:
            raise HTTPException(
                status_code=404,
                detail=f"Initial checkpoint not found for dialog {dialog_id}",
            )

        # Restore to initial checkpoint (best-effort, skips locked files)
        tracker = VersioningTracker(str(project.root), dialog_id)
        restored_files = []
        try:
            restored_files = tracker.restore_checkpoint(initial_checkpoint_id)
            logger.info(
                "Reset dialog to initial checkpoint",
                dialog_id=dialog_id,
                checkpoint_id=initial_checkpoint_id[:8],
                files_restored=len(restored_files),
            )
        except Exception as restore_err:
            # Log but don't fail - restore is best-effort
            logger.warning(
                "Reset completed with errors (some files may be skipped)",
                dialog_id=dialog_id,
                error=str(restore_err),
            )

        # Sync RAG with actual file state (check hashes and reindex if needed)
        try:
            vector_store = project.get_vector_store()
            sync_stats = await vector_store.sync_files_if_needed()

            if sync_stats["reindexed"] > 0 or sync_stats["removed"] > 0:
                logger.info(
                    "Synced RAG after reset",
                    dialog_id=dialog_id,
                    checked=sync_stats["checked"],
                    reindexed=sync_stats["reindexed"],
                    removed=sync_stats["removed"],
                )
        except Exception as rag_err:
            # Don't fail reset if RAG sync fails
            logger.warning(
                "Failed to sync RAG after reset",
                dialog_id=dialog_id,
                error=str(rag_err),
            )

        # Create new checkpoint after reset
        new_checkpoint = tracker.create_checkpoint(
            f"Reset to initial checkpoint {initial_checkpoint_id[:8]}"
        )

        return RestoreResponse(
            restored_to=initial_checkpoint_id,
            new_checkpoint=new_checkpoint.commit_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to reset dialog", dialog_id=dialog_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e
