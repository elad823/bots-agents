from __future__ import annotations

import json
import uuid
from typing import Any
from backend.core.database import db_manager, DatabaseManager


class MessageRepository:
    """Data access repository for messages table."""

    def __init__(self, manager: DatabaseManager | None = None) -> None:
        self.db = manager or db_manager

    async def add_message(
        self,
        session_id: str,
        sender_id: str,
        role: str,
        content: str,
        recipient_id: str = "all",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a chat message or agent response."""
        msg_id = str(uuid.uuid4())
        metadata_json = json.dumps(metadata or {})

        # Ensure content is always a valid string for SQLite binding
        if not isinstance(content, str):
            if isinstance(content, (dict, list)):
                safe_content = json.dumps(content, indent=2)
            else:
                safe_content = str(content)
        else:
            safe_content = content

        sql = """
        INSERT INTO messages (id, session_id, sender_id, recipient_id, role, content, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        await self.db.execute(
            sql,
            (msg_id, session_id, sender_id, recipient_id, role, safe_content, metadata_json),
        )
        created = await self.db.fetch_one("SELECT * FROM messages WHERE id = ?", (msg_id,))
        if not created:
            raise RuntimeError(f"Failed to retrieve newly added message: {msg_id}")
        return created

    async def get_history(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Retrieve chronological message history for a given session."""
        sql = """
        SELECT id, session_id, sender_id, recipient_id, role, content, metadata_json, created_at
        FROM messages
        WHERE session_id = ?
        ORDER BY created_at ASC
        LIMIT ?
        """
        return await self.db.fetch_all(sql, (session_id, limit))

    async def get_all_sessions(self) -> list[str]:
        """Get distinct session IDs ordered by latest activity."""
        sql = """
        SELECT session_id, MAX(created_at) as last_activity
        FROM messages
        GROUP BY session_id
        ORDER BY last_activity DESC
        LIMIT 50
        """
        rows = await self.db.fetch_all(sql)
        return [r["session_id"] for r in rows]


message_repository = MessageRepository()
