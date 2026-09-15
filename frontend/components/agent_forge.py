from __future__ import annotations

from typing import Any
import streamlit as st
try:
    from frontend.utils.api_client import api_client
except ImportError:
    from utils.api_client import api_client  # type: ignore



def render_agent_forge() -> None:
    """Render the Agent Forge interface for creating and managing custom agents."""
    st.header("🛠️ Agent Forge & Dynamic Spawner")
    st.caption("Inspect, create, and configure specialized agents. Custom agents immediately register in the supervisor routing network.")

    col_list, col_create = st.columns([1, 1], gap="large")

    with col_create:
        st.subheader("Spawn Custom Specialist")
        with st.form("create_agent_form"):
            agent_name = st.text_input("Agent Display Name", placeholder="e.g. Database Optimizer")
            agent_slug = st.text_input("Slug (optional)", placeholder="e.g. db_optimizer (auto-generated if empty)")
            agent_role = st.text_input("Role & Core Capability", placeholder="e.g. SQLite performance tuning and indexing expert")
            system_prompt = st.text_area(
                "System Prompt (Persona & Instructions)",
                height=180,
                placeholder=(
                    "You are a specialized Database Performance Engineer. "
                    "Analyze slow queries, recommend optimal index strategies, "
                    "and review schema designs for high-throughput concurrency."
                ),
            )

            submitted = st.form_submit_button("🔨 Forge & Register Agent", use_container_width=True)

            if submitted:
                if not agent_name or not agent_role or not system_prompt:
                    st.error("Name, role, and system prompt are required.")
                else:
                    try:
                        new_agent = api_client.create_agent(
                            name=agent_name,
                            role=agent_role,
                            system_prompt=system_prompt,
                            slug=agent_slug if agent_slug else None,
                        )
                        st.success(f"Agent '{new_agent['name']}' forged and added to LangGraph network!")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed to create agent: {exc}")

    with col_list:
        st.subheader("Active Agent Registry")
        agents = []
        try:
            agents = api_client.get_agents()
        except Exception as e:
            st.error(f"Failed to load agents: {e}")

        for agent in agents:
            is_sys = agent.get("is_system_agent", 0) == 1
            badge = "🔒 Master System" if is_sys else "⚡ Dynamic Specialist"

            with st.expander(f"🤖 {agent['name']} ({badge})", expanded=not is_sys):
                st.markdown(f"**Role:** {agent.get('role', 'N/A')}")
                st.caption(f"**Slug:** `{agent['slug']}` | **Model:** `{agent.get('model', 'gemini-1.5-flash')}`")
                st.caption(f"**Status:** `{agent.get('status', 'idle')}`")
                st.text_area("System Prompt", value=agent.get("system_prompt", ""), height=100, disabled=True, key=f"sp_{agent['id']}")

                if not is_sys:
                    if st.button("🗑️ Delete Agent", key=f"del_agent_{agent['id']}", use_container_width=True):
                        try:
                            api_client.delete_agent(agent["id"])
                            st.success(f"Agent '{agent['name']}' deleted.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Delete failed: {e}")
