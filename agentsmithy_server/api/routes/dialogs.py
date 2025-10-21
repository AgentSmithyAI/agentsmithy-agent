from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from agentsmithy_server.api.deps import get_project
from agentsmithy_server.api.schemas import (
    DialogCreateRequest,
    DialogPatchRequest,
)
from agentsmithy_server.core.project import Project

router = APIRouter()


@router.get("/api/dialogs")
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
    # Remove null title fields
    cleaned_items = []
    for item in items:
        cleaned = {k: v for k, v in item.items() if v is not None}
        cleaned_items.append(cleaned)

    return {
        "current_dialog_id": project.get_current_dialog_id(),
        "dialogs": cleaned_items,
    }


@router.post("/api/dialogs")
async def create_dialog(
    payload: DialogCreateRequest,
    project: Project = Depends(get_project),  # noqa: B008
):
    dialog_id = project.create_dialog(
        title=payload.title, set_current=payload.set_current
    )
    return {"id": dialog_id}


@router.get("/api/dialogs/current")
async def get_current_dialog(project: Project = Depends(get_project)):  # noqa: B008
    cid = project.get_current_dialog_id()
    if not cid:
        return {"id": None}
    meta = project.get_dialog_meta(cid)
    # Remove null fields from meta
    cleaned_meta = {k: v for k, v in meta.items() if v is not None} if meta else None
    return {"id": cid, "meta": cleaned_meta}


@router.patch("/api/dialogs/current")
async def set_current_dialog(
    id: str,
    project: Project = Depends(get_project),  # noqa: B008
):
    project.set_current_dialog_id(id)
    return {"ok": True}


@router.get("/api/dialogs/{dialog_id}")
async def get_dialog(
    dialog_id: str,
    project: Project = Depends(get_project),  # noqa: B008
):
    meta = project.get_dialog_meta(dialog_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Dialog not found")
    # Remove null fields
    return {k: v for k, v in meta.items() if v is not None}


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
