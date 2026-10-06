"""adapter: wayward trace log (logs/wayward-trace.log, JSONL).

The proven always-on JSONL event stream (EXP-026 verified shipping
78,509 events in 24s). Events: iteration.start, task.claim,
backend.result (exit_code), gate.*, commit, failures. Deterministic
trace id per task (wayward:{task}).
"""

from __future__ import annotations

import json
from pathlib import Path

from canon import EventKind, Session, Span

DEFAULT_LOG = Path("logs/wayward-trace.log")  # relative to wayward repo root


def _discover() -> Path:
    """Resolve the live wayward trace log even when run from trace-miner."""
    if DEFAULT_LOG.exists():
        return DEFAULT_LOG
    for cand in (
        Path(r"E:\vibe_coding\dev\family\wayward\logs\wayward-trace.log"),
        Path.home() / "dev" / "family" / "wayward" / "logs" / "wayward-trace.log",
    ):
        if cand.exists():
            return cand
    return DEFAULT_LOG


def iter_sessions(log: Path | None = None, max_batches: int = 500) -> list[Session]:
    log = log or _discover()
    if not log.exists():
        return []
    by_task: dict[str, Session] = {}

    def sess_for(task: str, cwd: str = "") -> Session:
        return by_task.setdefault(task, Session(
            agent="wayward", session_id=task, cwd=cwd))

    with log.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(ev, dict):
                continue
            event = str(ev.get("event", ""))
            task = str(ev.get("task", ev.get("plan", "unassigned")))
            if not task or task.startswith("C:\\") or "pytest" in task:
                task = "unassigned"
            sess = sess_for(task, str(ev.get("cwd", "")))
            seq = len(sess.spans) + 1
            kind = _kind_for(event)
            status, message = 1, ""
            exit_code = ev.get("exit_code")
            if event == "backend.result" and exit_code not in (0, None):
                status, message = 2, f"exit {exit_code}"
            sess.spans.append(Span(
                agent="wayward", session_id=task, kind=kind,
                ts=str(ev.get("ts", "")), name=event,
                status_code=status, message=message,
                task_id=task, seq=seq,
                attrs={k: str(v)[:300] for k, v in ev.items()
                       if k not in ("ts", "event", "task", "plan")}))
            if seq >= 5000:
                break
    return list(by_task.values())[:max_batches]


def _kind_for(event: str) -> EventKind:
    if event.startswith("gate"):
        return EventKind.GATE
    if event in ("backend.result", "tool.result"):
        return EventKind.TOOL_RESULT
    if event == "backend.start":
        return EventKind.TOOL_CALL
    if event == "iteration.start":
        return EventKind.ITERATION
    if event in ("task.claim", "loop.claim"):
        return EventKind.TASK_CLAIM
    if "fail" in event or "error" in event:
        return EventKind.FAILURE
    if "commit" in event:
        return EventKind.COMMIT
    if "timeout" in event:
        return EventKind.TIMEOUT
    return EventKind.ITERATION