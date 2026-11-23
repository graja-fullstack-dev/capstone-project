"""Status lifecycle state machine with a human-in-the-loop gate on In Review -> Closed.

The ONLY code path that changes `reports.status`. Agents may request closure but
can never approve it: `decide_approval` is called from the reviewer UI only.
"""
from __future__ import annotations

import sqlite3

from . import audit
from .db import transaction
from .schemas import Status

ALLOWED: dict[Status, list[Status]] = {
    Status.NEW: [Status.IN_REVIEW],
    Status.IN_REVIEW: [Status.CLOSED],
    Status.CLOSED: [],
}


class WorkflowError(Exception):
    pass


class InvalidTransition(WorkflowError):
    pass


class ReportFrozen(WorkflowError):
    pass


class NotFound(WorkflowError):
    pass


def _get(conn: sqlite3.Connection, ref_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT ref_id, status FROM reports WHERE ref_id = ?", (ref_id,)).fetchone()
    if not row:
        raise NotFound(f"Report {ref_id} was not found")
    return row


def _pending(conn: sqlite3.Connection, ref_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM approvals WHERE ref_id = ? AND state = 'PENDING'", (ref_id,)).fetchone()


def _apply(conn: sqlite3.Connection, ref_id: str, frm: Status, to: Status, actor: str) -> None:
    now = audit.now_utc()
    conn.execute("UPDATE reports SET status = ?, updated_at = ? WHERE ref_id = ?", (to.value, now, ref_id))
    conn.execute("INSERT INTO status_transitions (ref_id, from_status, to_status, actor, at) VALUES (?,?,?,?,?)",
                 (ref_id, frm.value, to.value, actor, now))
    audit.log_event(conn, "STATUS_CHANGE", actor=actor, ref_id=ref_id, from_status=frm.value, to_status=to.value)


def request_transition(conn: sqlite3.Connection, ref_id: str, target: Status, actor: str) -> dict:
    """Request a transition. Returns {'applied': bool, 'pending_approval': bool, 'status': str}."""
    with transaction(conn):
        current = Status(_get(conn, ref_id)["status"])
        if _pending(conn, ref_id):
            raise ReportFrozen(f"{ref_id} is frozen: a Closed approval is pending human reviewer authorization")
        if target not in ALLOWED[current]:
            allowed = ", ".join(s.value for s in ALLOWED[current]) or "none (terminal state)"
            raise InvalidTransition(f"Cannot move {ref_id} from '{current.value}' to '{target.value}'. Allowed next: {allowed}")
        if target == Status.CLOSED:  # HITL gate
            conn.execute("INSERT INTO approvals (ref_id, requested_by, requested_at) VALUES (?,?,?)",
                         (ref_id, actor, audit.now_utc()))
            audit.log_event(conn, "CLOSE_REQUESTED", actor=actor, ref_id=ref_id,
                            from_status=current.value, to_status=target.value)
            return {"applied": False, "pending_approval": True, "status": current.value}
        _apply(conn, ref_id, current, target, actor)
        return {"applied": True, "pending_approval": False, "status": target.value}


def decide_approval(conn: sqlite3.Connection, ref_id: str, reviewer_code: str, approve: bool) -> dict:
    """Human reviewer decision. Approval is recorded in the audit trail BEFORE the state changes."""
    with transaction(conn):
        current = Status(_get(conn, ref_id)["status"])
        pend = _pending(conn, ref_id)
        if not pend:
            raise WorkflowError(f"{ref_id} has no pending approval")
        if pend["requested_by"] == reviewer_code:
            raise WorkflowError("Reviewer must differ from the requester (four-eyes principle)")
        state = "APPROVED" if approve else "REJECTED"
        conn.execute("UPDATE approvals SET state = ?, reviewer_code = ?, decided_at = ? WHERE id = ?",
                     (state, reviewer_code, audit.now_utc(), pend["id"]))
        audit.log_event(conn, state, actor=reviewer_code, ref_id=ref_id,
                        from_status=current.value, to_status=Status.CLOSED.value)
        if approve:
            _apply(conn, ref_id, current, Status.CLOSED, reviewer_code)
        return {"applied": approve, "status": Status.CLOSED.value if approve else current.value}
