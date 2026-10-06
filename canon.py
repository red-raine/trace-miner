"""canon — normalize heterogeneous agent sessions to one event schema.

Each adapter yields raw records; canon maps them onto the Task-Lifecycle
Event schema used by the whole family (see wayward EXP-029 + the TRACE
trajectory model). A session = an agent run; a trace = one task inside
it; events = claim -> iterate -> gate -> commit/timeout.

2026 backing: TRACE (arxiv 2602.21230) trajectory-aware evaluation and
davanstrien/agent-traces 3-table layout (sessions/events/content).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

AGENT_LABELS = {
    "claude": "claude",
    "opencode": "opencode",
    "zcode": "zcode",
    "codex": "codex",
    "freebuff": "freebuff",
    "codebuff": "codebuff",
    "wayward": "wayward",
    "mecha": "mecha",
    "pseudag": "pseudag",
    "tracefoundry": "tracefoundry",
    "nanoresearch": "nanoresearch",
}


class EventKind(str, Enum):
    SESSION_START = "session.start"
    TASK_CLAIM = "task.claim"
    ITERATION = "iteration"
    TOOL_CALL = "tool.call"
    TOOL_RESULT = "tool.result"
    GATE = "gate"
    COMMIT = "commit"
    TIMEOUT = "timeout"
    FAILURE = "failure"
    LLM_CALL = "llm.call"
    SESSION_END = "session.end"


@dataclass
class Span:
    """One normalized event with OTLP-friendly attributes."""

    agent: str
    session_id: str
    kind: EventKind
    ts: str
    name: str
    status_code: int = 1  # OTLP: 1=OK, 2=ERROR
    message: str = ""
    attrs: dict[str, Any] = field(default_factory=dict)
    # deterministic trace id sourcing (task-scoped when available)
    task_id: str = ""
    seq: int = 0

    @property
    def trace_key(self) -> str:
        return self.task_id or self.session_id


@dataclass
class Session:
    agent: str
    session_id: str
    cwd: str = ""
    model: str = ""
    started_at: str = ""
    ended_at: str = ""
    spans: list[Span] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def trace_id_for(agent: str, key: str) -> str:
    """Stable 32-hex trace id (Langfuse dedupes by trace_id+span_id)."""
    import hashlib

    return hashlib.sha256(f"{agent}:{key}".encode()).hexdigest()[:32].upper()


def span_id(agent: str, ts: str, kind: str, seq: int) -> str:
    import hashlib

    return hashlib.sha256(f"{agent}|{ts}|{kind}|{seq}".encode()).hexdigest()[:16].upper()