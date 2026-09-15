from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Literal

try:
    from pydantic import BaseModel, Field

    class MessageBase(BaseModel):
        session_id: str
        sender_id: str
        recipient_id: str = "all"
        role: Literal["user", "assistant", "system", "tool"]
        content: str
        metadata_json: str = "{}"

    class MessageCreate(MessageBase):
        pass

    class MessageResponse(MessageBase):
        id: str
        created_at: str | None = None

    class ChatRequest(BaseModel):
        prompt: str = Field(..., min_length=1)
        session_id: str | None = None
        target_agent: str = "supervisor"  # "supervisor" or specific agent slug

    class ChatResponse(BaseModel):
        response: str
        session_id: str
        agent_slug: str
        delegation_chain: list[str] = []
        created_at: str | None = None

except ImportError:
    @dataclass
    class MessageBase:  # type: ignore
        session_id: str
        sender_id: str
        role: str
        content: str
        recipient_id: str = "all"
        metadata_json: str = "{}"

        def model_dump(self) -> dict[str, Any]:
            return asdict(self)

    @dataclass
    class MessageCreate(MessageBase):
        pass

    @dataclass
    class MessageResponse(MessageBase):  # type: ignore
        id: str = ""
        created_at: str | None = None

        def model_dump(self) -> dict[str, Any]:
            return asdict(self)

    @dataclass
    class ChatRequest:  # type: ignore
        prompt: str
        session_id: str | None = None
        target_agent: str = "supervisor"

        def model_dump(self) -> dict[str, Any]:
            return asdict(self)

    @dataclass
    class ChatResponse:  # type: ignore
        response: str
        session_id: str
        agent_slug: str
        delegation_chain: list[str] = None  # type: ignore
        created_at: str | None = None

        def __post_init__(self) -> None:
            if self.delegation_chain is None:
                self.delegation_chain = []

        def model_dump(self) -> dict[str, Any]:
            return asdict(self)
