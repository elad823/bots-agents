from __future__ import annotations

import asyncio
import os
import sqlite3
from pathlib import Path
from typing import Any, AsyncGenerator
import json
import uuid

from backend.core.config import settings

# Attempt import of aiosqlite, with clean fallback to threadpool sqlite3
try:
    import aiosqlite
    HAS_AIOSQLITE = True
except ImportError:
    HAS_AIOSQLITE = False

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- 1. Agents Registry
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT 'gemini-1.5-flash',
    status TEXT NOT NULL DEFAULT 'idle',
    is_system_agent INTEGER NOT NULL DEFAULT 0,
    config_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Chat & Message History
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    recipient_id TEXT DEFAULT 'all',
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Autonomous Scheduled Tasks
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    name TEXT NOT NULL,
    prompt TEXT NOT NULL,
    schedule_type TEXT NOT NULL,
    schedule_expr TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
);

-- 4. Autonomous Task Run Executions
CREATE TABLE IF NOT EXISTS task_runs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL,
    input_prompt TEXT NOT NULL,
    output_result TEXT,
    error_message TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_agents_slug ON agents(slug);
CREATE INDEX IF NOT EXISTS idx_tasks_agent ON tasks(agent_id);
CREATE INDEX IF NOT EXISTS idx_task_runs_task ON task_runs(task_id);
"""

DEFAULT_SUPERVISOR_PROMPT = """You are the Master Supervisor of the Autonomous Multi-Agent System.
Your job is to analyze user requests, understand their intent, and either:
1. Respond directly if the request is conversational, a direct synthesis, or within general scope.
2. Delegate the task to a specialized agent in your network if one already exists.
3. Dynamically spawn a new specialized agent using the create_agent tool if a required domain skill is missing, and then delegate to it.

Always be concise, structured, and strategic in your orchestration."""

DEFAULT_RESEARCHER_PROMPT = """You are a specialized Research and Information Specialist.
Your role is to deeply analyze topics, synthesize information, find insights, and present structured research summaries."""


def get_db_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Create a synchronous sqlite3 connection with Row factory and WAL mode."""
    target_path = db_path or settings.database_path
    if target_path != ":memory:":
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


async def init_database(db_path: str | None = None) -> None:
    """Initialize SQLite tables and default seed agents asynchronously."""
    target_path = db_path or settings.database_path
    
    def _sync_init() -> None:
        conn = get_db_connection(target_path)
        try:
            with conn:
                conn.executescript(SCHEMA_SQL)
                # Check if default supervisor exists
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM agents WHERE slug = 'supervisor'")
                if not cursor.fetchone():
                    supervisor_id = str(uuid.uuid4())
                    cursor.execute(
                        """
                        INSERT INTO agents (id, name, slug, role, system_prompt, model, status, is_system_agent)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            supervisor_id,
                            "Supervisor",
                            "supervisor",
                            "Master Coordinator & Router",
                            DEFAULT_SUPERVISOR_PROMPT,
                            settings.gemini_model_default,
                            "idle",
                            1
                        )
                    )
                # Seed default researcher specialist
                cursor.execute("SELECT id FROM agents WHERE slug = 'researcher'")
                if not cursor.fetchone():
                    researcher_id = str(uuid.uuid4())
                    cursor.execute(
                        """
                        INSERT INTO agents (id, name, slug, role, system_prompt, model, status, is_system_agent)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            researcher_id,
                            "Researcher",
                            "researcher",
                            "In-depth research and synthesis specialist",
                            DEFAULT_RESEARCHER_PROMPT,
                            settings.gemini_model_default,
                            "idle",
                            0
                        )
                    )
        finally:
            conn.close()

    await asyncio.to_thread(_sync_init)


class DatabaseManager:
    """Manages SQLite queries with non-blocking execution."""
    
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or settings.database_path

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        """Execute INSERT/UPDATE/DELETE query and return lastrowid or affected rows."""
        def _exec() -> int:
            conn = get_db_connection(self.db_path)
            try:
                with conn:
                    cursor = conn.cursor()
                    cursor.execute(sql, params)
                    return cursor.rowcount
            finally:
                conn.close()
        return await asyncio.to_thread(_exec)

    async def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        """Fetch single row as dictionary."""
        def _fetch() -> dict[str, Any] | None:
            conn = get_db_connection(self.db_path)
            try:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                row = cursor.fetchone()
                return dict(row) if row else None
            finally:
                conn.close()
        return await asyncio.to_thread(_fetch)

    async def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Fetch multiple rows as list of dictionaries."""
        def _fetch() -> list[dict[str, Any]]:
            conn = get_db_connection(self.db_path)
            try:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
        return await asyncio.to_thread(_fetch)


db_manager = DatabaseManager()
