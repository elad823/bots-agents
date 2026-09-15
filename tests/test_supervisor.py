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
from backend.services.chat_service import ChatService
from backend.services.langgraph_engine.graph_builder import MultiAgentGraphRunner


@pytest.mark.asyncio
async def test_supervisor_direct_chat() -> None:
    """Test direct conversational interaction with the supervisor."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        await init_database(db_path)
        mgr = DatabaseManager(db_path)
        msg_repo = MessageRepository(mgr)
        chat = ChatService(msg_repo=msg_repo)

        result = await chat.send_message(
            prompt="Hello Supervisor, what is your primary function?",
            session_id="test-session-direct",
            target_agent="supervisor",
        )

        assert "Supervisor" in result["response"]
        assert result["session_id"] == "test-session-direct"

        # Verify messages stored in DB
        history = await msg_repo.get_history("test-session-direct")
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.mark.asyncio
async def test_supervisor_delegation_to_researcher() -> None:
    """Test supervisor delegating a research task to the researcher agent."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        await init_database(db_path)
        mgr = DatabaseManager(db_path)
        msg_repo = MessageRepository(mgr)
        chat = ChatService(msg_repo=msg_repo)

        result = await chat.send_message(
            prompt="Please analyze and research distributed consensus algorithms.",
            session_id="test-session-delegate",
            target_agent="supervisor",
        )

        assert len(result["response"]) > 0
        assert "researcher" in result["delegation_chain"]

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.mark.asyncio
async def test_dynamic_agent_spawning() -> None:
    """Test dynamic agent creation when user requests a new domain specialist."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        await init_database(db_path)
        mgr = DatabaseManager(db_path)
        agent_repo = AgentRepository(mgr)
        msg_repo = MessageRepository(mgr)
        chat = ChatService(msg_repo=msg_repo)

        # Prompt that triggers dynamic agent spawning
        result = await chat.send_message(
            prompt="I need an expert in Rust cryptography to audit this curve.",
            session_id="test-session-spawn",
            target_agent="supervisor",
        )

        assert len(result["response"]) > 0

        # Verify newly spawned agent exists in SQLite registry
        from backend.repositories.agent_repository import agent_repository as global_agent_repo
        all_agents = await global_agent_repo.get_all()
        slugs = [a["slug"] for a in all_agents]
        # An agent with 'rust' or 'cryptography' or 'specialist' should have been created
        has_new_agent = any("rust" in s or "crypto" in s or "specialist" in s for s in slugs)
        assert has_new_agent is True, f"Expected dynamically spawned agent in slugs: {slugs}"


    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
