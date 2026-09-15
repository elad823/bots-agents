from __future__ import annotations

from typing import Any
try:
    from fastapi import APIRouter
except ImportError:
    class APIRouter:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass
        def get(self, *args: Any, **kwargs: Any) -> Any:
            return lambda fn: fn

from backend.core.config import settings
from backend.core.llm_gateway import llm_gateway
from backend.core.rate_limiter import rate_limiter
from backend.repositories.agent_repository import agent_repository
from backend.services.scheduler_service import scheduler_service

router = APIRouter(prefix="/api/system", tags=["System & Diagnostics"])


@router.get("/status", response_model=None)
async def system_status() -> dict[str, Any]:
    """Return health check and rate limit diagnostic metrics."""
    agents = await agent_repository.get_all()
    limiter_status = rate_limiter.get_status()

    return {
        "status": "ok",
        "environment": settings.environment,
        "llm_mode": "mock" if llm_gateway.is_mock_mode else "live_gemini",
        "registered_agents_count": len(agents),
        "scheduler_running": scheduler_service._is_running,
        "rate_limiter": limiter_status,
    }
