"""adapter: zcode session store (~/.zcode/v2/*.json).

zcode persists bot/agent state + session files under ~/.zcode/v2. This
adapter mines the JSON state files (agents-state.json, bot-state.v2/v3,
telemetry-state.json) plus any session/workspace JSONL.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from canon import EventKind, Session, Span

DEFAULT_ROOT = Path.home() / ".zcode" / "v2"
INTERESTING = ("agents-state.json", "bot-state.v2.json", "bot-state.v3.json",
               "telemetry-state.json", "coding-plan-cache.json")


def iter_sessions(root: Path | None = None) -> list[Session]:
    root = root or DEFAULT_ROOT
    out: list[Session] = []
    if not root.exists():
        return out
    for fname in INTERESTING:
        f = root / fname
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append(_mine_json(fname, data))
    # JSONL sessions under workspace/session dirs if any
    for jsonl in root.rglob("*.jsonl"):
        if "session" in str(jsonl).lower():
            out.append(_mine_jsonl(jsonl))
    return [s for s in out if s.spans or s.session_id]


def _walk(obj: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Flatten nested JSON into dotted key -> leaf value pairs."""
    found: list[tuple[str, Any]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            kp = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (dict, list)):
                found.extend(_walk(v, kp))
            else:
                found.append((kp, v))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, (dict, list)):
                found.extend(_walk(v, f"{prefix}.{i}"))
            else:
                found.append((f"{prefix}.{i}", v))
    return found


def _mine_json(fname: str, data: Any) -> Session:
    sess = Session(agent="zcode", session_id=fname)
    seq = 0
    for key, value in _walk(data):
        seq += 1
        kind = EventKind.SESSION_START if seq == 1 else EventKind.ITERATION
        text = str(value)[:300]
        sess.spans.append(Span(
            agent="zcode", session_id=fname, kind=kind,
            ts="", name=f"{fname}.{key}",
            attrs={key: text}, seq=seq))
        if seq > 2000:
            break
    sess.metadata["source"] = fname
    return sess


def _mine_jsonl(path: Path) -> Session:
    sess = Session(agent="zcode", session_id=path.stem)
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
                seq = len(sess.spans) + 1
                sess.spans.append(Span(
                    agent="zcode", session_id=path.stem,
                    kind=EventKind.ITERATION, ts="", name=str(rec.get("type", "event")),
                    attrs={"data": json.dumps(rec)[:500]}, seq=seq))
    except OSError:
        pass
    sess.metadata["source"] = str(path)
    return sess