"""Append-only, hash-chained audit trail. Records field NAMES only, never free-text values."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

GENESIS = "0" * 64


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _digest(prev_hash: str, ts: str, actor: str, action: str, ref_id, from_s, to_s, fields) -> str:
    body = json.dumps([prev_hash, ts, actor, action, ref_id, from_s, to_s, fields], sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def log_event(
    conn: sqlite3.Connection,
    action: str,
    actor: str = "system",
    ref_id: str | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    fields: list[str] | None = None,
) -> int:
    """Append an event. Call inside the same transaction as the state change."""
    row = conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    prev = row["hash"] if row else GENESIS
    ts = now_utc()
    fields_json = json.dumps(sorted(fields)) if fields else None
    h = _digest(prev, ts, actor, action, ref_id, from_status, to_status, fields_json)
    cur = conn.execute(
        "INSERT INTO audit_log (ts_utc, actor, action, ref_id, from_status, to_status, fields, prev_hash, hash)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (ts, actor, action, ref_id, from_status, to_status, fields_json, prev, h),
    )
    return int(cur.lastrowid)


def list_events(conn: sqlite3.Connection, ref_id: str | None = None) -> list[dict]:
    q, args = "SELECT * FROM audit_log", ()
    if ref_id:
        q, args = q + " WHERE ref_id = ?", (ref_id,)
    return [dict(r) for r in conn.execute(q + " ORDER BY id", args)]


def verify_chain(conn: sqlite3.Connection) -> tuple[bool, int | None]:
    """Return (ok, first_bad_id). Detects edits made by bypassing the triggers."""
    prev = GENESIS
    for r in conn.execute("SELECT * FROM audit_log ORDER BY id"):
        expected = _digest(prev, r["ts_utc"], r["actor"], r["action"], r["ref_id"],
                           r["from_status"], r["to_status"], r["fields"])
        if r["prev_hash"] != prev or r["hash"] != expected:
            return False, int(r["id"])
        prev = r["hash"]
    return True, None
