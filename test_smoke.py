"""trace-miner smoke tests (stdlib, no pytest dependency assumed).

Run:  python test_smoke.py
Verifies adapters can mine real stores + canon/ship/score units without
touching Langfuse (ship is mocked via injectable post).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from canon import EventKind, Session, Span, span_id, trace_id_for  # noqa: E402


def test_canon_ids():
    a = trace_id_for("claude", "sess-1")
    b = trace_id_for("claude", "sess-1")
    assert a == b and len(a) == 32
    assert len(span_id("claude", "2026-01-01T00:00:00", "iteration", 1)) == 16
    print("ok: canon deterministic ids")


def test_claude_adapter():
    root = Path.home() / ".claude" / "projects"
    from adapters.claude import iter_sessions

    if root.exists():
        sessions = iter_sessions(root)
        print(f"ok: claude adapter mined {len(sessions)} sessions")
    else:
        print("skip: no ~/.claude/projects")


def test_opencode_adapter():
    db = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
    from adapters.opencode import iter_sessions

    if db.exists():
        sessions = iter_sessions(db, limit_sessions=10)
        print(f"ok: opencode adapter mined {len(sessions)} sessions")
    else:
        print("skip: no opencode DB")


def test_wayward_adapter():
    from adapters.wayward import iter_sessions

    log = Path(r"E:\vibe_coding\dev\family\wayward\logs\wayward-trace.log")
    sessions = iter_sessions(log, max_batches=5)
    print(f"ok: wayward adapter mined {len(sessions)} sessions")
    if sessions:
        assert all(s.spans for s in sessions)
        failed = [s for s in sessions if any(sp.status_code == 2 for sp in s.spans)]
        print(f"    ({len(failed)} with ERROR spans)")
    else:
        print("    (no events mined)")

def test_ship_mocked():
    from ship import build_payload, build_span, ship_session

    sess = Session(agent="claude", session_id="s1")
    sess.spans = [Span(agent="claude", session_id="s1", kind=EventKind.ITERATION,
                       ts="2026-01-01T00:00:00+00:00", name="assistant.message",
                       attrs={"role": "assistant"}, seq=1)]
    sent = {}

    def fake_post(url, auth, body):
        sent["body"] = json.loads(body)
        sent["url"] = url
        return 200

    n = ship_session(sess, "http://x/otel", ("pk", "sk"), post=fake_post)
    assert n == 1
    assert sent["body"]["resourceSpans"][0]["resource"]["attributes"][0]["value"]["stringValue"] == "trace-miner-claude"
    span = sent["body"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert span["status"]["code"] == 1
    print("ok: ship_session produces valid OTLP payload (+mocked POST 200)")


def test_score():
    from score import classify_span, gold_filter

    strong = classify_span("<verify> path connects cue + target\nanswer: alpha")
    assert strong["class"] == "strong"
    weak = classify_span("<verify> committing on surface match - confidence low\nanswer: moon")
    assert weak["class"] == "weak"
    gold, stats = gold_filter([Session(agent="t", session_id="x", spans=[
        Span(agent="t", session_id="x", kind=EventKind.ITERATION, ts="", name="answer: ok", seq=1),
        Span(agent="t", session_id="x", kind=EventKind.ITERATION, ts="", name="confidence low", seq=2),
    ])], min_score=0.5)
    assert stats["gold_spans"] == 1 and stats["weak_spans"] == 1
    print("ok: score good/bad detector bridge")


def test_resolve_alias_detection():
    from resolve import ALIAS_RE

    assert ALIAS_RE.match("free-flash-pool")
    assert ALIAS_RE.match("wayward-minion")
    assert ALIAS_RE.match("coding-glm-5-free")
    assert ALIAS_RE.match("agnes-flash")
    assert not ALIAS_RE.match("google-gemini-3-6-flash")
    assert not ALIAS_RE.match("nyx-qwen25-1.5b")
    assert not ALIAS_RE.match("openai/gpt-oss-20b")
    # concrete model already → resolve returns (claimed, False)
    from canon import Session
    from resolve import resolve_session_model

    sess = Session(agent="t", session_id="x", model="google-gemini-3-6-flash")
    m, resolved = resolve_session_model(sess)
    assert m == "google-gemini-3-6-flash" and resolved is False
    print("ok: resolve alias detection (concrete stays, alias triggers lookup)")


def test_ship_carries_model():
    from ship import build_payload, build_span, ship_session

    sess = Session(agent="claude", session_id="s1", model="opencode/gpt-oss-20b")
    sess.spans = [Span(agent="claude", session_id="s1", kind=EventKind.ITERATION,
                       ts="2026-01-01T00:00:00+00:00", name="assistant.message",
                       attrs={"role": "assistant"}, seq=1)]
    sent = {}

    def fake_post(url, auth, body):
        sent["body"] = json.loads(body)
        return 200

    ship_session(sess, "http://x/otel", ("pk", "sk"), post=fake_post)
    span = sent["body"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    attrs = {a["key"]: a["value"] for a in span["attributes"]}
    assert attrs.get("trace.model", {}).get("stringValue") == "opencode/gpt-oss-20b"
    print("ok: ship carries resolved model attribute")


def main():
    tests = [test_canon_ids, test_claude_adapter, test_opencode_adapter,
             test_wayward_adapter, test_ship_mocked, test_score,
             test_resolve_alias_detection, test_ship_carries_model]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL: {t.__name__}: {exc}")
        except Exception as exc:
            failed += 1
            print(f"ERROR: {t.__name__}: {exc}")
    print(f"\n{'PASS' if failed == 0 else str(failed) + ' FAILURES'}")
    return failed


if __name__ == "__main__":
    raise SystemExit(main())