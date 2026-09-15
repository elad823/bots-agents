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


@pytest.mark.asyncio
async def test_database_initialization_and_seeding() -> None:
    """Test that SQLite initializes tables and seeds supervisor and researcher."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        await init_database(db_path)
        mgr = DatabaseManager(db_path)

        # Verify agents table exists and has seeded agents
        agents = await mgr.fetch_all("SELECT id, slug, name, role, status FROM agents ORDER BY slug")
        assert len(agents) >= 2


        slugs = [a["slug"] for a in agents]
        assert "supervisor" in slugs
        assert "researcher" in slugs

        # Verify messages table exists
        await mgr.execute(
            "INSERT INTO messages (id, session_id, sender_id, role, content) VALUES (?, ?, ?, ?, ?)",
            ("msg-1", "session-123", "user", "user", "Hello Supervisor"),
        )
        msg = await mgr.fetch_one("SELECT * FROM messages WHERE id = ?", ("msg-1",))
        assert msg is not None
        assert msg["content"] == "Hello Supervisor"

        # Verify tasks table exists
        await mgr.execute(
            """
            INSERT INTO tasks (id, agent_id, name, prompt, schedule_type, schedule_expr, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("task-1", agents[0]["id"] if "id" in agents[0] else "agent-1", "Test Task", "Do something", "interval", "60", 1),
        )
        task = await mgr.fetch_one("SELECT * FROM tasks WHERE id = ?", ("task-1",))
        assert task is not None
        assert task["name"] == "Test Task"

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
