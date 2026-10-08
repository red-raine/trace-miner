"""adapter: pseudag round/task logs (JSONL) + repair artifacts.

pseudag produces grammar-validated pseudocode-DAG IR with a deterministic
checker gate — its traces carry GROUND-TRUTH labels (green/red ASTs, not
LLM-judged). Sources:
  experiments/e1-checker-policy/tasks.jsonl        — trial logs
  experiments/corpus/pseudag-mutation.jsonl        — mutation corpus
  usage.json / masterplan metadata                — session state

This adapter mines the task/repair lifecycle into canonical spans.
"""

from __future__ import annotations

import json
from pathlib import Path

from canon import EventKind, Session, Span

DEFAULT_ROOT = Path(r"E:\vibe_coding\dev\family\pseudag")


def iter_sessions(root: Path | None = None) -> list[Session]:
    root = root or DEFAULT_ROOT
    out: list[Session] = []
    for rel in ("experiments/e1-checker-policy/tasks.jsonl",
                "experiments/corpus/pseudag-mutation.jsonl"):
        f = root / rel
        if not f.exists():
            continue
        sess = Session(agent="pseudag", session_id=f.stem, cwd=str(f.parent))
        try:
            with f.open("r", encoding="utf-8", errors="replace") as fh:
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
                    kind = EventKind.GATE
                    status, msg = 1, ""
                    text = json.dumps(rec, ensure_ascii=False)[:300]
                    mutation = str(rec.get("mutation", ""))
                    field = str(rec.get("field", ""))
                    ground_truth = "mutant" if mutation else "clean"
                    if mutation or field:
                        status, msg = 2, f"ground-truth {mutation or field}"
                    sess.spans.append(Span(
                        agent="pseudag", session_id=f.stem, kind=kind,
                        ts=str(rec.get("ts", "")), name=rec.get("id", f"row-{seq}"),
                        status_code=status, message=msg,
                        task_id=str(rec.get("id", "")),
                        seq=seq,
                        attrs={"ground_truth": ground_truth,
                               "mutation": mutation, "data": text}))
                    if seq >= 5000:
                        break
        except OSError:
            pass
        if sess.spans:
            out.append(sess)
    return out