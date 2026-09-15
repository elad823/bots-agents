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
        def put(self, *args: Any, **kwargs: Any) -> Any:
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

from backend.services.agent_service import agent_service

router = APIRouter(prefix="/api/agents", tags=["Agents"])


@router.get("", response_model=None)
async def list_agents() -> list[dict[str, Any]]:
    """Retrieve all registered agents."""
    return await agent_service.list_agents()


@router.post("", response_model=None, status_code=getattr(status, "HTTP_201_CREATED", 201))
async def create_agent(payload: dict[str, Any]) -> dict[str, Any]:
    """Manually register a new specialist agent."""
    name = payload.get("name")
    role = payload.get("role")
    system_prompt = payload.get("system_prompt")
    slug = payload.get("slug")
    model = payload.get("model", "gemini-1.5-flash")

    if not name or not role or not system_prompt:
        raise HTTPException(
            status_code=getattr(status, "HTTP_400_BAD_REQUEST", 400),
            detail="Fields 'name', 'role', and 'system_prompt' are required.",
        )

    return await agent_service.create_agent(
        name=name,
        role=role,
        system_prompt=system_prompt,
        slug=slug,
        model=model,
    )


@router.get("/{agent_id}", response_model=None)
async def get_agent(agent_id: str) -> dict[str, Any]:
    """Retrieve details of an agent by ID or slug."""
    agent = await agent_service.get_agent(agent_id)
    if not agent:
        raise HTTPException(
            status_code=getattr(status, "HTTP_404_NOT_FOUND", 404),
            detail=f"Agent '{agent_id}' not found.",
        )
    return agent


@router.delete("/{agent_id}", response_model=None)
async def delete_agent(agent_id: str) -> dict[str, str]:
    """Delete a dynamic agent (system agents like supervisor cannot be deleted)."""
    success = await agent_service.delete_agent(agent_id)
    if not success:
        raise HTTPException(
            status_code=getattr(status, "HTTP_400_BAD_REQUEST", 400),
            detail=f"Cannot delete agent '{agent_id}' (it may be a protected system agent or not exist).",
        )
    return {"status": "deleted", "agent_id": agent_id}
