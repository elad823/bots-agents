from __future__ import annotations

import uuid
from typing import Any
from backend.core.database import db_manager, DatabaseManager


class TaskRepository:
    """Data access repository for scheduled tasks and task execution runs."""

    def __init__(self, manager: DatabaseManager | None = None) -> None:
        self.db = manager or db_manager

    async def get_all(self) -> list[dict[str, Any]]:
        """Return all scheduled tasks joined with agent details."""
        sql = """
        SELECT t.id, t.agent_id, t.name, t.prompt, t.schedule_type, t.schedule_expr,
               t.is_active, t.last_run_at, t.next_run_at, t.created_at, t.updated_at,
               a.name as agent_name, a.slug as agent_slug
        FROM tasks t
        LEFT JOIN agents a ON t.agent_id = a.id
        ORDER BY t.created_at DESC
        """
        return await self.db.fetch_all(sql)

    async def get_active_tasks(self) -> list[dict[str, Any]]:
        """Return all enabled scheduled tasks."""
        sql = """
        SELECT t.*, a.name as agent_name, a.slug as agent_slug
        FROM tasks t
        LEFT JOIN agents a ON t.agent_id = a.id
        WHERE t.is_active = 1
        """
        return await self.db.fetch_all(sql)

    async def get_by_id(self, task_id: str) -> dict[str, Any] | None:
        """Fetch task record by ID."""
        sql = """
        SELECT t.*, a.name as agent_name, a.slug as agent_slug
        FROM tasks t
        LEFT JOIN agents a ON t.agent_id = a.id
        WHERE t.id = ?
        """
        return await self.db.fetch_one(sql, (task_id,))

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new scheduled task."""
        task_id = data.get("id") or str(uuid.uuid4())
        agent_id = data["agent_id"]
        name = data["name"]
        prompt = data["prompt"]
        schedule_type = data["schedule_type"]
        schedule_expr = data["schedule_expr"]
        is_active = data.get("is_active", 1)

        sql = """
        INSERT INTO tasks (id, agent_id, name, prompt, schedule_type, schedule_expr, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        await self.db.execute(sql, (task_id, agent_id, name, prompt, schedule_type, schedule_expr, is_active))
        created = await self.get_by_id(task_id)
        if not created:
            raise RuntimeError(f"Failed to retrieve newly created task: {task_id}")
        return created

    async def update_run_timestamps(self, task_id: str, last_run: str, next_run: str | None = None) -> bool:
        """Update last and next execution timestamps for a task."""
        sql = "UPDATE tasks SET last_run_at = ?, next_run_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        affected = await self.db.execute(sql, (last_run, next_run, task_id))
        return affected > 0

    async def delete(self, task_id: str) -> bool:
        """Delete a task and its associated run records."""
        sql = "DELETE FROM tasks WHERE id = ?"
        affected = await self.db.execute(sql, (task_id,))
        return affected > 0

    async def start_run(self, task_id: str, agent_id: str, input_prompt: str) -> dict[str, Any]:
        """Record the initiation of an autonomous task run."""
        run_id = str(uuid.uuid4())
        sql = """
        INSERT INTO task_runs (id, task_id, agent_id, status, input_prompt)
        VALUES (?, ?, ?, 'running', ?)
        """
        await self.db.execute(sql, (run_id, task_id, agent_id, input_prompt))
        run = await self.db.fetch_one("SELECT * FROM task_runs WHERE id = ?", (run_id,))
        if not run:
            raise RuntimeError(f"Failed to retrieve newly started task run: {run_id}")
        return run

    async def complete_run(
        self,
        run_id: str,
        status: str,
        output_result: str | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Complete an autonomous task run record."""
        sql = """
        UPDATE task_runs
        SET status = ?, output_result = ?, error_message = ?, completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """
        affected = await self.db.execute(sql, (status, output_result, error_message, run_id))
        return affected > 0

    async def get_recent_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        """Fetch latest autonomous execution records with task and agent names."""
        sql = """
        SELECT r.id, r.task_id, r.agent_id, r.status, r.input_prompt, r.output_result,
               r.error_message, r.started_at, r.completed_at,
               t.name as task_name, a.name as agent_name, a.slug as agent_slug
        FROM task_runs r
        LEFT JOIN tasks t ON r.task_id = t.id
        LEFT JOIN agents a ON r.agent_id = a.id
        ORDER BY r.started_at DESC
        LIMIT ?
        """
        return await self.db.fetch_all(sql, (limit,))


task_repository = TaskRepository()
