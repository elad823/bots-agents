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
        delegation_chain = final_state.get("delegation_chain", [])

        # 4. Identify and persist all new assistant/consultation messages generated during this turn
        all_messages = final_state.get("messages", [])
        last_user_idx = -1
        for idx, m in enumerate(all_messages):
            if m.get("role") == "user" and m.get("content") == prompt:
                last_user_idx = idx

        new_assistant_messages = [
            m for m in all_messages[last_user_idx + 1:]
            if m.get("role") == "assistant"
        ] if last_user_idx != -1 else [
            m for m in all_messages if m.get("role") == "assistant"
        ]

        if new_assistant_messages:
            for m in new_assistant_messages:
                sender = m.get("sender_id", "supervisor")
                recipient = m.get("recipient_id", "user")
                content = m.get("content", "")
                if content:
                    await self.message_repo.add_message(
                        session_id=active_session,
                        sender_id=sender,
                        recipient_id=recipient,
                        role="assistant",
                        content=content,
                        metadata={"delegation_chain": delegation_chain},
                    )
            if not response_text:
                raw_resp = new_assistant_messages[-1].get("content", "")
                response_text = json.dumps(raw_resp, indent=2) if isinstance(raw_resp, (dict, list)) else str(raw_resp)
        else:
            if not response_text:
                response_text = "Task completed."
            await self.message_repo.add_message(
                session_id=active_session,
                sender_id=target_agent if target_agent != "supervisor" else "supervisor",
                recipient_id="user",
                role="assistant",
                content=response_text,
                metadata={"delegation_chain": delegation_chain},
            )

        final_response_str = json.dumps(response_text, indent=2) if isinstance(response_text, (dict, list)) else str(response_text)

        return {
            "response": final_response_str,
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
