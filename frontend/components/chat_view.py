from __future__ import annotations

from typing import Any
import uuid
import streamlit as st
try:
    from frontend.utils.api_client import api_client
except ImportError:
    from utils.api_client import api_client  # type: ignore



def render_chat_view(target_agent_slug: str) -> None:
    """Render the multi-agent chat interface with history and delegation breadcrumbs."""
    st.header(f"💬 Chat Console — Target: `{target_agent_slug.upper()}`")
    st.caption("Interact with the autonomous agent network. The Supervisor dynamically coordinates and synthesizes specialists.")

    # Initialize session state for active session ID
    if "session_id" not in st.session_state:
        st.session_state["session_id"] = str(uuid.uuid4())

    session_id = st.session_state["session_id"]

    # Session controls
    col_sess, col_new = st.columns([4, 1])
    with col_sess:
        st.caption(f"Session ID: `{session_id}`")
    with col_new:
        if st.button("➕ New Chat Session", use_container_width=True):
            st.session_state["session_id"] = str(uuid.uuid4())
            st.rerun()

    # Fetch and render conversation history from SQLite
    messages = []
    try:
        messages = api_client.get_chat_history(session_id)
    except Exception as exc:
        st.warning(f"Could not load conversation history: {exc}")

    chat_container = st.container()
    with chat_container:
        if not messages:
            st.info(
                "💡 **Try these prompts:**\n"
                "- *'Hello Supervisor, introduce yourself and list your active specialists.'*\n"
                "- *'Analyze the security vulnerabilities in JWT token authentication.'* (delegates to specialist)\n"
                "- *'I need an expert in Rust cryptography to audit this signature.'* (spawns new agent on the fly!)"
            )

        for msg in messages:
            role = msg.get("role", "user")
            sender = msg.get("sender_id", "unknown")
            content = msg.get("content", "")

            with st.chat_message(role):
                st.markdown(f"**[{sender.capitalize()}]**: {content}")

    # Chat input box
    if user_prompt := st.chat_input("Enter instructions or ask a question to the agent network..."):
        # Display user message immediately
        with chat_container:
            with st.chat_message("user"):
                st.markdown(f"**[User]**: {user_prompt}")

        # Send to API and await multi-agent graph resolution
        with chat_container:
            with st.chat_message("assistant"):
                with st.spinner(f"Agents are collaborating on your request..."):
                    try:
                        resp = api_client.send_chat(
                            prompt=user_prompt,
                            session_id=session_id,
                            target_agent=target_agent_slug,
                        )
                        response_text = resp.get("response", "No response generated.")
                        delegation_chain = resp.get("delegation_chain", [])

                        if delegation_chain:
                            chain_str = " ➔ ".join([c.capitalize() for c in delegation_chain])
                            st.info(f"🔗 **Delegation Trail:** {chain_str}", icon="🤖")

                        st.markdown(response_text)
                        st.rerun()

                    except Exception as err:
                        st.error(f"Error communicating with agent network: {err}", icon="❌")
