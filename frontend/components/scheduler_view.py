from __future__ import annotations

from typing import Any
import streamlit as st
try:
    from frontend.utils.api_client import api_client
except ImportError:
    from utils.api_client import api_client  # type: ignore



def render_scheduler_view() -> None:
    """Render autonomous background task management and execution run history."""
    st.header("⏱️ Autonomous Background Task Manager")
    st.caption("Schedule background cron jobs and interval triggers. Tasks execute autonomously without active browser sessions.")

    tab_tasks, tab_new, tab_runs = st.tabs(["📋 Active Schedules", "➕ New Scheduled Task", "📜 Execution History"])

    # Fetch agents for dropdowns
    agents = []
    try:
        agents = api_client.get_agents()
    except Exception:
        pass

    agent_lookup = {f"{a['name']} ({a['slug']})": a["id"] for a in agents}

    # Tab 1: Active Schedules
    with tab_tasks:
        st.subheader("Configured Background Tasks")
        try:
            tasks = api_client.get_tasks()
        except Exception as e:
            tasks = []
            st.error(f"Failed to load tasks: {e}")

        if not tasks:
            st.info("No background tasks configured yet. Create one in the 'New Scheduled Task' tab.")
        else:
            for task in tasks:
                t_id = task["id"]
                t_name = task["name"]
                t_agent = task.get("agent_name", "Unknown Agent")
                t_type = task["schedule_type"]
                t_expr = task["schedule_expr"]
                last_run = task.get("last_run_at") or "Never"

                with st.expander(f"📌 {t_name} — Target: **{t_agent}**", expanded=True):
                    col_info, col_act = st.columns([3, 1])
                    with col_info:
                        st.markdown(f"**Prompt:** *{task['prompt']}*")
                        st.caption(f"**Schedule:** `{t_type}` (`{t_expr}`) | **Last Run:** `{last_run}`")
                    with col_act:
                        if st.button("⚡ Trigger Now", key=f"run_{t_id}", use_container_width=True):
                            with st.spinner("Executing task out-of-band..."):
                                try:
                                    res = api_client.trigger_task(t_id)
                                    st.success(f"Execution complete! Run ID: `{res.get('run_id')[:8]}`")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Execution failed: {exc}")

                        if st.button("🗑️ Delete", key=f"del_{t_id}", use_container_width=True):
                            try:
                                api_client.delete_task(t_id)
                                st.success("Task deleted.")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Delete failed: {exc}")

    # Tab 2: New Scheduled Task Form
    with tab_new:
        st.subheader("Create Autonomous Scheduled Task")
        with st.form("create_task_form"):
            task_name = st.text_input("Task Title", placeholder="e.g. Daily Vulnerability Sweep")
            target_agent_choice = st.selectbox("Target Agent", options=list(agent_lookup.keys()))
            prompt = st.text_area(
                "Task Instructions / Prompt",
                placeholder="e.g. Audit all active endpoints and generate a system security health report.",
            )

            col_type, col_expr = st.columns(2)
            with col_type:
                sched_type = st.selectbox("Schedule Type", options=["interval", "cron"])
            with col_expr:
                if sched_type == "interval":
                    sched_expr = st.text_input("Interval (seconds)", value="300")
                else:
                    sched_expr = st.text_input("Cron Expression", value="0 9 * * *")

            submitted = st.form_submit_button("🚀 Register & Activate Task", use_container_width=True)

            if submitted:
                if not task_name or not prompt:
                    st.error("Title and prompt are required.")
                else:
                    agent_id = agent_lookup.get(target_agent_choice)
                    if not agent_id:
                        st.error("Invalid agent selected.")
                    else:
                        try:
                            api_client.create_task(
                                agent_id=agent_id,
                                name=task_name,
                                prompt=prompt,
                                schedule_type=sched_type,
                                schedule_expr=sched_expr,
                            )
                            st.success(f"Task '{task_name}' successfully created and registered with scheduler!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to create task: {e}")

    # Tab 3: Execution History
    with tab_runs:
        st.subheader("Autonomous Execution Run Logs")
        if st.button("🔄 Refresh Run Logs"):
            st.rerun()

        try:
            runs = api_client.get_recent_runs()
        except Exception as e:
            runs = []
            st.error(f"Failed to load run logs: {e}")

        if not runs:
            st.info("No autonomous executions recorded yet.")
        else:
            for r in runs:
                status = r["status"]
                icon = "🟢" if status == "success" else ("🟠" if status == "running" else "🔴")
                t_name = r.get("task_name") or "Direct Trigger"
                a_name = r.get("agent_name") or "Agent"
                started = r.get("started_at") or "Unknown"

                with st.expander(f"{icon} [{status.upper()}] {t_name} (Agent: {a_name}) — {started}"):
                    st.markdown(f"**Input Prompt:**\n*{r['input_prompt']}*")
                    if r.get("output_result"):
                        st.markdown("**Output Result:**")
                        st.markdown(r["output_result"])
                    if r.get("error_message"):
                        st.error(f"**Error:** {r['error_message']}")
                    st.caption(f"Run ID: `{r['id']}` | Completed: `{r.get('completed_at') or 'In progress'}`")
