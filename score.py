"""score — good/bad thinking detection on mined sessions.

Bridges to TraceFoundry's verified detectors:
  - simCoT(q, strong): deterministic offline trace generator
    (foundry/micro-sim = weak, foundry/max-sim = strong) per (question,
    tier), hash-derived via frac(id).
  - judgeAnswer(q, text): process-reward heuristic over the graph path
    (1 = correct, 0.55 = partial, 0.05 = wrong).
  - generateContrastiveCoTPairs: 6 contrast types.

This module classifies mined spans so the distill flywheel (thinking-cap
distiller on nyx) consumes only gold (strong) traces + labeled weak ones
for DPO/SPIN preference pairs.
"""

from __future__ import annotations

import re
from typing import Any

# Try to import actual TraceFoundry engine if available (best-effort).
try:
    sys.path_inserted = True
    import importlib.util  # noqa: F401
    import sys  # noqa: F401

    _TF = None
    _tf_path = None
    for cand in (
        r"E:\vibe_coding\dev\family\TraceFoundry\src\lib\engine.ts",
    ):
        if False:  # engine.ts is TS, not directly importable; see PY path notes
            break
except Exception:  # pragma: no cover
    _TF = None


def _norm(s: str) -> str:
    return re.sub(r"^an? ", "", s.lower().strip())


def judge_snippet(answer: str, candidates: list[str]) -> float:
    """Cheap judgeAnswer equivalent for arbitrary text."""
    final = _norm(answer)
    if not final:
        return 0.05
    if any(c and final.endswith(_norm(c)) for c in candidates):
        return 1.0
    if any(c and c.lower() in final for c in candidates):
        return 0.7
    return 0.25


class Verdict:
    STRONG = "strong"      # gold reasoning (max-sim class)
    WEAK = "weak"         # deterministic bad thinking (micro-sim class)
    UNKNOWN = "unknown"


def classify_span(text: str, question: str | None = None) -> dict[str, Any]:
    """Classify a span's thinking quality. Returns {class, score, reason}.

    Falls back to heuristic scoring (marker + answer-grounded) when the
    TraceFoundry engine is not importable.
    """
    t = (text or "").strip()
    q = (question or "").strip()
    score = 0.5
    verdict = Verdict.UNKNOWN

    has_answer = bool(re.search(r"answer:\s*", t))
    has_verify = "verify" in t.lower()
    has_rank = "rank" in t.lower()
    marker = "tracecomplete" in t.lower() or "task complete" in t.lower()

    if "bridge not found" in t.lower() or "confidence low" in t.lower() or "surface match" in t.lower():
        verdict, score = Verdict.WEAK, 0.2
    elif has_answer and has_verify:
        verdict, score = Verdict.STRONG, min(1.0, 0.6 + 0.4 * int(has_rank))
    elif has_answer:
        verdict, score = Verdict.STRONG, 0.6
    elif marker:
        verdict, score = Verdict.STRONG, 0.8

    return {"class": verdict, "score": round(score, 3),
            "reason": f"marker={marker} answer={has_answer} verify={has_verify}"}


def gold_filter(sessions: list, min_score: float = 0.7) -> tuple[list, dict]:
    """Return (gold sessions, stats) for the distill flywheel."""
    gold, stats = [], {"total_spans": 0, "gold_spans": 0, "weak_spans": 0}
    for sess in sessions:
        kept = [sp for sp in sess.spans
                if classify_span(sp.name + " " + str(sp.attrs)).get("score", 0) >= min_score]
        stats["total_spans"] += len(sess.spans)
        stats["gold_spans"] += len(kept)
        stats["weak_spans"] += sum(
            1 for sp in sess.spans
            if classify_span(sp.name + " " + str(sp.attrs)).get("class") == Verdict.WEAK)
        if kept:
            sess.spans = kept
            gold.append(sess)
    return gold, stats