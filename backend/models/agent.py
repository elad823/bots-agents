from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Literal

try:
    from pydantic import BaseModel, Field

    class AgentBase(BaseModel):
        name: str = Field(..., min_length=1, max_length=100)
        slug: str = Field(..., pattern=r"^[a-z0-9_]+$")
        role: str = Field(..., min_length=3, max_length=200)
        system_prompt: str = Field(..., min_length=10)
        model: str = Field(default="gemini-1.5-flash")
        config_json: str = Field(default="{}")

    class AgentCreate(AgentBase):
        pass

    class AgentUpdate(BaseModel):
        name: str | None = None
        role: str | None = None
        system_prompt: str | None = None
        status: Literal["idle", "running", "error", "cooling_down"] | None = None
        config_json: str | None = None

    class AgentResponse(AgentBase):
        id: str
        status: str = "idle"
        is_system_agent: int = 0
        created_at: str | None = None
        updated_at: str | None = None

except ImportError:
    @dataclass
    class AgentBase:  # type: ignore
        name: str
        slug: str
        role: str
        system_prompt: str
        model: str = "gemini-1.5-flash"
        config_json: str = "{}"

        def model_dump(self) -> dict[str, Any]:
            return asdict(self)

    @dataclass
    class AgentCreate(AgentBase):
        pass

    @dataclass
    class AgentUpdate:  # type: ignore
        name: str | None = None
        role: str | None = None
        system_prompt: str | None = None
        status: str | None = None
        config_json: str | None = None

        def model_dump(self, exclude_unset: bool = False) -> dict[str, Any]:
            d = asdict(self)
            return {k: v for k, v in d.items() if v is not None} if exclude_unset else d

    @dataclass
    class AgentResponse(AgentBase):  # type: ignore
        id: str = ""
        status: str = "idle"
        is_system_agent: int = 0
        created_at: str | None = None
        updated_at: str | None = None

        def model_dump(self) -> dict[str, Any]:
            return asdict(self)
