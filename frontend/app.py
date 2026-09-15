import sys
from pathlib import Path

# Ensure workspace root is always at the head of sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

# Set Streamlit page configuration (wide layout, custom icon)
st.set_page_config(
    page_title="Grok MAS Control Plane",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

try:
    from frontend.components.sidebar import render_sidebar
    from frontend.components.chat_view import render_chat_view
    from frontend.components.scheduler_view import render_scheduler_view
    from frontend.components.agent_forge import render_agent_forge
    from frontend.utils.api_client import api_client
except ImportError:
    from components.sidebar import render_sidebar  # type: ignore
    from components.chat_view import render_chat_view  # type: ignore
    from components.scheduler_view import render_scheduler_view  # type: ignore
    from components.agent_forge import render_agent_forge  # type: ignore
    from utils.api_client import api_client  # type: ignore



def main() -> None:
    """Main application loop for the visual MAS control plane."""
    # Render sidebar and capture selected direct target agent
    target_agent_slug = render_sidebar()

    # Top-level tabs for clean navigation
    tab_chat, tab_scheduler, tab_forge, tab_diagnostics = st.tabs([
        "💬 Multi-Agent Chat",
        "⏱️ Task Scheduler",
        "🛠️ Agent Forge",
        "📊 System Diagnostics",
    ])

    with tab_chat:
        render_chat_view(target_agent_slug=target_agent_slug)

    with tab_scheduler:
        render_scheduler_view()

    with tab_forge:
        render_agent_forge()

    with tab_diagnostics:
        st.header("📊 System Health & Rate-Limiter Diagnostics")
        status = api_client.get_system_status()

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Backend Status", status.get("status", "unknown").upper())
            st.metric("Active Environment", status.get("environment", "unknown"))
        with col2:
            st.metric("Registered Agents", status.get("registered_agents_count", 0))
            st.metric("Scheduler Running", "YES" if status.get("scheduler_running") else "NO")
        with col3:
            rl = status.get("rate_limiter", {})
            st.metric("Gemini 15 RPM Window", f"{rl.get('current_window_requests', 0)} / {rl.get('max_rpm', 14)}")
            st.metric("Remaining RPM Slots", rl.get("remaining_slots", 14))

        st.subheader("Raw Status Envelope")
        st.json(status)


if __name__ == "__main__":
    main()
