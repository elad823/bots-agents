from __future__ import annotations

import logging
import re
from typing import Any
from backend.core.config import settings
from backend.repositories.agent_repository import agent_repository, AgentRepository

logger = logging.getLogger("mas.agent_service")


class AgentService:
    """Business service for managing agent lifecycles and registry operations."""

    def __init__(self, repo: AgentRepository | None = None) -> None:
        self.repo = repo or agent_repository

    async def list_agents(self) -> list[dict[str, Any]]:
        """List all agents in the registry."""
        return await self.repo.get_all()

    async def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        """Get agent by ID or slug."""
        agent = await self.repo.get_by_id(agent_id)
        if not agent:
            agent = await self.repo.get_by_slug(agent_id)
        return agent

    async def create_agent(
        self,
        name: str,
        role: str,
        system_prompt: str,
        slug: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Create and register a new specialist agent."""
        chosen_model = model or settings.gemini_model_default
        if not slug:
            # Generate slug from name: lower, alphanumeric, underscores
            clean_slug = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip().lower()).strip("_")
            slug = clean_slug[:30]

        # If an agent with this slug already exists, reuse it rather than creating duplicates
        existing = await self.repo.get_by_slug(slug)
        if existing:
            logger.info("Agent with slug '%s' already exists. Reusing existing agent.", slug)
            return existing

        return await self.repo.create({
            "name": name,
            "slug": slug,
            "role": role,
            "system_prompt": system_prompt,
            "model": chosen_model,
            "status": "idle",
            "is_system_agent": 0,
        })

    async def update_status(self, agent_id: str, status: str) -> bool:
        """Update agent execution status."""
        return await self.repo.update_status(agent_id, status)

    async def delete_agent(self, agent_id: str) -> bool:
        """Delete dynamic agent (returns False if agent is a system agent)."""
        return await self.repo.delete(agent_id)


agent_service = AgentService()
