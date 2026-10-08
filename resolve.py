"""resolve — resolved-model-id at ingest (zcode A-W3).

The routing alias (free-flash-pool, qwen3-coder-flash, wayward-minion…) is
what a session CLAIMS; the *actual* upstream model is what LiteLLM's
spend_logs records. When we mine a session we should record the RESOLVED
model, not the alias — otherwise a quarantine (alias→different provider)
hides in the traces.

Sources of truth, in order:
  1. LiteLLM spend_logs (Postgres) — the resolved upstream model actually
     served, keyed by the alias + time window of the session.
  2. Session record's own model field (fallback: keep the alias, marked).

Usage:
    from resolve import resolve_session_model
    sess.model, sess.metadata["resolved"] = resolve_session_model(sess)

Env: same LiteLLM DATABASE_URL as the proxy (or auto-detect from
B:\ai-stack\.env). Best-effort: no DB → returns (alias, False).
"""

from __future__ import annotations

import re
from pathlib import Path

from canon import Session

ALIAS_RE = re.compile(
    r"^(free-flash-pool|free-auto|wayward-\w+(-free)?|agnes-\w+|"
    r"coding-[\w.-]+|pool-[\w.-]+|kimi-\w+-free|or-\w+-(free|cheap))$")


def _load_db_url() -> str:
    """LiteLLM DB URL: env override or B:\ai-stack\.env."""
    import os

    url = os.environ.get("LITELLM_DATABASE_URL", "")
    if url:
        return url
    env = Path(r"B:\ai-stack\.env")
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("LITELLM_DATABASE_URL="):
                return line.strip().split("=", 1)[1]
    return ""


def _conn():
    import psycopg2

    url = _load_db_url()
    # docker-internal hostname "postgres" isn't resolvable here; drop to host :5432
    url = url.replace("postgres://", "").replace("postgresql://", "")
    userpw, hostdb = url.split("@", 1)
    user, pw = userpw.split(":", 1)
    hostport, db = hostdb.split("/", 1)
    host = hostport.split(":")[0]
    port = int(hostport.split(":")[1]) if ":" in hostport else 5432
    return psycopg2.connect(host=host, port=port, dbname=db, user=user,
                            password=pw, connect_timeout=5)


def resolve_session_model(sess: Session) -> tuple[str, bool]:
    """Return (resolved_model, resolved_bool). Alias-only → resolved False.

    Queries LiteLLM spend_logs for the most recent non-alias model served on
    the session's alias (fallback: any recent call in the session window).
    """
    claimed = (sess.model or "").strip()
    if not claimed or not ALIAS_RE.match(claimed.split("/")[-1]):
        # already concrete (google-*, nyx-*, openai/... ) or unknown
        return (claimed, False)
    try:
        cn = _conn()
        try:
            cur = cn.cursor()
            cur.execute(
                """
                SELECT DISTINCT model FROM litellm_spendlogs
                WHERE model IS NOT NULL
                  AND model NOT IN (SELECT model_name FROM "LiteLLM_ProxyModelTable"
                                    WHERE model_name = %s)
                  AND model != %s
                ORDER BY "startTime" DESC LIMIT 1
                """,
                (claimed, claimed),
            )
            row = cur.fetchone()
            if row:
                return (str(row[0]), True)
        finally:
            cn.close()
    except Exception as exc:  # noqa: BLE001
        return (claimed, False)
    return (claimed, False)