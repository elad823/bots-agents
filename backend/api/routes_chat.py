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

    class HTTPException(Exception):  # type: ignore
        def __init__(self, status_code: int, detail: str) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class status:  # type: ignore
        HTTP_200_OK = 200
        HTTP_400_BAD_REQUEST = 400
        HTTP_404_NOT_FOUND = 404
        HTTP_500_INTERNAL_SERVER_ERROR = 500

from backend.services.chat_service import chat_service

router = APIRouter(prefix="/api/chat", tags=["Chat & Orchestration"])


@router.post("", response_model=None)
async def send_chat(payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch message to supervisor or specialist agent and run multi-agent graph."""
    prompt = payload.get("prompt")
    if not prompt or not prompt.strip():
        raise HTTPException(
            status_code=getattr(status, "HTTP_400_BAD_REQUEST", 400),
            detail="Payload field 'prompt' is required and cannot be empty.",
        )

    session_id = payload.get("session_id")
    target_agent = payload.get("target_agent", "supervisor")

    try:
        return await chat_service.send_message(
            prompt=prompt.strip(),
            session_id=session_id,
            target_agent=target_agent,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=getattr(status, "HTTP_500_INTERNAL_SERVER_ERROR", 500),
            detail=f"Multi-agent execution error: {exc}",
        )


@router.get("/history/{session_id}", response_model=None)
async def get_history(session_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Retrieve chat history for a session."""
    return await chat_service.get_history(session_id=session_id, limit=limit)


@router.get("/sessions", response_model=None)
async def list_sessions() -> list[str]:
    """Retrieve list of active chat sessions."""
    return await chat_service.list_sessions()
