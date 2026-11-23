"""Unique reference ID generator: REF-<year>-<4-digit sequence>."""
from __future__ import annotations

import sqlite3
from datetime import date

from .db import transaction


def _fmt(year: int, n: int) -> str:
    return f"REF-{year}-{n:04d}"


def peek_next_ref_id(conn: sqlite3.Connection, year: int | None = None) -> str:
    """Preview the ID the next submission will receive (does not reserve it)."""
    year = year or date.today().year
    row = conn.execute("SELECT last FROM ref_sequence WHERE year = ?", (year,)).fetchone()
    return _fmt(year, (row["last"] if row else 0) + 1)


def next_ref_id(conn: sqlite3.Connection, year: int | None = None) -> str:
    """Atomically allocate the next ID (BEGIN IMMEDIATE serializes writers)."""
    year = year or date.today().year
    with transaction(conn):
        conn.execute("INSERT OR IGNORE INTO ref_sequence(year, last) VALUES (?, 0)", (year,))
        conn.execute("UPDATE ref_sequence SET last = last + 1 WHERE year = ?", (year,))
        n = conn.execute("SELECT last FROM ref_sequence WHERE year = ?", (year,)).fetchone()["last"]
    return _fmt(year, n)
