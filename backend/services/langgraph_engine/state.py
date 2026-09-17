from __future__ import annotations

from typing import Any, Optional, Sequence, TypedDict


class AgentMessage(TypedDict):
    role: str  # "user", "assistant", "system", "tool"
    content: str
    sender_id: str
    recipient_id: str


class AgentState(TypedDict, total=False):
    messages: list[dict[str, Any]]
    next: str  # "FINISH" or worker slug (e.g. "researcher", "secops")
    session_id: str
    active_agent: str
    delegation_chain: list[str]
    supervisor_scratchpad: str
    latest_response: str
    error: Optional[str]
    consultation_stack: list[dict[str, str]]
