"""adapter: Claude Code session store (~/.claude/projects/*/*.jsonl).

Format: NDJSON lines; each line has type (user/assistant/...), ts,
sessionId, cwd, plus data. 2026: HuggingFace natively supports these;
SemiAnalysis cc-traces prove real Claude Code session logs are used for
KV-cache + trajectory mining. This adapter mines the task lifecycle:
session bounds, tool calls/gestures, summaries.

Discovery: clauses */*.jsonl under ~/.claude/projects. Deterministic
trace id per session (stable across runs for idempotent re-ship).
"""

from __future__ import annotations

import json
from pathlib import Path

from canon import EventKind, Session, Span

DEFAULT_ROOT = Path.home() / ".claude" / "projects"


def _iso_to_ts(ts: str) -> str:
    return ts if ts else ""


def iter_sessions(root: Path | None = None) -> list[Session]:
    root = root or DEFAULT_ROOT
    sessions: list[Session] = []
    if not root.exists():
        return sessions
    for proj_dir in sorted(root.iterdir()):
        for jsonl in sorted(proj_dir.glob("*.jsonl")):
            sessions.append(_mine_file(jsonl))
    return [s for s in sessions if s.spans]


def _mine_file(path: Path) -> Session:
    session_ids: dict[str, Session] = {}
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
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
                sid = str(rec.get("sessionId", path.stem))
                sess = session_ids.setdefault(sid, Session(
                    agent="claude", session_id=sid,
                    cwd=str(rec.get("cwd", ""))))
                seq = len(sess.spans) + 1
                typ = str(rec.get("type", ""))
                ts = _iso_to_ts(str(rec.get("ts", "")))
                data = rec.get("data", {})
                if typ == "user":
                    sess.spans.append(Span(
                        agent="claude", session_id=sid, kind=EventKind.SESSION_START,
                        ts=ts or sess.started_at or "", name="user.message",
                        attrs={"type": typ, "cwd": sess.cwd}, seq=seq))
                elif typ == "assistant" or typ == "summary":
                    sess.spans.append(Span(
                        agent="claude", session_id=sid, kind=EventKind.ITERATION,
                        ts=ts, name="assistant.message",
                        attrs={"type": typ, "message_id": str(rec.get("messageId", ""))},
                        seq=seq))
                elif typ == "isSnapshotUpdate" or typ == "file-history-snapshot":
                    sess.spans.append(Span(
                        agent="claude", session_id=sid, kind=EventKind.TOOL_RESULT,
                        ts=ts, name="file.snapshot", seq=seq))
                elif ts:
                    # progress/hook/other event stream records
                    sess.spans.append(Span(
                        agent="claude", session_id=sid, kind=EventKind.TOOL_CALL,
                        ts=ts, name=typ,
                        attrs={"data": json.dumps(data)[:500]}, seq=seq))
    except OSError:
        pass

    # session bounds from span timestamps
    if not path.parent.exists():
        return Session(agent="claude", session_id=path.stem)
    if session_ids:
        for sess in session_ids.values():
            times = [sp.ts for sp in sess.spans if sp.ts]
            if times:
                sess.started_at, sess.ended_at = min(times), max(times)
            sess.metadata["source"] = str(path)
    return next(iter(session_ids.values()), Session(agent="claude", session_id=path.stem))