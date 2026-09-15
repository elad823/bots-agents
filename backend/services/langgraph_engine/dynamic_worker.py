from __future__ import annotations

import logging
from typing import Any
from backend.core.llm_gateway import llm_gateway
from backend.repositories.agent_repository import agent_repository
from backend.services.langgraph_engine.state import AgentState

logger = logging.getLogger("mas.dynamic_worker")


async def execute_worker_node(agent_slug: str, state: AgentState) -> AgentState:
    """Executes a worker specialist agent, updating live status and state."""
    logger.info("Starting execution for worker: %s", agent_slug)

    # 1. Look up agent definition
    agent = await agent_repository.get_by_slug(agent_slug)
    if not agent:
        error_msg = f"Worker agent '{agent_slug}' not found in registry."
        logger.error(error_msg)
        state["error"] = error_msg
        state["next"] = "FINISH"
        return state

    # 2. Update status to 'running' (🟠) for live UI display
    await agent_repository.update_status(agent["id"], "running")
    state["active_agent"] = agent_slug
    if agent_slug not in state["delegation_chain"]:
        state["delegation_chain"].append(agent_slug)

    try:
        # 3. Extract user prompt & context
        last_user_message = next(
            (m["content"] for m in reversed(state["messages"]) if m.get("role") == "user"),
            "Execute your specialist task.",
        )

        worker_context = f"Task assigned by Supervisor:\n{last_user_message}\n"
        if state.get("supervisor_scratchpad"):
            worker_context += f"\nSupervisor Guidance:\n{state['supervisor_scratchpad']}\n"

        # 4. Generate response through resilient rate-limited gateway
        response_text = await llm_gateway.generate_response(
            prompt=worker_context,
            system_prompt=agent["system_prompt"],
            model_name=agent.get("model"),
            caller_id=agent_slug,
        )

        # 5. Append response to state messages
        state["messages"].append({
            "role": "assistant",
            "sender_id": agent_slug,
            "recipient_id": "supervisor",
            "content": response_text,
        })
        state["latest_response"] = response_text
        state["next"] = "supervisor"  # Return control to supervisor for synthesis

    except Exception as exc:
        logger.error("Error executing worker '%s': %s", agent_slug, exc)
        await agent_repository.update_status(agent["id"], "error")
        state["error"] = str(exc)
        state["next"] = "FINISH"
        raise
    finally:
        # Reset status to 'idle' (🟢)
        await agent_repository.update_status(agent["id"], "idle")

    return state
