from __future__ import annotations

from fastapi import APIRouter

from agentsmithy_server.api.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse()
