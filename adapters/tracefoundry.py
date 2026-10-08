"""adapter: TraceFoundry trace store (~/.tracefoundry, MCP state).

TraceFoundry's harness persists traces in $TF_DATA_DIR (default ~/.tracefoundry)
per its mcp-server.mjs (mcp-state.json + trace export files). These are the
offline/contrastive CoT pairs the lab generates. This adapter also satisfies
the zcode "G2 span-tier handoff": spans map directly onto canon spans (the
TraceFoundry adapter consumes them losslessly).
"""

from __future__ import annotations

import json
from pathlib import Path

from canon import EventKind, Session, Span

DEFAULT_ROOT = Path.home() / ".tracefoundry"


def iter_sessions(root: Path | None = None) -> list[Session]:
    root = root or DEFAULT_ROOT
    out: list[Session] = []
    if not root.exists():
        return out
    # mcp-state.json (the harness's in-memory trace raft)
    state = root / "mcp-state.json"
    if state.exists():
        try:
            data = json.loads(state.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        traces = data.get("traces") or []
        if traces:
            sess = Session(agent="tracefoundry", session_id="mcp-state",
                           cwd=str(root), metadata={"source": "mcp-state.json"})
            for i, tr in enumerate(traces[:500]):
                if isinstance(tr, dict):
                    seq = len(sess.spans) + 1
                    verdict = str(tr.get("verdict", ""))
                    status = 2 if verdict in ("fail",) else 1
                    sess.spans.append(Span(
                        agent="tracefoundry", session_id="mcp-state",
                        kind=EventKind.ITERATION,
                        ts=str(tr.get("ts", "")), name=str(tr.get("id", f"trace-{seq}")),
                        status_code=status, message=verdict,
                        task_id=str(tr.get("question_id", "")),
                        seq=seq,
                        attrs={"score": str(tr.get("score", "")),
                               "model": str(tr.get("model", "")),
                               "data": json.dumps(tr)[:300]}))
            if sess.spans:
                out.append(sess)
    # g2-export JSONL files (tf_export / mined turns)
    for f in sorted(root.glob("*.jsonl")):
        out.append(_mine_jsonl(f))
    return out


def _mine_jsonl(path: Path) -> Session:
    sess = Session(agent="tracefoundry", session_id=path.stem, cwd=str(path.parent))
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
                seq = len(sess.spans) + 1
                verdict = str(rec.get("verdict", ""))
                status = 2 if verdict in ("fail", "escalated") else 1
                sess.spans.append(Span(
                    agent="tracefoundry", session_id=path.stem,
                    kind=EventKind.ITERATION, ts=str(rec.get("ts", "")),
                    name=str(rec.get("id", rec.get("name", f"row-{seq}"))),
                    status_code=status, message=verdict,
                    task_id=str(rec.get("question_id", rec.get("task_id", ""))),
                    seq=seq,
                    attrs={"score": str(rec.get("score", "")),
                           "model": str(rec.get("model", "")),
                           "data": json.dumps(rec)[:300]}))
                if seq >= 5000:
                    break
    except OSError:
        pass
    if not sess.spans:
        sess.metadata["skip"] = "no spans"
    return sess