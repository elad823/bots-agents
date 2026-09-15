from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Literal

try:
    from pydantic import BaseModel, Field

    class TaskBase(BaseModel):
        agent_id: str
        name: str = Field(..., min_length=1, max_length=150)
        prompt: str = Field(..., min_length=1)
        schedule_type: Literal["cron", "interval", "one_shot"]
        schedule_expr: str = Field(..., description="Cron expression e.g. '0 9 * * *' or interval in seconds '300'")
        is_active: int = 1

    class TaskCreate(TaskBase):
        pass

    class TaskResponse(TaskBase):
        id: str
        agent_name: str | None = None
        agent_slug: str | None = None
        last_run_at: str | None = None
        next_run_at: str | None = None
        created_at: str | None = None
        updated_at: str | None = None

    class TaskRunResponse(BaseModel):
        id: str
        task_id: str
        agent_id: str
        status: Literal["running", "success", "failed"]
        input_prompt: str
        output_result: str | None = None
        error_message: str | None = None
        started_at: str | None = None
        completed_at: str | None = None

except ImportError:
    @dataclass
    class TaskBase:  # type: ignore
        agent_id: str
        name: str
        prompt: str
        schedule_type: str
        schedule_expr: str
        is_active: int = 1

        def model_dump(self) -> dict[str, Any]:
            return asdict(self)

    @dataclass
    class TaskCreate(TaskBase):
        pass

    @dataclass
    class TaskResponse(TaskBase):  # type: ignore
        id: str = ""
        agent_name: str | None = None
        agent_slug: str | None = None
        last_run_at: str | None = None
        next_run_at: str | None = None
        created_at: str | None = None
        updated_at: str | None = None

        def model_dump(self) -> dict[str, Any]:
            return asdict(self)

    @dataclass
    class TaskRunResponse:  # type: ignore
        id: str
        task_id: str
        agent_id: str
        status: str
        input_prompt: str
        output_result: str | None = None
        error_message: str | None = None
        started_at: str | None = None
        completed_at: str | None = None

        def model_dump(self) -> dict[str, Any]:
            return asdict(self)
