from __future__ import annotations

import asyncio
import pytest
from fastapi.testclient import TestClient

from backend.core.database import init_database
from backend.core.rate_limiter import rate_limiter
from backend.main import app


@pytest.fixture(scope="module", autouse=True)
def setup_e2e_environment():
    """Initialize clean database and reset rate limiter for the E2E test session."""
    asyncio.run(init_database())
    rate_limiter.reset()
    yield
    rate_limiter.reset()


@pytest.fixture
def client():
    """FastAPI synchronous test client."""
    with TestClient(app) as test_client:
        yield test_client


def test_e2e_01_system_status_and_health(client: TestClient):
    """AC-01 & AC-08: Health diagnostics, quota status, and agent registry."""
    response = client.get("/api/system/status")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert "environment" in data
    assert "rate_limiter" in data
    assert data["rate_limiter"]["max_rpm"] == 14
    assert data["registered_agents_count"] >= 3


def test_e2e_02_agent_full_lifecycle(client: TestClient):
    """AC-02: Agent creation, retrieval, and persistence verification."""
    # 1. Create specialist agent
    agent_payload = {
        "name": "DevOps Pipeline Architect",
        "slug": "devops_architect_e2e",
        "role": "Cloud infrastructure and CI/CD automation specialist",
        "system_prompt": "You are a senior DevOps architect specializing in Cloud Run and GitHub Actions.",
    }
    create_res = client.post("/api/agents", json=agent_payload)
    assert create_res.status_code == 201
    created = create_res.json()
    assert created["slug"] == "devops_architect_e2e"
    agent_id = created["id"]

    # 2. Retrieve all agents and confirm presence
    list_res = client.get("/api/agents")
    assert list_res.status_code == 200
    agents = list_res.json()
    slugs = [a["slug"] for a in agents]
    assert "devops_architect_e2e" in slugs

    # 3. Clean up created agent
    del_res = client.delete(f"/api/agents/{agent_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"


def test_e2e_03_chat_conversational_and_delegation(client: TestClient):
    """AC-03 & AC-04: Multi-agent conversational dispatch with delegation."""
    session_id = "e2e-session-chat-101"
    chat_payload = {
        "prompt": "Please analyze and research potential security risks in container deployment.",
        "session_id": session_id,
        "target_agent": "supervisor",
    }
    chat_res = client.post("/api/chat", json=chat_payload)
    assert chat_res.status_code == 200
    data = chat_res.json()

    assert "response" in data
    assert len(data["response"]) > 0
    assert data["session_id"] == session_id

    # Verify history is persisted in SQLite
    hist_res = client.get(f"/api/chat/history/{session_id}")
    assert hist_res.status_code == 200
    history = hist_res.json()
    assert len(history) >= 2  # user prompt + agent response


def test_e2e_04_dynamic_agent_spawning(client: TestClient):
    """AC-04: On-the-fly specialist spawning through supervisor."""
    session_id = "e2e-session-spawn-102"
    prompt = "We need an expert in Kubernetes deployment to configure our production cluster."
    chat_res = client.post("/api/chat", json={
        "prompt": prompt,
        "session_id": session_id,
        "target_agent": "supervisor",
    })
    assert chat_res.status_code == 200
    data = chat_res.json()

    assert "response" in data
    assert len(data["response"]) > 0

    # Verify that a Kubernetes specialist was dynamically registered in SQLite
    agents_res = client.get("/api/agents")
    slugs = [a["slug"] for a in agents_res.json()]
    assert any("kubernetes" in s for s in slugs)


def test_e2e_05_autonomous_task_lifecycle(client: TestClient):
    """AC-05: Autonomous background task scheduling, triggering, and logs."""
    # 1. Fetch valid registered agent ID
    agents_res = client.get("/api/agents")
    assert agents_res.status_code == 200
    agents = agents_res.json()
    assert len(agents) > 0
    target_agent_id = agents[0]["id"]

    # 2. Register task for agent
    task_payload = {
        "agent_id": target_agent_id,
        "name": "E2E Nightly Vulnerability Scan",
        "prompt": "Scan external dependencies for newly published CVEs.",
        "schedule_type": "interval",
        "schedule_expr": "3600",
    }
    create_res = client.post("/api/tasks", json=task_payload)
    assert create_res.status_code == 201
    task = create_res.json()
    task_id = task["id"]

    # 3. Trigger task immediately
    run_res = client.post(f"/api/tasks/{task_id}/run")
    assert run_res.status_code == 200
    run_data = run_res.json()
    assert run_data["status"] == "success"

    # 4. Verify task execution run logs
    logs_res = client.get("/api/tasks/runs/recent")
    assert logs_res.status_code == 200
    logs = logs_res.json()
    assert len(logs) >= 1
    assert logs[0]["status"] == "success"

    # 5. Clean up task
    del_res = client.delete(f"/api/tasks/{task_id}")
    assert del_res.status_code == 200


def test_e2e_06_rate_limiter_compliance(client: TestClient):
    """AC-01: Sliding window rate limit diagnostics and stability under burst."""
    rate_limiter.reset()

    # Send rapid requests to system status endpoint
    for _ in range(5):
        res = client.get("/api/system/status")
        assert res.status_code == 200

    status = client.get("/api/system/status").json()
    rl = status["rate_limiter"]
    assert rl["max_rpm"] == 14
    assert rl["remaining_slots"] <= 14
