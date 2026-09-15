from __future__ import annotations

import uuid
from typing import Any
from backend.repositories.message_repository import message_repository, MessageRepository
from backend.services.langgraph_engine.graph_builder import multi_agent_runner, MultiAgentGraphRunner


class ChatService:
    """Orchestrates end-to-end multi-agent chat interactions."""

    def __init__(
        self,
        msg_repo: MessageRepository | None = None,
        runner: MultiAgentGraphRunner | None = None,
    ) -> None:
        self.message_repo = msg_repo or message_repository
        self.runner = runner or multi_agent_runner

    async def send_message(
        self,
        prompt: str,
        session_id: str | None = None,
        target_agent: str = "supervisor",
    ) -> dict[str, Any]:
        """Process incoming chat query and return synthesized response."""
        active_session = session_id or str(uuid.uuid4())

        # 1. Record incoming user message
        await self.message_repo.add_message(
            session_id=active_session,
            sender_id="user",
            recipient_id=target_agent,
            role="user",
            content=prompt,
        )

        # 2. Run multi-agent execution graph
        final_state = await self.runner.run(
            prompt=prompt,
            session_id=active_session,
            target_agent=target_agent,
        )

        # 3. Retrieve final response text
        response_text = final_state.get("latest_response", "")
        if not response_text and final_state.get("messages"):
            # Fallback to last assistant message
            for m in reversed(final_state["messages"]):
                if m.get("role") == "assistant":
                    response_text = m.get("content", "")
                    break

        delegation_chain = final_state.get("delegation_chain", [])

        # 4. Record assistant message in database
        await self.message_repo.add_message(
            session_id=active_session,
            sender_id=target_agent if target_agent != "supervisor" else "supervisor",
            recipient_id="user",
            role="assistant",
            content=response_text,
            metadata={"delegation_chain": delegation_chain},
        )

        return {
            "response": response_text,
            "session_id": active_session,
            "agent_slug": target_agent,
            "delegation_chain": delegation_chain,
        }

    async def get_history(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Retrieve conversation history for a session."""
        return await self.message_repo.get_history(session_id, limit)

    async def list_sessions(self) -> list[str]:
        """List active chat sessions."""
        return await self.message_repo.get_all_sessions()


chat_service = ChatService()
