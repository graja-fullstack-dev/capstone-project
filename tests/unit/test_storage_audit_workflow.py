import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from pharma_intake import audit, db, repository, workflow
from pharma_intake.refgen import next_ref_id, peek_next_ref_id
from pharma_intake.schemas import Status
from pharma_intake.validation import validate_intake


def make(conn, raw):
    return repository.create_report(conn, validate_intake(raw).model)


def test_refs_unique_and_formatted(conn):
    assert peek_next_ref_id(conn, 2026) == "REF-2026-0001"
    ids = [next_ref_id(conn, 2026) for _ in range(5)]
    assert len(set(ids)) == 5 and ids[0] == "REF-2026-0001"


def test_refs_unique_under_concurrency(tmp_path):
    path = tmp_path / "c.db"
    db.connect(path).close()

    def alloc(_):
        c = db.connect(path)
        try:
            return next_ref_id(c, 2026)
        finally:
            c.close()

    with ThreadPoolExecutor(8) as ex:
        ids = list(ex.map(alloc, range(24)))
    assert len(set(ids)) == 24


def test_create_persists_report_ae_and_audit(conn, good_ae):
    ref = make(conn, good_ae)
    rep = repository.get_report(conn, ref)
    assert rep["status"] == "New" and rep["event_onset_date"] == "2026-03-02"
    ev = audit.list_events(conn, ref)
    assert ev[0]["action"] == "CREATE" and "description" in ev[0]["fields"]
    assert good_ae["description"] not in str(ev)  # no free text in audit


def test_failed_create_rolls_back(conn, good_pqc):
    model = validate_intake(good_pqc).model
    conn.execute("DROP TRIGGER audit_no_update")
    conn.execute("DROP TRIGGER audit_no_delete")
    conn.execute("DROP TABLE audit_log")  # audit insert will now fail after the report insert
    with pytest.raises(sqlite3.Error):
        repository.create_report(conn, model)
    assert conn.execute("SELECT COUNT(*) n FROM reports").fetchone()["n"] == 0


def test_audit_append_only_and_chain_detects_tamper(conn, good_pqc):
    make(conn, good_pqc)
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE audit_log SET actor='x'")
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM audit_log")
    assert audit.verify_chain(conn) == (True, None)
    conn.execute("DROP TRIGGER audit_no_update")  # attacker bypasses the trigger
    conn.execute("UPDATE audit_log SET actor='evil' WHERE id=1")
    ok, bad = audit.verify_chain(conn)
    assert not ok and bad == 1


def test_valid_transitions_and_hitl_gate(conn, good_pqc):
    ref = make(conn, good_pqc)
    assert workflow.request_transition(conn, ref, Status.IN_REVIEW, "REV-01")["applied"]
    r = workflow.request_transition(conn, ref, Status.CLOSED, "REV-01")
    assert r["pending_approval"] and not r["applied"]
    assert repository.get_report(conn, ref)["status"] == "In Review"  # frozen, not closed
    with pytest.raises(workflow.ReportFrozen):
        workflow.request_transition(conn, ref, Status.CLOSED, "REV-01")
    with pytest.raises(workflow.WorkflowError):  # four-eyes
        workflow.decide_approval(conn, ref, "REV-01", True)
    workflow.decide_approval(conn, ref, "REV-02", True)
    assert repository.get_report(conn, ref)["status"] == "Closed"
    actions = [e["action"] for e in audit.list_events(conn, ref)]
    assert actions == ["CREATE", "STATUS_CHANGE", "CLOSE_REQUESTED", "APPROVED", "STATUS_CHANGE"]
    assert audit.verify_chain(conn)[0]


def test_rejection_keeps_in_review(conn, good_pqc):
    ref = make(conn, good_pqc)
    workflow.request_transition(conn, ref, Status.IN_REVIEW, "REV-01")
    workflow.request_transition(conn, ref, Status.CLOSED, "REV-01")
    workflow.decide_approval(conn, ref, "REV-02", False)
    assert repository.get_report(conn, ref)["status"] == "In Review"
    assert workflow.request_transition(conn, ref, Status.CLOSED, "REV-01")["pending_approval"]


@pytest.mark.parametrize("start,target", [
    (Status.NEW, Status.CLOSED), (Status.NEW, Status.NEW), (Status.IN_REVIEW, Status.NEW), (Status.IN_REVIEW, Status.IN_REVIEW)])
def test_invalid_transitions(conn, good_pqc, start, target):
    ref = make(conn, good_pqc)
    if start == Status.IN_REVIEW:
        workflow.request_transition(conn, ref, Status.IN_REVIEW, "REV-01")
    with pytest.raises(workflow.InvalidTransition):
        workflow.request_transition(conn, ref, target, "REV-01")


def test_closed_is_terminal_and_unknown_ref(conn, good_pqc):
    ref = make(conn, good_pqc)
    workflow.request_transition(conn, ref, Status.IN_REVIEW, "REV-01")
    workflow.request_transition(conn, ref, Status.CLOSED, "REV-01")
    workflow.decide_approval(conn, ref, "REV-02", True)
    for t in Status:
        with pytest.raises(workflow.InvalidTransition):
            workflow.request_transition(conn, ref, t, "REV-01")
    with pytest.raises(workflow.NotFound):
        workflow.request_transition(conn, "REF-2026-9999", Status.IN_REVIEW, "REV-01")


def test_filtering(conn, good_pqc, good_ae):
    a, b = make(conn, good_pqc), make(conn, good_ae)
    workflow.request_transition(conn, b, Status.IN_REVIEW, "REV-01")
    assert [r["ref_id"] for r in repository.list_reports(conn, statuses=["In Review"])] == [b]
    assert [r["ref_id"] for r in repository.list_reports(conn, report_types=["Product Quality Complaint"])] == [a]
