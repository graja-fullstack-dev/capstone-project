"""SQLite schema and connection helper. Audit log is append-only via triggers."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    ref_id        TEXT PRIMARY KEY,
    report_type   TEXT NOT NULL CHECK (report_type IN ('Suspected Adverse Event','Product Quality Complaint')),
    product_name  TEXT NOT NULL,
    batch_id      TEXT NOT NULL,
    date_received TEXT NOT NULL,
    reporter_type TEXT NOT NULL,
    channel       TEXT NOT NULL,
    description   TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'New' CHECK (status IN ('New','In Review','Closed')),
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ae_details (
    ref_id            TEXT PRIMARY KEY REFERENCES reports(ref_id),
    event_description TEXT NOT NULL,
    event_onset_date  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS status_transitions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_id      TEXT NOT NULL REFERENCES reports(ref_id),
    from_status TEXT NOT NULL,
    to_status   TEXT NOT NULL,
    actor       TEXT NOT NULL,
    at          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_id        TEXT NOT NULL REFERENCES reports(ref_id),
    requested_by  TEXT NOT NULL,
    requested_at  TEXT NOT NULL,
    state         TEXT NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING','APPROVED','REJECTED')),
    reviewer_code TEXT,
    decided_at    TEXT
);
CREATE TABLE IF NOT EXISTS ref_sequence (
    year INTEGER PRIMARY KEY,
    last INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc      TEXT NOT NULL,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    ref_id      TEXT,
    from_status TEXT,
    to_status   TEXT,
    fields      TEXT,
    prev_hash   TEXT NOT NULL,
    hash        TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
"""


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Open a connection (autocommit mode; use `transaction()` for atomic writes)."""
    p = Path(path) if path else config.db_path()
    if str(p) != ":memory:":
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), isolation_level=None, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE ... COMMIT/ROLLBACK. Re-entrant: nested use joins the outer one."""
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
