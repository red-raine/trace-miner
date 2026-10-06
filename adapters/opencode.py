"""adapter: opencode session store (SQLite ~/.local/share/opencode/opencode.db).

opencode persists sessions/messages/parts in a SQLite DB (wal-mode).
This adapter streams rows read-only via Python's sqlite3.* connection
(no intrusive reads; DB is 3.5GB here, so streaming + LIMIT is used).

WAL caveat: open an immutable/"mode=ro" connection so we never write
checkpoints on the host DB.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from canon import EventKind, Session, Span

DEFAULT_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def _ro_connect(db: Path) -> sqlite3.Connection:
    uri = str(db.resolve()) if db.exists() else str(db)
    return sqlite3.connect(f"file:{uri}?mode=ro", uri=True, timeout=10)


def iter_sessions(db: Path | None = None, limit_sessions: int = 200) -> list[Session]:
    db = db or DEFAULT_DB
    if not db.exists():
        return []
    conn = _ro_connect(db)
    out: list[Session] = []
    try:
        tables = {r[0] for r in conn.execute(
            "select name from sqlite_master where type='table'")}
        if "session" not in tables:
            return []
        # introspection-safe column discovery
        session_cols = [d[1] for d in conn.execute("pragma table_info(session)")]
        msg_cols = [d[1] for d in conn.execute("pragma table_info(message)")] \
            if "message" in tables else []
        sid_col = "id" if "id" in session_cols else session_cols[0]
        srows = list(conn.execute(
            f"select * from session order by rowid desc limit ?", (limit_sessions,)))
        for srow in srows:
            srec = dict(zip(session_cols, srow))
            sid = str(srec.get(sid_col, srec.get("title", "")))
            sess = Session(
                agent="opencode", session_id=sid,
                cwd=str(srec.get("directory", "")),
                model=str(srec.get("model", "")),
                started_at=str(srec.get("time", {}).get("created", "")
                               if isinstance(srec.get("time"), dict) else ""),
            )
            # optional message-level traversal (streaming, capped)
            if "message" in tables:
                msg_rows = conn.execute(
                    "select * from message where session_id = ? limit 500",
                    (srec.get(sid_col),)).fetchall()
                for i, mi in enumerate(msg_rows):
                    mrec = dict(zip(msg_cols, mi))
                    role = str(mrec.get("role", ""))
                    seq = len(sess.spans) + 1
                    sess.spans.append(Span(
                        agent="opencode", session_id=sid,
                        kind=EventKind.ITERATION if role == "assistant"
                        else EventKind.TASK_CLAIM if role == "user"
                        else EventKind.TOOL_CALL,
                        ts=str(mrec.get("time", {}).get("created", "")
                               if isinstance(mrec.get("time"), dict) else ""),
                        name=f"message.{role}", seq=seq,
                        attrs={"message_id": str(mrec.get("id", ""))},
                    ))
                    if len(sess.spans) > 2000:
                        break
            out.append(sess)
    finally:
        conn.close()
    return [s for s in out if s.spans or s.session_id]