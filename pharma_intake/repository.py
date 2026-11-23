"""Data access for reports. Writes are atomic and always paired with an audit event."""
from __future__ import annotations

import sqlite3

from . import audit
from .db import transaction
from .refgen import next_ref_id
from .schemas import ReportType, Status, SubmitIntakeReportArgs


def create_report(conn: sqlite3.Connection, args: SubmitIntakeReportArgs, actor: str = "intake-operator") -> str:
    """Persist a validated report + AE details + CREATE audit event in one transaction."""
    now = audit.now_utc()
    with transaction(conn):
        ref_id = next_ref_id(conn)
        conn.execute(
            "INSERT INTO reports (ref_id, report_type, product_name, batch_id, date_received, reporter_type,"
            " channel, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ref_id, args.report_type.value, args.product_name, args.batch_id, args.date_received.isoformat(),
             args.reporter_type.value, args.channel.value, args.description, Status.NEW.value, now, now),
        )
        field_names = ["product_name", "batch_id", "date_received", "reporter_type", "channel", "description"]
        if args.report_type == ReportType.AE:
            conn.execute(
                "INSERT INTO ae_details (ref_id, event_description, event_onset_date) VALUES (?,?,?)",
                (ref_id, args.event_description, args.event_onset_date.isoformat()),
            )
            field_names += ["event_description", "event_onset_date"]
        audit.log_event(conn, "CREATE", actor=actor, ref_id=ref_id, to_status=Status.NEW.value, fields=field_names)
    return ref_id


def get_report(conn: sqlite3.Connection, ref_id: str) -> dict | None:
    row = conn.execute(
        "SELECT r.*, a.event_description, a.event_onset_date FROM reports r"
        " LEFT JOIN ae_details a ON a.ref_id = r.ref_id WHERE r.ref_id = ?", (ref_id,)
    ).fetchone()
    return dict(row) if row else None


def list_reports(conn: sqlite3.Connection, statuses: list[str] | None = None,
                 report_types: list[str] | None = None) -> list[dict]:
    q, where, args = "SELECT * FROM reports", [], []
    if statuses:
        where.append(f"status IN ({','.join('?' * len(statuses))})")
        args += statuses
    if report_types:
        where.append(f"report_type IN ({','.join('?' * len(report_types))})")
        args += report_types
    if where:
        q += " WHERE " + " AND ".join(where)
    return [dict(r) for r in conn.execute(q + " ORDER BY created_at DESC, ref_id DESC", args)]


def pending_approvals(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT ap.*, r.product_name, r.batch_id FROM approvals ap JOIN reports r ON r.ref_id = ap.ref_id"
        " WHERE ap.state = 'PENDING' ORDER BY ap.id")]
