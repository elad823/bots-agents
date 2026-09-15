from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any, Callable, Dict
from backend.repositories.agent_repository import agent_repository, AgentRepository
from backend.repositories.task_repository import task_repository, TaskRepository
from backend.services.chat_service import chat_service, ChatService

logger = logging.getLogger("mas.scheduler")

# Check if apscheduler is available
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False


class AutonomousSchedulerService:
    """Manages autonomous recurring (cron & interval) agent background tasks."""

    def __init__(
        self,
        task_repo: TaskRepository | None = None,
        agent_repo: AgentRepository | None = None,
        chat: ChatService | None = None,
    ) -> None:
        self.task_repo = task_repo or task_repository
        self.agent_repo = agent_repo or agent_repository
        self.chat = chat or chat_service
        self._is_running = False
        self._asyncio_jobs: Dict[str, asyncio.Task[Any]] = {}

        if HAS_APSCHEDULER:
            self._scheduler: AsyncIOScheduler | None = AsyncIOScheduler()
        else:
            self._scheduler = None

    async def start(self) -> None:
        """Initialize and start background task scheduler."""
        if self._is_running:
            return

        self._is_running = True
        logger.info("Starting Autonomous Scheduler Service (APScheduler: %s)...", HAS_APSCHEDULER)

        if HAS_APSCHEDULER and self._scheduler:
            self._scheduler.start()

        # Load active tasks from SQLite and schedule them
        active_tasks = await self.task_repo.get_active_tasks()
        for task in active_tasks:
            await self.schedule_task(task)

    async def stop(self) -> None:
        """Stop scheduler and cancel all running background jobs."""
        self._is_running = False
        logger.info("Stopping Autonomous Scheduler Service...")

        if HAS_APSCHEDULER and self._scheduler:
            self._scheduler.shutdown(wait=False)

        # Cancel any asyncio native jobs
        for job_id, job in self._asyncio_jobs.items():
            job.cancel()
        self._asyncio_jobs.clear()

    async def schedule_task(self, task: dict[str, Any]) -> None:
        """Register a single task with the scheduler."""
        task_id = task["id"]
        schedule_type = task["schedule_type"]
        schedule_expr = task["schedule_expr"]

        logger.info("Scheduling task '%s' (%s, expr: %s)", task["name"], schedule_type, schedule_expr)

        if HAS_APSCHEDULER and self._scheduler:
            # Remove existing job if present
            if self._scheduler.get_job(task_id):
                self._scheduler.remove_job(task_id)

            if schedule_type == "cron":
                trigger = CronTrigger.from_crontab(schedule_expr)
            else:  # interval
                try:
                    secs = float(schedule_expr)
                except ValueError:
                    secs = 60.0
                trigger = IntervalTrigger(seconds=secs)

            self._scheduler.add_job(
                func=self.trigger_now,
                trigger=trigger,
                id=task_id,
                args=[task_id],
                replace_existing=True,
            )
        else:
            # Native asyncio fallback interval runner
            if task_id in self._asyncio_jobs:
                self._asyncio_jobs[task_id].cancel()

            try:
                interval_secs = float(schedule_expr) if schedule_type == "interval" else 60.0
            except ValueError:
                interval_secs = 60.0

            async def _interval_loop(tid: str = task_id, delay: float = interval_secs) -> None:
                while self._is_running:
                    await asyncio.sleep(delay)
                    try:
                        await self.trigger_now(tid)
                    except Exception as e:
                        logger.error("Error in scheduled task loop for '%s': %s", tid, e)

            self._asyncio_jobs[task_id] = asyncio.create_task(_interval_loop())

    async def remove_task(self, task_id: str) -> None:
        """Deregister a scheduled task from background execution."""
        if HAS_APSCHEDULER and self._scheduler:
            if self._scheduler.get_job(task_id):
                self._scheduler.remove_job(task_id)

        if task_id in self._asyncio_jobs:
            self._asyncio_jobs[task_id].cancel()
            del self._asyncio_jobs[task_id]

    async def trigger_now(self, task_id: str) -> dict[str, Any]:
        """Immediately execute an autonomous scheduled task out-of-band."""
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found.")

        agent_id = task["agent_id"]
        agent = await self.agent_repo.get_by_id(agent_id)
        if not agent:
            raise ValueError(f"Agent '{agent_id}' for task '{task['name']}' not found.")

        agent_slug = agent["slug"]
        logger.info("Executing autonomous task '%s' targeting agent '%s'", task["name"], agent_slug)

        # 1. Record task run as 'running'
        run_record = await self.task_repo.start_run(
            task_id=task_id,
            agent_id=agent_id,
            input_prompt=task["prompt"],
        )
        run_id = run_record["id"]

        now_iso = datetime.datetime.utcnow().isoformat()
        await self.task_repo.update_run_timestamps(task_id=task_id, last_run=now_iso)

        try:
            # 2. Invoke chat service targeting the specialist agent
            chat_result = await self.chat.send_message(
                prompt=task["prompt"],
                session_id=f"task-session-{task_id[:8]}",
                target_agent=agent_slug,
            )

            output_text = chat_result["response"]

            # 3. Mark task run as 'success'
            await self.task_repo.complete_run(
                run_id=run_id,
                status="success",
                output_result=output_text,
            )
            logger.info("Autonomous task '%s' completed successfully.", task["name"])

            return {
                "run_id": run_id,
                "status": "success",
                "output": output_text,
                "task_id": task_id,
            }

        except Exception as exc:
            logger.error("Autonomous task '%s' failed: %s", task["name"], exc)
            await self.task_repo.complete_run(
                run_id=run_id,
                status="failed",
                error_message=str(exc),
            )
            raise


scheduler_service = AutonomousSchedulerService()
