"""adapter: Mecha-Sharness workspace trace.jsonl (per-workspace).

Mecha-Sharness already emits a JSONL trace per workspace via ml.tracer:
events like pattern_route, plus span w= weights, gates. `mecha doctor`
checks consistency. This adapter reads those JSONL files directly —
the lab's own science-lab tracing, so no wrapping needed.

Session id = workspace dir; trace id = hash of workspace + task/plan.
"""

from __future__ import annotations

import json
from pathlib import Path

from canon import EventKind, Session, Span

DEFAULT_ROOT = None  # caller passes repo root


def iter_sessions(repo_root: Path | None = None, workspaces: list[Path] | None = None) -> list[Session]:
    """Mine trace.jsonl under repo_root's workspaces (or explicit list)."""
    out: list[Session] = []
    if workspaces is None:
        workspaces = []
        if repo_root is not None:
            for ws in repo_root.rglob("trace.jsonl"):
                if "node_modules" not in str(ws):
                    workspaces.append(ws.parent)
    for ws in workspaces:
        trace = ws / "trace.jsonl"
        if not trace.exists():
            continue
        sess = _mine_workspace(ws, trace)
        if sess.spans:
            out.append(sess)
    return out


def _mine_workspace(ws: Path, trace: Path) -> Session:
    sess = Session(agent="mecha", session_id=ws.name, cwd=str(ws))
    with trace.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            seq = len(sess.spans) + 1
            name = str(rec.get("event", rec.get("name", "event")))
            weight = rec.get("w")
            task = str(rec.get("task_id", ""))
            spans_kind = EventKind.TOOL_CALL if "pattern_route" in name else EventKind.ITERATION
            sess.spans.append(Span(
                agent="mecha", session_id=ws.name, kind=spans_kind,
                ts=str(rec.get("ts", "")), name=name,
                task_id=task, seq=seq,
                attrs={"w": str(weight) if weight is not None else "",
                       "data": json.dumps(rec)[:500]}))
            if seq >= 5000:
                break
    sess.metadata["source"] = str(trace)
    return sess