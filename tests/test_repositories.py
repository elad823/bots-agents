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

from backend.core.database import DatabaseManager, init_database
from backend.repositories.agent_repository import AgentRepository
from backend.repositories.message_repository import MessageRepository
from backend.repositories.task_repository import TaskRepository


@pytest.mark.asyncio
async def test_agent_repository_crud() -> None:
    """Test full CRUD operations on the Agent repository."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        await init_database(db_path)
        mgr = DatabaseManager(db_path)
        repo = AgentRepository(mgr)

        # 1. List initial seeded agents
        agents = await repo.get_all()
        assert len(agents) >= 2
        supervisor = await repo.get_by_slug("supervisor")
        assert supervisor is not None
        assert supervisor["is_system_agent"] == 1

        # 2. Create dynamic agent
        created = await repo.create({
            "name": "SecOps Specialist",
            "slug": "secops_specialist",
            "role": "Security operations and vulnerability auditor",
            "system_prompt": "Audit code and infrastructure for vulnerabilities.",
            "model": "gemini-1.5-pro",
        })
        assert created["slug"] == "secops_specialist"
        assert created["status"] == "idle"

        # 3. Update status
        updated_status = await repo.update_status(created["id"], "running")
        assert updated_status is True
        fetched = await repo.get_by_id(created["id"])
        assert fetched["status"] == "running"

        # 4. Prevent deleting system agent
        cannot_delete_supervisor = await repo.delete(supervisor["id"])
        assert cannot_delete_supervisor is False

        # 5. Delete dynamic agent
        deleted = await repo.delete(created["id"])
        assert deleted is True
        assert await repo.get_by_id(created["id"]) is None

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.mark.asyncio
async def test_message_repository_history() -> None:
    """Test message persistence and retrieval by session."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        await init_database(db_path)
        mgr = DatabaseManager(db_path)
        repo = MessageRepository(mgr)

        session_id = "test-session-42"
        await repo.add_message(session_id, "user", "user", "What is the status of system?")
        await repo.add_message(session_id, "supervisor", "assistant", "All agents operational.")

        history = await repo.get_history(session_id)
        assert len(history) == 2
        assert history[0]["content"] == "What is the status of system?"
        assert history[1]["content"] == "All agents operational."

        sessions = await repo.get_all_sessions()
        assert session_id in sessions

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.mark.asyncio
async def test_task_repository_lifecycle() -> None:
    """Test task scheduling, execution run logging, and status tracking."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        await init_database(db_path)
        mgr = DatabaseManager(db_path)
        agent_repo = AgentRepository(mgr)
        task_repo = TaskRepository(mgr)

        # Get supervisor agent ID
        supervisor = await agent_repo.get_by_slug("supervisor")
        assert supervisor is not None

        # Create scheduled task
        task = await task_repo.create({
            "agent_id": supervisor["id"],
            "name": "Hourly Health Check",
            "prompt": "Check all registered agent health states.",
            "schedule_type": "interval",
            "schedule_expr": "3600",
            "is_active": 1,
        })
        assert task["name"] == "Hourly Health Check"
        assert task["agent_slug"] == "supervisor"

        # Start execution run
        run = await task_repo.start_run(task["id"], supervisor["id"], task["prompt"])
        assert run["status"] == "running"

        # Complete execution run
        success = await task_repo.complete_run(
            run["id"],
            status="success",
            output_result="All agents report 🟢 Idle.",
        )
        assert success is True

        # Verify recent runs
        runs = await task_repo.get_recent_runs()
        assert len(runs) >= 1
        assert runs[0]["output_result"] == "All agents report 🟢 Idle."
        assert runs[0]["status"] == "success"

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
