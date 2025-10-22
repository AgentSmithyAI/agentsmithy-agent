from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from agentsmithy.api.deps import get_project
from agentsmithy.api.schemas import (
    CurrentDialogResponse,
    DialogCreateRequest,
    DialogListResponse,
    DialogMetadata,
    DialogPatchRequest,
)
from agentsmithy.core.project import Project

router = APIRouter()


@router.get(
    "/api/dialogs", response_model=DialogListResponse, response_model_exclude_none=True
)
async def list_dialogs(
    sort: str = "updated_at",
    order: str = "desc",
    limit: int | None = 50,
    offset: int = 0,
    project: Project = Depends(get_project),  # noqa: B008
):
    descending = order.lower() != "asc"
    items = project.list_dialogs(
        sort_by=sort,
        descending=descending,
        limit=limit,
        offset=offset,
    )
    return DialogListResponse(
        current_dialog_id=project.get_current_dialog_id(),
        dialogs=[DialogMetadata(**item) for item in items],
    )


@router.post("/api/dialogs")
async def create_dialog(
    payload: DialogCreateRequest,
    project: Project = Depends(get_project),  # noqa: B008
):
    dialog_id = project.create_dialog(
        title=payload.title, set_current=payload.set_current
    )
    return {"id": dialog_id}


@router.get(
    "/api/dialogs/current",
    response_model=CurrentDialogResponse,
    response_model_exclude_none=True,
)
async def get_current_dialog(project: Project = Depends(get_project)):  # noqa: B008
    cid = project.get_current_dialog_id()
    if not cid:
        return CurrentDialogResponse(id=None, meta=None)
    meta = project.get_dialog_meta(cid)
    return CurrentDialogResponse(
        id=cid,
        meta=DialogMetadata(**meta) if meta else None,
    )


@router.patch("/api/dialogs/current")
async def set_current_dialog(
    id: str,
    project: Project = Depends(get_project),  # noqa: B008
):
    project.set_current_dialog_id(id)
    return {"ok": True}


@router.get(
    "/api/dialogs/{dialog_id}",
    response_model=DialogMetadata,
    response_model_exclude_none=True,
)
async def get_dialog(
    dialog_id: str,
    project: Project = Depends(get_project),  # noqa: B008
):
    meta = project.get_dialog_meta(dialog_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Dialog not found")
    return DialogMetadata(**meta)


@router.patch("/api/dialogs/{dialog_id}")
async def patch_dialog(
    dialog_id: str,
    payload: DialogPatchRequest,
    project: Project = Depends(get_project),  # noqa: B008
):
    fields: dict[str, Any] = {}
    if payload.title is not None:
        fields["title"] = payload.title
    if not fields:
        return {"ok": True}
    project.upsert_dialog_meta(dialog_id, **fields)
    return {"ok": True}


@router.delete("/api/dialogs/{dialog_id}")
async def delete_dialog(
    dialog_id: str,
    project: Project = Depends(get_project),  # noqa: B008
):
    project.delete_dialog(dialog_id)
    return {"ok": True}
