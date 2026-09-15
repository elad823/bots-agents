from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import urllib.error
import urllib.request
from typing import Any, Coroutine, TypeVar

# Try importing httpx
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

# Backend service imports for in-process bridge fallback
try:
    from backend.core.config import settings
    from backend.core.rate_limiter import rate_limiter
    from backend.core.llm_gateway import llm_gateway
    from backend.repositories.task_repository import task_repository
    from backend.services.agent_service import agent_service
    from backend.services.chat_service import chat_service
    from backend.services.scheduler_service import scheduler_service
    HAS_BACKEND = True
except Exception:
    HAS_BACKEND = False

BACKEND_URL = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000").rstrip("/")

T = TypeVar("T")


def _run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Helper to run async backend coroutines safely inside Streamlit worker threads."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            def _exec() -> T:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(coro)
                finally:
                    new_loop.close()
            return pool.submit(_exec).result()

    return loop.run_until_complete(coro)


class APIClient:
    """Dual-mode client for communicating with the MAS backend.

    Tries HTTP REST first (for containerized and remote deployments).
    Seamlessly falls back to direct in-process services if local network/sandbox restricts sockets.
    """

    def __init__(self, base_url: str = BACKEND_URL) -> None:
        self.base_url = base_url

    def _http_request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        """Synchronous HTTP request using httpx or standard library urllib."""
        url = f"{self.base_url}{path}"

        if HAS_HTTPX:
            with httpx.Client(timeout=30.0) as client:
                if method == "GET":
                    resp = client.get(url)
                elif method == "POST":
                    resp = client.post(url, json=payload or {})
                elif method == "DELETE":
                    resp = client.delete(url)
                else:
                    resp = client.request(method, url, json=payload or {})
                resp.raise_for_status()
                return resp.json()

        # Fallback to standard library urllib
        req = urllib.request.Request(url, method=method)
        req.add_header("Content-Type", "application/json")
        data_bytes = json.dumps(payload).encode("utf-8") if payload else None

        with urllib.request.urlopen(req, data=data_bytes, timeout=30.0) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}

    def get_system_status(self) -> dict[str, Any]:
        """Fetch health check and rate limiter diagnostics."""
        try:
            return self._http_request("GET", "/api/system/status")
        except Exception:
            if HAS_BACKEND:
                agents = _run_async(agent_service.list_agents())
                return {
                    "status": "ok",
                    "environment": settings.environment,
                    "llm_mode": "mock" if llm_gateway.is_mock_mode else "live_gemini",
                    "registered_agents_count": len(agents),
                    "scheduler_running": scheduler_service._is_running,
                    "rate_limiter": rate_limiter.get_status(),
                }
            return {
                "status": "offline",
                "environment": "unknown",
                "registered_agents_count": 0,
                "scheduler_running": False,
                "rate_limiter": {"current_window_requests": 0, "max_rpm": 14, "remaining_slots": 14, "is_cooling_down": False},
            }

    def get_agents(self) -> list[dict[str, Any]]:
        """Fetch all registered agents."""
        try:
            return self._http_request("GET", "/api/agents")
        except Exception:
            if HAS_BACKEND:
                return _run_async(agent_service.list_agents())
            raise

    def create_agent(self, name: str, role: str, system_prompt: str, slug: str | None = None) -> dict[str, Any]:
        """Manually spawn a new agent."""
        try:
            return self._http_request("POST", "/api/agents", {
                "name": name,
                "role": role,
                "system_prompt": system_prompt,
                "slug": slug or name.lower().replace(" ", "_"),
            })
        except Exception:
            if HAS_BACKEND:
                return _run_async(agent_service.create_agent(
                    name=name,
                    role=role,
                    system_prompt=system_prompt,
                    slug=slug,
                ))
            raise

    def delete_agent(self, agent_id: str) -> dict[str, Any]:
        """Delete an agent by ID."""
        try:
            return self._http_request("DELETE", f"/api/agents/{agent_id}")
        except Exception:
            if HAS_BACKEND:
                success = _run_async(agent_service.delete_agent(agent_id))
                return {"status": "deleted" if success else "failed", "agent_id": agent_id}
            raise

    def send_chat(self, prompt: str, session_id: str | None = None, target_agent: str = "supervisor") -> dict[str, Any]:
        """Send chat query to supervisor or specialist."""
        try:
            return self._http_request("POST", "/api/chat", {
                "prompt": prompt,
                "session_id": session_id,
                "target_agent": target_agent,
            })
        except Exception:
            if HAS_BACKEND:
                return _run_async(chat_service.send_message(
                    prompt=prompt,
                    session_id=session_id,
                    target_agent=target_agent,
                ))
            raise

    def get_chat_history(self, session_id: str) -> list[dict[str, Any]]:
        """Fetch message history for a session."""
        try:
            return self._http_request("GET", f"/api/chat/history/{session_id}")
        except Exception:
            if HAS_BACKEND:
                return _run_async(chat_service.get_history(session_id))
            return []

    def get_tasks(self) -> list[dict[str, Any]]:
        """Fetch all scheduled tasks."""
        try:
            return self._http_request("GET", "/api/tasks")
        except Exception:
            if HAS_BACKEND:
                return _run_async(task_repository.get_all())
            return []

    def create_task(self, agent_id: str, name: str, prompt: str, schedule_type: str, schedule_expr: str) -> dict[str, Any]:
        """Create a scheduled background task."""
        try:
            return self._http_request("POST", "/api/tasks", {
                "agent_id": agent_id,
                "name": name,
                "prompt": prompt,
                "schedule_type": schedule_type,
                "schedule_expr": schedule_expr,
            })
        except Exception:
            if HAS_BACKEND:
                task = _run_async(task_repository.create({
                    "agent_id": agent_id,
                    "name": name,
                    "prompt": prompt,
                    "schedule_type": schedule_type,
                    "schedule_expr": schedule_expr,
                    "is_active": 1,
                }))
                _run_async(scheduler_service.schedule_task(task))
                return task
            raise

    def trigger_task(self, task_id: str) -> dict[str, Any]:
        """Trigger an autonomous task run immediately."""
        try:
            return self._http_request("POST", f"/api/tasks/{task_id}/run")
        except Exception:
            if HAS_BACKEND:
                return _run_async(scheduler_service.trigger_now(task_id))
            raise

    def delete_task(self, task_id: str) -> dict[str, Any]:
        """Delete a scheduled task."""
        try:
            return self._http_request("DELETE", f"/api/tasks/{task_id}")
        except Exception:
            if HAS_BACKEND:
                _run_async(scheduler_service.remove_task(task_id))
                deleted = _run_async(task_repository.delete(task_id))
                return {"status": "deleted" if deleted else "failed", "task_id": task_id}
            raise

    def get_recent_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        """Fetch history of task execution runs."""
        try:
            return self._http_request("GET", f"/api/tasks/runs/recent?limit={limit}")
        except Exception:
            if HAS_BACKEND:
                return _run_async(task_repository.get_recent_runs(limit))
            return []


api_client = APIClient()
