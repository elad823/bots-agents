from __future__ import annotations

from typing import Any
import streamlit as st
try:
    from frontend.utils.api_client import api_client
except ImportError:
    from utils.api_client import api_client  # type: ignore



def render_sidebar() -> str:
    """Render sidebar with live status indicators, quota meters, and target agent selector."""
    with st.sidebar:
        st.title("⚡ Grok MAS")
        st.caption("Autonomous Multi-Agent System Control Plane")

        # 1. System Health & Rate Limiter Gauge
        status_data = api_client.get_system_status()
        is_online = status_data.get("status") == "ok"

        st.subheader("System Status")
        if is_online:
            st.success("🟢 Backend Connected", icon="✅")
        else:
            st.error("🔴 Backend Disconnected", icon="⚠️")

        # Quota Monitor
        rl = status_data.get("rate_limiter", {})
        used_reqs = rl.get("current_window_requests", 0)
        max_rpm = rl.get("max_rpm", 14)
        remaining = rl.get("remaining_slots", 14)
        cooling_down = rl.get("is_cooling_down", False)

        st.metric(
            label="Gemini Quota (60s Window)",
            value=f"{used_reqs}/{max_rpm} RPM",
            delta=f"{remaining} slots free",
            delta_color="normal" if not cooling_down else "inverse",
        )
        st.progress(min(1.0, used_reqs / max_rpm))
        if cooling_down:
            st.warning("🟠 Rate-Limiter Backoff: Queuing requests...", icon="⏳")

        st.divider()

        # 2. Live Agent Registry
        st.subheader("Registered Agents")
        agents = []
        try:
            agents = api_client.get_agents()
        except Exception:
            pass

        if not agents:
            st.info("No agents found in registry.")
            return "supervisor"

        # Display agent status chips
        for agent in agents:
            name = agent["name"]
            slug = agent["slug"]
            status = agent.get("status", "idle")
            is_sys = agent.get("is_system_agent", 0) == 1

            if status == "running":
                icon = "🟠"
                status_text = "Running / Thinking"
            elif status == "error":
                icon = "🔴"
                status_text = "Error / Cooling"
            else:
                icon = "🟢"
                status_text = "Idle"

            sys_badge = " [Master]" if is_sys else ""
            with st.expander(f"{icon} {name}{sys_badge}", expanded=False):
                st.caption(f"**Slug:** `{slug}`")
                st.caption(f"**Status:** {status_text}")
                st.caption(f"**Role:** {agent.get('role', 'N/A')}")
                st.caption(f"**Model:** `{agent.get('model', 'gemini-1.5-flash')}`")

        st.divider()

        # 3. Target Agent Selector
        agent_options = {f"{a['name']} ({a['slug']})": a["slug"] for a in agents}
        default_idx = 0
        for i, a in enumerate(agents):
            if a["slug"] == "supervisor":
                default_idx = i
                break

        selected_label = st.selectbox(
            "Direct Query Target",
            options=list(agent_options.keys()),
            index=default_idx,
            help="Choose to speak with the Master Supervisor (auto-delegating) or directly with a specialist agent.",
        )
        selected_slug = agent_options.get(selected_label, "supervisor")

        if st.button("🔄 Refresh Agent States", use_container_width=True):
            st.rerun()

        return selected_slug
