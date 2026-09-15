from __future__ import annotations

import json
import logging
import re
from typing import Any
from backend.core.llm_gateway import llm_gateway
from backend.repositories.agent_repository import agent_repository
from backend.services.agent_service import agent_service
from backend.services.langgraph_engine.state import AgentState

logger = logging.getLogger("mas.supervisor")


async def execute_supervisor_node(state: AgentState) -> AgentState:
    """Supervisor execution node: inspects state, dynamically spawns agents, or routes."""
    logger.info("Starting Supervisor node execution. Delegation chain: %s", state.get("delegation_chain", []))

    # 1. Update supervisor status to running
    await agent_repository.update_status_by_slug("supervisor", "running")
    state["active_agent"] = "supervisor"

    try:
        # 2. Check if a worker has already executed in this turn
        worker_responses = [
            m for m in state["messages"]
            if m.get("role") == "assistant" and m.get("sender_id") not in ("user", "supervisor")
        ]

        if worker_responses:
            # We already have worker output. Synthesize and complete workflow.
            latest_worker_msg = worker_responses[-1]
            worker_slug = latest_worker_msg.get("sender_id", "specialist")
            synthesis_prompt = (
                f"You are the MAS Supervisor. A specialist agent ('{worker_slug}') completed their task:\n"
                f"Specialist Report:\n{latest_worker_msg['content']}\n\n"
                f"Synthesize a clear, concise final response to the user summarizing the result."
            )

            final_response = await llm_gateway.generate_response(
                prompt=synthesis_prompt,
                caller_id="supervisor",
            )

            state["latest_response"] = final_response
            state["messages"].append({
                "role": "assistant",
                "sender_id": "supervisor",
                "recipient_id": "user",
                "content": final_response,
            })
            state["next"] = "FINISH"
            return state

        # 3. New query routing logic
        all_agents = await agent_repository.get_all()
        active_workers = [a for a in all_agents if a["slug"] != "supervisor"]
        workers_summary = "\n".join(f"- {a['slug']}: {a['role']}" for a in active_workers)

        last_user_msg = next(
            (m["content"] for m in reversed(state["messages"]) if m.get("role") == "user"),
            "",
        )

        # 3. Build conversation context for multi-turn awareness
        convo_snippets = []
        for m in state["messages"][-6:]:
            sender = m.get("sender_id") or m.get("role", "user")
            convo_snippets.append(f"{sender.capitalize()}: {m.get('content', '')}")
        conversation_context = "\n".join(convo_snippets)

        supervisor_system_prompt = (
            "You are the Master Supervisor of an Autonomous Multi-Agent System.\n"
            f"Active Registered Specialist Agents:\n{workers_summary if workers_summary else 'None (Only Master Supervisor is currently active)'}\n\n"
            "Analyze the conversation and user request. You must decide whether to:\n"
            "1. DIRECT_ANSWER: You can answer directly if conversational, administrative, clarification, or general synthesis.\n"
            "2. DELEGATE: Route to an existing registered specialist agent.\n"
            "3. SPAWN_AGENT: A specialized domain capability is needed but missing from registered agents. Create a new specialist!\n"
            "4. REMOVE_AGENTS: The user explicitly requests or confirms removing, deleting, or clearing specialist agents.\n\n"
            "Respond in strictly valid JSON format with keys:\n"
            '{"action": "DIRECT_ANSWER"|"DELEGATE"|"SPAWN_AGENT"|"REMOVE_AGENTS", '
            '"target_agent": "<slug>", "target_agents": ["all" or list of slugs], '
            '"spawn_details": {"name": "...", "slug": "...", "role": "...", "system_prompt": "..."}, '
            '"scratchpad": "reasoning...", "direct_answer": "..."}'
        )

        supervisor_prompt = (
            f"Conversation History:\n{conversation_context}\n\n"
            f"Latest User Request: {last_user_msg}"
        )

        decision_raw = await llm_gateway.generate_response(
            prompt=supervisor_prompt,
            system_prompt=supervisor_system_prompt,
            caller_id="supervisor",
        )

        # 4. Parse decision
        decision = _parse_supervisor_json(decision_raw)
        action = decision.get("action", "DIRECT_ANSWER")

        if action == "REMOVE_AGENTS":
            all_current = await agent_repository.get_all()
            target_slugs = decision.get("target_agents") or [decision.get("target_agent", "all")]
            deleted = []
            for ag in all_current:
                if ag.get("is_system_agent") == 1:
                    continue
                if "all" in target_slugs or ag["slug"] in target_slugs:
                    await agent_repository.delete(ag["id"])
                    deleted.append(ag["name"])

            if deleted:
                ans = f"✅ Successfully removed {len(deleted)} specialist agent(s): {', '.join(deleted)}. Only the Master Supervisor remains active."
            else:
                ans = "No specialist agents were found to remove. Only the Master Supervisor remains active."

            state["latest_response"] = ans
            state["messages"].append({
                "role": "assistant",
                "sender_id": "supervisor",
                "recipient_id": "user",
                "content": ans,
            })
            state["next"] = "FINISH"

        elif action == "SPAWN_AGENT":
            spawn_info = decision.get("spawn_details") or decision
            name = spawn_info.get("name") or "Specialist Agent"
            role = spawn_info.get("role") or "Domain specialist"
            sys_prompt = spawn_info.get("system_prompt") or "You are a domain expert."
            slug = spawn_info.get("slug")

            # Persist newly spawned agent in SQLite
            new_agent = await agent_service.create_agent(
                name=name,
                role=role,
                system_prompt=sys_prompt,
                slug=slug,
            )
            target_slug = new_agent["slug"]
            logger.info("Supervisor dynamically spawned new agent: %s (%s)", name, target_slug)

            state["supervisor_scratchpad"] = f"Spawned '{name}' to address: {last_user_msg}"
            state["next"] = target_slug

        elif action == "DELEGATE":
            target_slug = decision.get("target_agent", "researcher")
            # Verify target agent exists
            target_agent = await agent_repository.get_by_slug(target_slug)
            if not target_agent and active_workers:
                target_slug = active_workers[0]["slug"]

            state["supervisor_scratchpad"] = decision.get("scratchpad", f"Delegating to {target_slug}")
            state["next"] = target_slug

        else:  # DIRECT_ANSWER
            ans = decision.get("direct_answer") or decision_raw
            state["latest_response"] = ans
            state["messages"].append({
                "role": "assistant",
                "sender_id": "supervisor",
                "recipient_id": "user",
                "content": ans,
            })
            state["next"] = "FINISH"

    except Exception as exc:
        logger.error("Supervisor execution failure: %s", exc)
        state["error"] = str(exc)
        state["latest_response"] = f"[Supervisor Error]: {exc}"
        state["next"] = "FINISH"
    finally:
        await agent_repository.update_status_by_slug("supervisor", "idle")

    return state


def _parse_supervisor_json(raw_text: str) -> dict[str, Any]:
    """Robustly extract JSON dictionary from LLM output."""
    try:
        # Try direct JSON parsing
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    # Extract first {...} block
    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Fallback to direct answer
    return {"action": "DIRECT_ANSWER", "direct_answer": raw_text}
