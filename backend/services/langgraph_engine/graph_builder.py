from __future__ import annotations

import logging
from typing import Any
from backend.repositories.agent_repository import agent_repository
from backend.repositories.message_repository import message_repository
from backend.services.langgraph_engine.dynamic_worker import execute_worker_node
from backend.services.langgraph_engine.state import AgentState
from backend.services.langgraph_engine.supervisor import execute_supervisor_node

logger = logging.getLogger("mas.graph_builder")

# Check if langgraph is available
try:
    from langgraph.graph import StateGraph, END
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False


class MultiAgentGraphRunner:
    """Orchestrates multi-agent execution using LangGraph or resilient state machine."""

    def __init__(self) -> None:
        self.max_iterations = 10

    async def run(
        self,
        prompt: str,
        session_id: str,
        target_agent: str = "supervisor",
    ) -> AgentState:
        """Execute multi-agent workflow starting from target agent or supervisor."""
        # Load recent session history to maintain multi-turn context
        history = await message_repository.get_history(session_id, limit=8)
        formatted_messages: list[dict[str, Any]] = [
            {
                "role": m.get("role", "user"),
                "sender_id": m.get("sender_id", "user"),
                "recipient_id": m.get("recipient_id", "all"),
                "content": m.get("content", ""),
            }
            for m in history
        ]
        if not formatted_messages or formatted_messages[-1].get("content") != prompt:
            formatted_messages.append({
                "role": "user",
                "sender_id": "user",
                "recipient_id": target_agent,
                "content": prompt,
            })

        initial_state: AgentState = {
            "messages": formatted_messages,
            "next": target_agent,
            "session_id": session_id,
            "active_agent": target_agent,
            "delegation_chain": [],
            "supervisor_scratchpad": "",
            "latest_response": "",
            "error": None,
        }

        # If user explicitly directed query to a specific worker agent rather than supervisor
        if target_agent != "supervisor":
            worker_agent = await agent_repository.get_by_slug(target_agent)
            if worker_agent:
                # Directly execute the target specialist agent
                state = await execute_worker_node(target_agent, initial_state)
                state["next"] = "FINISH"
                return state

        # If LangGraph package is installed, we can compile dynamically
        if HAS_LANGGRAPH:
            try:
                return await self._run_langgraph(initial_state)
            except Exception as e:
                logger.warning("LangGraph execution encountered error (%s), falling back to native state runner.", e)

        # Resilient native State Machine execution
        return await self._run_state_machine(initial_state)

    async def _run_state_machine(self, state: AgentState) -> AgentState:
        """Native asynchronous state machine matching LangGraph transitions."""
        current_node = state.get("next") or "supervisor"
        if current_node == "FINISH" or (HAS_LANGGRAPH and current_node == END):
            current_node = "supervisor"
        iteration = 0

        while current_node != "FINISH" and iteration < self.max_iterations:
            iteration += 1
            logger.debug("State machine iteration %d: executing node '%s'", iteration, current_node)

            if current_node == "supervisor":
                state = await execute_supervisor_node(state)
                current_node = state.get("next", "FINISH")
            else:
                # Worker node execution
                worker_slug = current_node
                state = await execute_worker_node(worker_slug, state)
                current_node = state.get("next", "supervisor")

        if iteration >= self.max_iterations and current_node != "FINISH":
            logger.warning("Graph reached maximum iterations limit (%d). Terminating.", self.max_iterations)
            state["next"] = "FINISH"

        return state

    async def _run_langgraph(self, initial_state: AgentState) -> AgentState:
        """Compile and invoke a LangGraph StateGraph dynamically."""
        workflow = StateGraph(AgentState)

        # 1. Add Supervisor node
        workflow.add_node("supervisor", execute_supervisor_node)

        # 2. Add all registered worker nodes
        all_agents = await agent_repository.get_all()

        def _route_worker(s: AgentState) -> str:
            nxt = s.get("next", "supervisor")
            return END if nxt == "FINISH" else nxt

        for agent in all_agents:
            slug = agent["slug"]
            if slug != "supervisor":
                # Create closure for worker node
                async def _worker_node(s: AgentState, slug: str = slug) -> AgentState:
                    return await execute_worker_node(slug, s)
                workflow.add_node(slug, _worker_node)
                workflow.add_conditional_edges(slug, _route_worker)

        # 3. Conditional routing from supervisor
        def _route_next(s: AgentState) -> str:
            nxt = s.get("next", "FINISH")
            return END if nxt == "FINISH" else nxt

        workflow.add_conditional_edges("supervisor", _route_next)
        workflow.set_entry_point("supervisor")

        app = workflow.compile()
        result = await app.ainvoke(initial_state)
        nxt = result.get("next")
        if nxt and nxt != "FINISH" and (not HAS_LANGGRAPH or nxt != END):
            # Resiliently resume via state machine runner if more transitions remain
            return await self._run_state_machine(result)
        return result


multi_agent_runner = MultiAgentGraphRunner()
