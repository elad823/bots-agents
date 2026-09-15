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
from backend.services.chat_service import ChatService
from backend.services.scheduler_service import AutonomousSchedulerService


@pytest.mark.asyncio
async def test_scheduler_manual_trigger() -> None:
    """Test manual out-of-band trigger of a scheduled task."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        await init_database(db_path)
        mgr = DatabaseManager(db_path)
        agent_repo = AgentRepository(mgr)
        task_repo = TaskRepository(mgr)
        msg_repo = MessageRepository(mgr)
        chat = ChatService(msg_repo=msg_repo)
        scheduler = AutonomousSchedulerService(task_repo=task_repo, agent_repo=agent_repo, chat=chat)


        supervisor = await agent_repo.get_by_slug("supervisor")
        assert supervisor is not None

        task = await task_repo.create({
            "agent_id": supervisor["id"],
            "name": "Periodic System Probe",
            "prompt": "Probe registered agents and report status.",
            "schedule_type": "interval",
            "schedule_expr": "60",
            "is_active": 1,
        })

        # Trigger task run
        run_res = await scheduler.trigger_now(task["id"])
        assert run_res["status"] == "success"
        assert len(run_res["output"]) > 0

        # Verify task run was recorded in DB
        runs = await task_repo.get_recent_runs()
        assert len(runs) >= 1
        assert runs[0]["task_id"] == task["id"]
        assert runs[0]["status"] == "success"

        # Verify task last_run_at was updated
        updated_task = await task_repo.get_by_id(task["id"])
        assert updated_task["last_run_at"] is not None

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.mark.asyncio
async def test_scheduler_lifecycle() -> None:
    """Test scheduler startup, scheduling, and graceful shutdown."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        await init_database(db_path)
        mgr = DatabaseManager(db_path)
        agent_repo = AgentRepository(mgr)
        task_repo = TaskRepository(mgr)
        scheduler = AutonomousSchedulerService(task_repo=task_repo, agent_repo=agent_repo)

        await scheduler.start()
        assert scheduler._is_running is True

        supervisor = await agent_repo.get_by_slug("supervisor")
        task = await task_repo.create({
            "agent_id": supervisor["id"],
            "name": "Ephemeral Task",
            "prompt": "Ephemeral check",
            "schedule_type": "interval",
            "schedule_expr": "300",
            "is_active": 1,
        })

        await scheduler.schedule_task(task)
        await scheduler.remove_task(task["id"])

        await scheduler.stop()
        assert scheduler._is_running is False

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
