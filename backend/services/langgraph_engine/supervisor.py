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
        # 2. Check if there are active pending consultations
        consultation_stack = state.get("consultation_stack", [])
        if consultation_stack:
            next_target = consultation_stack[-1]["consulted"]
            logger.info("Supervisor yielding to pending consultation target: %s", next_target)
            state["next"] = next_target
            return state

        # 2.5 Check if last message was an inter-agent consultation reply returning to caller specialist
        last_msg = state["messages"][-1] if state.get("messages") else {}
        if (
            last_msg.get("role") == "assistant"
            and last_msg.get("sender_id") not in ("user", "supervisor")
            and last_msg.get("recipient_id") not in ("user", "supervisor", "all")
        ):
            caller_slug = last_msg.get("recipient_id")
            logger.info("Supervisor yielding to caller specialist after consultation reply: %s", caller_slug)
            state["next"] = caller_slug
            return state

        # 3. Check if worker has completed final output in this turn
        final_worker_responses = [
            m for m in state["messages"]
            if m.get("role") == "assistant"
            and m.get("sender_id") not in ("user", "supervisor")
            and m.get("recipient_id") in ("user", "supervisor", "all")
        ]

        if final_worker_responses:
            # Synthesize worker output and complete workflow
            latest_worker_msg = final_worker_responses[-1]
            worker_slug = latest_worker_msg.get("sender_id", "specialist")
            delegation_str = " ➔ ".join([c.replace("_", " ").title() for c in state.get("delegation_chain", [])])
            raw_worker_content = latest_worker_msg.get("content", "")
            worker_content_str = json.dumps(raw_worker_content, indent=2) if isinstance(raw_worker_content, (dict, list)) else str(raw_worker_content)
            synthesis_prompt = (
                f"You are the MAS Master Supervisor.\n"
                f"Specialist Collaboration Trail: {delegation_str}\n"
                f"Lead Specialist '{worker_slug.replace('_', ' ').title()}' Final Response:\n{worker_content_str}\n\n"
                f"Synthesize a clear, polished final response to the user summarizing the collaborative specialist results."
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

        # 4. New query routing logic
        all_agents = await agent_repository.get_all()
        active_workers = [a for a in all_agents if a["slug"] != "supervisor"]
        workers_summary = "\n".join(f"- {a['slug']}: {a['role']}" for a in active_workers)

        last_user_msg = next(
            (m["content"] for m in reversed(state["messages"]) if m.get("role") == "user"),
            "",
        )

        # Build conversation context for multi-turn awareness
        convo_snippets = []
        for m in state["messages"][-6:]:
            sender = m.get("sender_id") or m.get("role", "user")
            convo_snippets.append(f"{sender.capitalize()}: {m.get('content', '')}")
        conversation_context = "\n".join(convo_snippets)

        supervisor_system_prompt = (
            "You are the Master Supervisor of an Autonomous Multi-Agent System.\n"
            f"Active Registered Specialist Agents in Network:\n{workers_summary if workers_summary else 'None (Only Master Supervisor is currently active)'}\n\n"
            "Analyze the conversation and user request. You must decide on one of the following actions:\n"
            "1. DIRECT_ANSWER: Conversational greetings, clarifications, general synthesis, or explanations.\n"
            "2. DELEGATE: Route a domain-specific task to an existing registered specialist agent.\n"
            "3. SPAWN_AGENT or SPAWN_AGENTS: The user explicitly requests creating/registering new agent(s) (e.g. 'create agent architect', 'create the following agents: Architect, Designer, Programmer'), OR a new specialized domain capability is needed.\n"
            "   - If the user only asked to create/register the agent(s) without an immediate work task to execute, set 'task_delegated': false.\n"
            "   - If the user also gave a specific problem for the new agent to solve immediately, set 'task_delegated': true and specify 'target_agent'.\n"
            "4. REMOVE_AGENTS: The user explicitly requests or confirms removing, deleting, or clearing specialist agents.\n\n"
            "Respond in strictly valid JSON format with keys:\n"
            '{\n'
            '  "action": "DIRECT_ANSWER" | "DELEGATE" | "SPAWN_AGENT" | "SPAWN_AGENTS" | "REMOVE_AGENTS",\n'
            '  "target_agent": "<slug>",\n'
            '  "target_agents": ["all" or list of slugs],\n'
            '  "task_delegated": false,\n'
            '  "spawn_details": [\n'
            '    {"name": "Architect", "slug": "architect", "role": "System & Cloud Architect", "system_prompt": "..."},\n'
            '    {"name": "Designer", "slug": "designer", "role": "UI/UX & Solution Designer", "system_prompt": "..."}\n'
            '  ],\n'
            '  "scratchpad": "reasoning...",\n'
            '  "direct_answer": "..."\n'
            '}'
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

        # Parse decision
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

        elif action in ("SPAWN_AGENT", "SPAWN_AGENTS"):
            raw_details = decision.get("spawn_details") or decision
            items_to_spawn: list[dict[str, Any]] = []

            if isinstance(raw_details, list):
                for item in raw_details:
                    if isinstance(item, dict):
                        inner = item.get("spawn_details") if "spawn_details" in item and isinstance(item["spawn_details"], dict) else item
                        items_to_spawn.append(inner)
            elif isinstance(raw_details, dict):
                items_to_spawn.append(raw_details)
            elif isinstance(decision.get("name"), str):
                items_to_spawn.append(decision)

            created_agents = []
            for item in items_to_spawn:
                name = item.get("name") or "Specialist Agent"
                role = item.get("role") or "Domain specialist"
                sys_prompt = item.get("system_prompt") or f"You are an expert {role} in the Autonomous Multi-Agent System."
                slug = item.get("slug")

                new_agent = await agent_service.create_agent(
                    name=name,
                    role=role,
                    system_prompt=sys_prompt,
                    slug=slug,
                )
                created_agents.append(new_agent)
                logger.info("Supervisor dynamically registered agent: %s (%s)", new_agent["name"], new_agent["slug"])

            # Determine whether this was purely an administrative creation or a task delegation
            task_delegated = bool(decision.get("task_delegated", False))
            target_slug = decision.get("target_agent")

            user_msg_clean = last_user_msg.strip().lower()
            is_admin_create = any(
                user_msg_clean.startswith(prefix)
                for prefix in ("create ", "make ", "spawn ", "register ", "add ", "build ")
            ) and not any(
                kw in user_msg_clean
                for kw in ("and have ", "and ask ", "and design ", "and write ", "and build ", "and solve ", "and run ")
            )

            if not task_delegated or is_admin_create or not target_slug:
                names_summary = "\n".join(
                    f"- 🤖 **{a['name']}** (`{a['slug']}`): {a['role']}"
                    for a in created_agents
                )
                ans = (
                    f"✅ Successfully registered {len(created_agents)} specialist agent(s):\n"
                    f"{names_summary}\n\n"
                    f"All agents are active in the MAS network and ready for tasks or peer consultation."
                )
                state["latest_response"] = ans
                state["messages"].append({
                    "role": "assistant",
                    "sender_id": "supervisor",
                    "recipient_id": "user",
                    "content": ans,
                })
                state["next"] = "FINISH"
            else:
                target_agent = await agent_repository.get_by_slug(target_slug)
                if not target_agent and created_agents:
                    target_slug = created_agents[0]["slug"]
                state["supervisor_scratchpad"] = f"Spawned {len(created_agents)} agent(s). Delegating to {target_slug}."
                state["next"] = target_slug

        elif action == "DELEGATE":
            target_slug = decision.get("target_agent", "researcher")
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
    """Robustly extract JSON dictionary from LLM output, handling lists and code fences."""
    raw = raw_text.strip()

    # 1. Strip markdown code fences if present
    code_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    candidate_text = code_match.group(1).strip() if code_match else raw

    # 2. Try direct JSON parse on candidate text
    try:
        parsed = json.loads(candidate_text)
        if isinstance(parsed, list):
            return {"action": "SPAWN_AGENTS", "spawn_details": parsed}
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # 3. Search for JSON object {...}
    obj_match = re.search(r"\{[\s\S]*\}", raw)
    if obj_match:
        try:
            parsed = json.loads(obj_match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    # 4. Search for JSON array [...]
    list_match = re.search(r"\[[\s\S]*\]", raw)
    if list_match:
        try:
            parsed = json.loads(list_match.group(0))
            if isinstance(parsed, list):
                return {"action": "SPAWN_AGENTS", "spawn_details": parsed}
        except Exception:
            pass

    # Fallback to direct answer
    return {"action": "DIRECT_ANSWER", "direct_answer": raw_text}
