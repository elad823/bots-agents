from __future__ import annotations

import uuid
from typing import Any
from backend.core.database import db_manager, DatabaseManager


class AgentRepository:
    """Data access repository for agents table."""

    def __init__(self, manager: DatabaseManager | None = None) -> None:
        self.db = manager or db_manager

    async def get_all(self) -> list[dict[str, Any]]:
        """Return all registered agents ordered by system agent flag then name."""
        sql = """
        SELECT id, name, slug, role, system_prompt, model, status, is_system_agent,
               config_json, created_at, updated_at
        FROM agents
        ORDER BY is_system_agent DESC, name ASC
        """
        return await self.db.fetch_all(sql)

    async def get_by_id(self, agent_id: str) -> dict[str, Any] | None:
        """Fetch agent record by UUID."""
        sql = "SELECT * FROM agents WHERE id = ?"
        return await self.db.fetch_one(sql, (agent_id,))

    async def get_by_slug(self, slug: str) -> dict[str, Any] | None:
        """Fetch agent record by unique slug."""
        sql = "SELECT * FROM agents WHERE slug = ?"
        return await self.db.fetch_one(sql, (slug,))

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new agent in the registry."""
        agent_id = data.get("id") or str(uuid.uuid4())
        name = data["name"]
        slug = data["slug"].lower().strip()
        role = data["role"]
        system_prompt = data["system_prompt"]
        model = data.get("model", "gemini-1.5-flash")
        status = data.get("status", "idle")
        is_system_agent = data.get("is_system_agent", 0)
        config_json = data.get("config_json", "{}")

        sql = """
        INSERT INTO agents (id, name, slug, role, system_prompt, model, status, is_system_agent, config_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        await self.db.execute(
            sql,
            (agent_id, name, slug, role, system_prompt, model, status, is_system_agent, config_json),
        )
        created = await self.get_by_id(agent_id)
        if not created:
            raise RuntimeError(f"Failed to retrieve newly created agent: {agent_id}")
        return created

    async def update(self, agent_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        """Update fields of an agent."""
        existing = await self.get_by_id(agent_id)
        if not existing:
            return None

        allowed = {"name", "role", "system_prompt", "model", "status", "config_json"}
        filtered = {k: v for k, v in updates.items() if k in allowed and v is not None}
        if not filtered:
            return existing

        set_clause = ", ".join(f"{k} = ?" for k in filtered.keys())
        params = list(filtered.values())
        params.append(agent_id)

        sql = f"UPDATE agents SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        await self.db.execute(sql, tuple(params))
        return await self.get_by_id(agent_id)

    async def update_status(self, agent_id: str, status: str) -> bool:
        """Quick update of agent execution status (idle, running, error, cooling_down)."""
        sql = "UPDATE agents SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        affected = await self.db.execute(sql, (status, agent_id))
        return affected > 0

    async def update_status_by_slug(self, slug: str, status: str) -> bool:
        """Quick update of agent execution status by slug."""
        sql = "UPDATE agents SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE slug = ?"
        affected = await self.db.execute(sql, (status, slug))
        return affected > 0

    async def delete(self, agent_id: str) -> bool:
        """Delete an agent (system agents cannot be deleted)."""
        existing = await self.get_by_id(agent_id)
        if not existing or existing.get("is_system_agent") == 1:
            return False
        sql = "DELETE FROM agents WHERE id = ?"
        affected = await self.db.execute(sql, (agent_id,))
        return affected > 0


agent_repository = AgentRepository()
