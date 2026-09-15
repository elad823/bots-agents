from __future__ import annotations

from typing import Any
try:
    from fastapi import APIRouter, HTTPException, status
except ImportError:
    class APIRouter:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass
        def get(self, *args: Any, **kwargs: Any) -> Any:
            return lambda fn: fn
        def post(self, *args: Any, **kwargs: Any) -> Any:
            return lambda fn: fn
        def delete(self, *args: Any, **kwargs: Any) -> Any:
            return lambda fn: fn

    class HTTPException(Exception):  # type: ignore
        def __init__(self, status_code: int, detail: str) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class status:  # type: ignore
        HTTP_200_OK = 200
        HTTP_201_CREATED = 201
        HTTP_400_BAD_REQUEST = 400
        HTTP_404_NOT_FOUND = 404
        HTTP_500_INTERNAL_SERVER_ERROR = 500

from backend.repositories.task_repository import task_repository
from backend.services.scheduler_service import scheduler_service

router = APIRouter(prefix="/api/tasks", tags=["Autonomous Tasks"])


@router.get("", response_model=None)
async def list_tasks() -> list[dict[str, Any]]:
    """Retrieve all scheduled tasks."""
    return await task_repository.get_all()


@router.post("", response_model=None, status_code=getattr(status, "HTTP_201_CREATED", 201))
async def create_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a new scheduled background task."""
    agent_id = payload.get("agent_id")
    name = payload.get("name")
    prompt = payload.get("prompt")
    schedule_type = payload.get("schedule_type", "interval")
    schedule_expr = payload.get("schedule_expr", "300")

    if not agent_id or not name or not prompt:
        raise HTTPException(
            status_code=getattr(status, "HTTP_400_BAD_REQUEST", 400),
            detail="Fields 'agent_id', 'name', and 'prompt' are required.",
        )

    task = await task_repository.create({
        "agent_id": agent_id,
        "name": name,
        "prompt": prompt,
        "schedule_type": schedule_type,
        "schedule_expr": schedule_expr,
        "is_active": 1,
    })

    # Add to active scheduler
    await scheduler_service.schedule_task(task)
    return task


@router.post("/{task_id}/run", response_model=None)
async def trigger_task(task_id: str) -> dict[str, Any]:
    """Manually trigger a scheduled task immediately."""
    try:
        return await scheduler_service.trigger_now(task_id)
    except ValueError as val_err:
        raise HTTPException(
            status_code=getattr(status, "HTTP_404_NOT_FOUND", 404),
            detail=str(val_err),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=getattr(status, "HTTP_500_INTERNAL_SERVER_ERROR", 500),
            detail=f"Failed to execute task run: {exc}",
        )


@router.delete("/{task_id}", response_model=None)
async def delete_task(task_id: str) -> dict[str, str]:
    """Delete a scheduled task."""
    await scheduler_service.remove_task(task_id)
    deleted = await task_repository.delete(task_id)
    if not deleted:
        raise HTTPException(
            status_code=getattr(status, "HTTP_404_NOT_FOUND", 404),
            detail=f"Task '{task_id}' not found.",
        )
    return {"status": "deleted", "task_id": task_id}


@router.get("/runs/recent", response_model=None)
async def list_recent_runs(limit: int = 30) -> list[dict[str, Any]]:
    """Retrieve history of autonomous task executions."""
    return await task_repository.get_recent_runs(limit=limit)
