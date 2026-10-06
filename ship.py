"""ship — transport canonical sessions to Langfuse v4 via OTLP/JSON.

Port of the proven wayward.trace_shipper transport (EXP-026 verified:
78,509 events in 24s, idempotent byte-offset resume, Langfuse dedupes by
(trace_id, span_id)). stdlib only.

Env (defaults read from ~/.langfuse-otlp.env if present):
    LANGFUSE_OTLP_URL    e.g. http://localhost:3002/api/public/otel/v1/traces
    LANGFUSE_PK          public key (basic-auth user)
    LANGFUSE_SK          secret key (basic-auth password)
"""

from __future__ import annotations

import base64
import datetime as _dt
import json
import os
import urllib.request
from pathlib import Path

from canon import Session, Span, span_id, trace_id_for

DEFAULT_ENV = Path.home() / ".langfuse-otlp.env"
BATCH_SIZE = 200
SPAN_DURATION_NS = 1_000_000  # point-span rendered as 1 microsecond

_ATTR_TYPES = ((bool, "boolValue"), (int, "intValue"), (float, "doubleValue"))


def _ts_to_nano(ts: str) -> int:
    try:
        dt = _dt.datetime.fromisoformat(ts)
    except ValueError:
        dt = _dt.datetime.now(_dt.UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.UTC)
    return int(dt.timestamp() * 1_000_000_000)


def _attr(key: str, value):
    otel_key = f"trace.{key}"
    for py_type, otel_field in _ATTR_TYPES:
        if py_type is bool and isinstance(value, bool):
            return {"key": otel_key, "value": {otel_field: str(value).lower()}}
        if py_type is int and isinstance(value, int) and not isinstance(value, bool):
            return {"key": otel_key, "value": {otel_field: str(value)}}
        if py_type is float and isinstance(value, float):
            return {"key": otel_key, "value": {otel_field: str(value)}}
    if isinstance(value, str):
        return {"key": otel_key, "value": {"stringValue": value}}
    return {"key": otel_key, "value": {"stringValue": json.dumps(value)}}


def build_span(sp: Span) -> dict:
    """Canonical Span -> one OTLP point-span."""
    start = _ts_to_nano(sp.ts)
    attrs = [_attr("agent", sp.agent), _attr("session", sp.session_id)]
    if sp.task_id:
        attrs.append(_attr("task", sp.task_id))
    for k, v in sp.attrs.items():
        attrs.append(_attr(k, v))
    span = {
        "traceId": trace_id_for(sp.agent, sp.trace_key),
        "spanId": span_id(sp.agent, sp.ts, sp.kind.value, sp.seq),
        "name": sp.name,
        "kind": 1,
        "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(start + SPAN_DURATION_NS),
        "attributes": attrs,
        "status": {"code": sp.status_code},
    }
    if sp.message:
        span["status"]["message"] = sp.message
    return span


def build_payload(session: Session, spans: list[dict]) -> dict:
    return {
        "resourceSpans": [{
            "resource": {"attributes": [
                {"key": "service.name", "value": {"stringValue": f"trace-miner-{session.agent}"}},
                {"key": "service.version", "value": {"stringValue": "trace-miner-0.1.0"}},
                {"key": "agent", "value": {"stringValue": session.agent}},
            ]},
            "scopeSpans": [{
                "scope": {"name": "trace-miner", "version": "1"},
                "spans": spans,
            }],
        }]
    }


def load_env() -> tuple[str, str, str]:
    url = os.environ.get("LANGFUSE_OTLP_URL", "")
    pk = os.environ.get("LANGFUSE_PK", "")
    sk = os.environ.get("LANGFUSE_SK", "")
    if DEFAULT_ENV.exists() and not (url and pk and sk):
        for line in DEFAULT_ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
        url = os.environ.get("LANGFUSE_OTLP_URL", url)
        pk = os.environ.get("LANGFUSE_PK", pk)
        sk = os.environ.get("LANGFUSE_SK", sk)
    if not (url and pk and sk):
        raise SystemExit("missing LANGFUSE_OTLP_URL/PK/SK (or create ~/.langfuse-otlp.env)")
    return url, pk, sk


def _post_http(url: str, auth: tuple[str, str], body: bytes) -> int:
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"})
    token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return int(resp.status)


def _post(url: str, auth: tuple[str, str], body: bytes) -> int:
    return _post_http(url, auth, body)


def ship_session(session: Session, url: str, auth: tuple[str, str],
                 post=None) -> int:
    """Ship one canonical session to Langfuse. Returns span count."""
    post_fn = post if post is not None else _post
    spans = [build_span(sp) for sp in session.spans]
    if not spans:
        return 0
    for i in range(0, len(spans), BATCH_SIZE):
        chunk = spans[i : i + BATCH_SIZE]
        status = post_fn(url, auth, json.dumps(build_payload(session, chunk)).encode())
        if status not in (200, 202):
            raise OSError(f"langfuse ingest returned {status}")
    return len(spans)


def audit_warn() -> str:
    """Honesty caveat referenced by EXP-029: ads/other vendors' text are
    not reliably separable from agent chatter. Structured fields only."""
    return "trace-miner: structured fields are mined; for freebuff/ads see wayward EXP-029 caveat."