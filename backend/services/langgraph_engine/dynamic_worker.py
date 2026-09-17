from __future__ import annotations

import json
import logging
import re
from typing import Any
from backend.core.llm_gateway import llm_gateway
from backend.repositories.agent_repository import agent_repository
from backend.services.agent_service import agent_service
from backend.services.langgraph_engine.state import AgentState

logger = logging.getLogger("mas.dynamic_worker")


def _parse_worker_json(raw: str) -> dict[str, Any]:
    """Parse JSON action from worker LLM output with robust fallback."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception:
        pass

    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except Exception:
            pass

    return {"action": "FINISH", "response": raw}


def _is_same_domain(slug1: str, slug2: str) -> bool:
    """Determine if two agent slugs share the same domain/role to prevent duplicate self-consultation."""
    s1 = re.sub(r"_\d+$", "", slug1.lower().strip()).split("_")[0]
    s2 = re.sub(r"_\d+$", "", slug2.lower().strip()).split("_")[0]
    return s1 == s2


async def execute_worker_node(agent_slug: str, state: AgentState) -> AgentState:
    """Executes a worker specialist agent, supporting autonomous peer-to-peer consultation."""
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

    consultation_stack = state.setdefault("consultation_stack", [])

    try:
        # Case A: This agent was consulted by another agent
        if consultation_stack and consultation_stack[-1].get("consulted") == agent_slug:
            active_consultation = consultation_stack.pop()
            caller_slug = active_consultation["caller"]
            question = active_consultation["question"]

            logger.info("Worker '%s' answering consultation from '%s': %s", agent_slug, caller_slug, question[:60])
            consult_prompt = (
                f"You are {agent['name']} ({agent['role']}).\n"
                f"Peer specialist agent '{caller_slug.replace('_', ' ').title()}' has sent you a consultation request:\n"
                f"Question / Task:\n{question}\n\n"
                f"Provide your authoritative, specialized domain answer so '{caller_slug.replace('_', ' ').title()}' can incorporate it."
            )

            response_text = await llm_gateway.generate_response(
                prompt=consult_prompt,
                system_prompt=agent["system_prompt"],
                model_name=agent.get("model"),
                caller_id=agent_slug,
            )

            state["messages"].append({
                "role": "assistant",
                "sender_id": agent_slug,
                "recipient_id": caller_slug,
                "content": response_text,
            })

            # Return control to caller specialist
            state["next"] = caller_slug
            state["active_agent"] = caller_slug
            return state

        # Case B: Primary task execution or resuming after receiving peer consultation answer
        last_user_message = next(
            (m["content"] for m in reversed(state["messages"]) if m.get("role") == "user"),
            "Execute your specialist task.",
        )

        all_agents = await agent_repository.get_all()
        peers = [
            a for a in all_agents
            if a["slug"] != agent_slug
            and a["slug"] != "supervisor"
            and not _is_same_domain(a["slug"], agent_slug)
        ]
        peers_summary = "\n".join(f"- {a['slug']}: {a['role']}" for a in peers)

        # Collect peer feedback already received in this turn
        peer_replies = [
            m for m in state["messages"]
            if m.get("recipient_id") == agent_slug and m.get("sender_id") != "user"
        ]
        peer_context = ""
        if peer_replies:
            peer_context = "\n\nConsultation Responses Received from Peers:\n" + "\n".join(
                f"- From [{m.get('sender_id', 'peer').title()}]: {m.get('content')}"
                for m in peer_replies
            )

        worker_context = (
            f"You are {agent['name']} ({agent['role']}).\n"
            f"User Instruction:\n{last_user_message}\n"
            f"{peer_context}\n\n"
            f"Registered Peer Specialists in Network (different domains):\n{peers_summary if peers_summary else 'None'}\n\n"
            "CRITICAL OPERATIONAL RULES:\n"
            "- You are the SOLE and authoritative expert in your own domain. NEVER consult or spawn an agent of your own domain (e.g. an Architect must never consult or spawn an Architect; a Designer must never consult a Designer).\n"
            "- Choose FINISH when you have the information needed to deliver your expert response.\n"
            "- Choose CONSULT ONLY when you genuinely need input from a DIFFERENT registered specialist domain (e.g. Designer consulting Architect for system infrastructure; or if the user explicitly asked to consult another specialist).\n"
            "- Choose SPAWN_AND_CONSULT only if an entirely DIFFERENT domain role is required that is not yet in the network.\n\n"
            "Respond in strictly valid JSON format with keys:\n"
            '{"action": "FINISH"|"CONSULT"|"SPAWN_AND_CONSULT", '
            '"target_agent": "<peer_slug>", '
            '"spawn_details": {"name": "...", "slug": "...", "role": "...", "system_prompt": "..."}, '
            '"question": "<specific question to peer>", '
            '"response": "<your complete, final expert solution>"}'
        )

        raw_response = await llm_gateway.generate_response(
            prompt=worker_context,
            system_prompt=agent["system_prompt"],
            model_name=agent.get("model"),
            caller_id=agent_slug,
        )

        decision = _parse_worker_json(raw_response)
        action = decision.get("action", "FINISH")

        # Loop depth protection
        if len(state.get("delegation_chain", [])) >= 6:
            logger.warning("Delegation chain reached max depth for '%s'. Forcing FINISH.", agent_slug)
            action = "FINISH"

        if action == "SPAWN_AND_CONSULT":
            spawn_info = decision.get("spawn_details") or {}
            name = spawn_info.get("name") or "Specialist Agent"
            role = spawn_info.get("role") or "Domain specialist"
            sys_prompt = spawn_info.get("system_prompt") or "You are a domain expert."
            slug = spawn_info.get("slug")
            question = decision.get("question") or f"Please assist with: {last_user_message}"

            # Self-domain guard: prevent spawning same domain
            clean_slug = (slug or name).lower().replace(" ", "_")
            if _is_same_domain(clean_slug, agent_slug) or name.lower() in agent["name"].lower():
                logger.warning("Worker '%s' attempted to spawn peer in own domain ('%s'). Forcing FINISH.", agent_slug, name)
                action = "FINISH"
            else:
                new_peer = await agent_service.create_agent(
                    name=name,
                    role=role,
                    system_prompt=sys_prompt,
                    slug=slug,
                )
                target_slug = new_peer["slug"]
                logger.info("Worker '%s' dynamically spawned peer '%s' (%s)", agent_slug, name, target_slug)

                state["messages"].append({
                    "role": "assistant",
                    "sender_id": agent_slug,
                    "recipient_id": target_slug,
                    "content": question,
                })
                consultation_stack.append({
                    "caller": agent_slug,
                    "consulted": target_slug,
                    "question": question,
                })
                state["delegation_chain"].append(f"{agent_slug} ➔ {target_slug}")
                state["next"] = target_slug
                return state

        elif action == "CONSULT":
            target_slug = decision.get("target_agent", "")
            question = decision.get("question") or f"Please assist with: {last_user_message}"

            # Self-consultation guard
            if not target_slug or target_slug == agent_slug or _is_same_domain(target_slug, agent_slug):
                logger.warning("Worker '%s' attempted self/same-domain consultation on '%s'. Forcing FINISH.", agent_slug, target_slug)
                action = "FINISH"
            else:
                target_peer = await agent_repository.get_by_slug(target_slug)
                if target_peer:
                    logger.info("Worker '%s' consulting peer '%s'", agent_slug, target_slug)
                    state["messages"].append({
                        "role": "assistant",
                        "sender_id": agent_slug,
                        "recipient_id": target_slug,
                        "content": question,
                    })
                    consultation_stack.append({
                        "caller": agent_slug,
                        "consulted": target_slug,
                        "question": question,
                    })
                    state["delegation_chain"].append(f"{agent_slug} ➔ {target_slug}")
                    state["next"] = target_slug
                    return state
                else:
                    action = "FINISH"

        # FINISH (or fallback)
        final_answer = decision.get("response") or raw_response
        state["messages"].append({
            "role": "assistant",
            "sender_id": agent_slug,
            "recipient_id": "user",
            "content": final_answer,
        })
        state["latest_response"] = final_answer
        state["next"] = "supervisor"

    except Exception as exc:
        logger.error("Error executing worker '%s': %s", agent_slug, exc)
        await agent_repository.update_status(agent["id"], "error")
        state["error"] = str(exc)
        state["next"] = "FINISH"
        raise
    finally:
        await agent_repository.update_status(agent["id"], "idle")

    return state
