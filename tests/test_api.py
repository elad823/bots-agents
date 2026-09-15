from __future__ import annotations

import os
import tempfile

try:
    import pytest
except ImportError:
    class _MockMark:
        @staticmethod
        def asyncio(fn):
            return fn
    class _MockPytest:
        mark = _MockMark()
    pytest = _MockPytest()

from backend.core.database import init_database
from backend.api.routes_system import system_status
from backend.api.routes_agents import list_agents, create_agent, delete_agent
from backend.api.routes_chat import send_chat
from backend.api.routes_tasks import list_tasks, create_task, trigger_task, delete_task


@pytest.mark.asyncio
async def test_api_system_and_agents() -> None:
    """Test system diagnostics and agent API endpoints."""
    await init_database()

    # 1. System status
    status_resp = await system_status()
    assert status_resp["status"] == "ok"
    assert "rate_limiter" in status_resp

    # 2. List agents
    agents = await list_agents()
    assert len(agents) >= 2

    # 3. Create agent
    new_agent = await create_agent({
        "name": "DevOps Architect",
        "role": "Cloud infrastructure and CI/CD expert",
        "system_prompt": "You are a DevOps Architect specializing in Terraform and Docker.",
        "slug": "devops_arch",
    })
    assert new_agent["slug"] == "devops_arch"

    # 4. Delete agent
    del_resp = await delete_agent(new_agent["id"])
    assert del_resp["status"] == "deleted"


@pytest.mark.asyncio
async def test_api_chat_and_tasks() -> None:
    """Test chat dispatch and task scheduling API endpoints."""
    await init_database()

    # 1. Chat dispatch
    chat_resp = await send_chat({
        "prompt": "Hello via API, please report your role.",
        "target_agent": "supervisor",
    })
    assert "response" in chat_resp
    assert chat_resp["agent_slug"] == "supervisor"

    # 2. Task endpoints
    agents = await list_agents()
    supervisor_id = next(a["id"] for a in agents if a["slug"] == "supervisor")

    task = await create_task({
        "agent_id": supervisor_id,
        "name": "API Scheduled Probe",
        "prompt": "Probe network health",
        "schedule_type": "interval",
        "schedule_expr": "120",
    })
    assert task["name"] == "API Scheduled Probe"

    # 3. Trigger task
    run_resp = await trigger_task(task["id"])
    assert run_resp["status"] == "success"

    # 4. Delete task
    del_resp = await delete_task(task["id"])
    assert del_resp["status"] == "deleted"
