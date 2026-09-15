from __future__ import annotations

import os
import tempfile
import asyncio

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
async def test_e2e_container_restart_persistence() -> None:
    """Simulates container stop and restart with persistent SQLite volume."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        # Phase 1: First container lifecycle
        await init_database(db_path)
        mgr_1 = DatabaseManager(db_path)
        agent_repo_1 = AgentRepository(mgr_1)
        msg_repo_1 = MessageRepository(mgr_1)
        task_repo_1 = TaskRepository(mgr_1)

        # 1. Create a specialized agent
        created_agent = await agent_repo_1.create({
            "name": "Cloud Security Specialist",
            "slug": "cloud_sec_spec",
            "role": "Cloud infrastructure security auditor",
            "system_prompt": "Audit AWS and GCP IAM roles and VPC configurations.",
            "model": "gemini-1.5-pro",
        })

        # 2. Add message to chat history
        session_id = "persistence-session-001"
        await msg_repo_1.add_message(session_id, "user", "user", "Audit the Cloud Run configuration.")
        await msg_repo_1.add_message(session_id, "cloud_sec_spec", "assistant", "VPC and IAM policies verified.")

        # 3. Schedule autonomous task
        task = await task_repo_1.create({
            "agent_id": created_agent["id"],
            "name": "Nightly IAM Sweep",
            "prompt": "Scan IAM policies for wildcard permissions.",
            "schedule_type": "interval",
            "schedule_expr": "86400",
            "is_active": 1,
        })

        # Phase 2: Simulate Container Stop / Restart
        del mgr_1, agent_repo_1, msg_repo_1, task_repo_1

        # Phase 3: New Container connects to the persistent SQLite volume
        mgr_2 = DatabaseManager(db_path)
        agent_repo_2 = AgentRepository(mgr_2)
        msg_repo_2 = MessageRepository(mgr_2)
        task_repo_2 = TaskRepository(mgr_2)

        # Verify agent survived container restart
        restored_agent = await agent_repo_2.get_by_slug("cloud_sec_spec")
        assert restored_agent is not None
        assert restored_agent["name"] == "Cloud Security Specialist"
        assert restored_agent["status"] == "idle"

        # Verify messages survived
        history = await msg_repo_2.get_history(session_id)
        assert len(history) == 2
        assert history[0]["content"] == "Audit the Cloud Run configuration."
        assert history[1]["content"] == "VPC and IAM policies verified."

        # Verify scheduled task survived
        restored_task = await task_repo_2.get_by_id(task["id"])
        assert restored_task is not None
        assert restored_task["name"] == "Nightly IAM Sweep"

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
