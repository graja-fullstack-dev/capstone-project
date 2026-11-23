import pytest

from pharma_intake import audit, repository
from pharma_intake.agent.circuit_breaker import CircuitBreaker, CircuitOpen
from pharma_intake.agent.llm import MockBackend, ToolCall, Turn
from pharma_intake.agent.orchestrator import Orchestrator
from pharma_intake.agent.router import Route, route
from pharma_intake.agent.tools import AgentContext, execute_tool, tool_definitions
from pharma_intake.guardrails import check_scope
from pharma_intake.validation import validate_intake


@pytest.mark.parametrize("text,expected", [
    ("hello", Route.DIRECT), ("Hi there", Route.DIRECT), ("thanks", Route.DIRECT),
    ("What does the SOP say about lot numbers?", Route.RAG), ("LOT-88392", Route.RAG),
    ("difficulty breathing", Route.RAG), ("What is the status of REF-2026-0001?", Route.RAG),
    ("move REF-2026-0001 to In Review, reviewer REV-01", Route.STATUS),
    ("close ref-2026-0002", Route.STATUS),
    ("log report: type=AE; product=X", Route.INTAKE), ("I received a new complaint", Route.INTAKE),
    ("Did the drug cause the anaphylaxis?", Route.REFUSE), ("What treatment should the patient take?", Route.REFUSE),
    ("Is this case reportable to the FDA?", Route.REFUSE)])
def test_router_table(text, expected):
    assert route(text)[0] == expected


def test_guardrail_categories():
    assert check_scope("is this reportable")[0] == "reportability"
    assert check_scope("was it caused by the product")[0] == "causality"
    assert check_scope("recommend a treatment")[0] == "treatment"
    assert check_scope("what is the SOP for lot numbers") is None


def test_circuit_breaker_third_identical_invalid_halts():
    b = CircuitBreaker()
    args = {"batch_id": "bad"}
    b.record("submit_intake_report", args, valid=False)
    b.record("submit_intake_report", args, valid=False)
    with pytest.raises(CircuitOpen):
        b.record("submit_intake_report", args, valid=False)
    with pytest.raises(CircuitOpen):
        b.check()


def test_circuit_breaker_resets_and_differs_by_args():
    b = CircuitBreaker()
    b.record("t", {"a": 1}, False)
    b.record("t", {"a": 1}, False)
    b.record("t", {"a": 1}, True)  # valid call resets
    b.record("t", {"a": 1}, False)
    b.record("t", {"a": 1}, False)
    b.record("t", {"a": 2}, False)  # different signature -> count restarts
    assert b.consecutive_invalid == 1 and not b.open


def test_tool_schema_is_self_contained():
    for d in tool_definitions():
        assert "$ref" not in str(d["input_schema"]) and d["input_schema"]["additionalProperties"] is False


def test_execute_tool_validation_errors(conn):
    ctx = AgentContext(conn)
    r = execute_tool(ctx, "update_status", {"ref_id": "nope", "target_status": "Closed", "reviewer_code": "REV-01"})
    assert not r.ok and r.validation_failed and "REF-2026-0001" in r.content
    assert execute_tool(ctx, "nope", {}).validation_failed
    assert execute_tool(ctx, "update_status", "string").validation_failed


def test_orchestrator_refusal_audited_without_text(conn):
    o = Orchestrator(AgentContext(conn), MockBackend([]))
    run = o.handle("Did the product cause this event?")
    assert run.route == Route.REFUSE and "causality" in run.reply
    ev = audit.list_events(conn)
    assert ev[-1]["action"] == "REFUSED" and "Did the product" not in str(ev)


def test_orchestrator_trips_breaker_on_repeated_invalid_calls(conn):
    bad = {"ref_id": "REF-2026-0001", "target_status": "Closed"}  # reviewer_code missing every time
    script = [Turn(tool_calls=[ToolCall(f"t{i}", "update_status", dict(bad))]) for i in range(5)]
    backend = MockBackend(script)
    run = Orchestrator(AgentContext(conn), backend).handle("close REF-2026-0001")
    assert run.circuit_open and backend.calls == 3
    assert audit.list_events(conn)[-1]["action"] == "CIRCUIT_OPEN"


def test_agent_close_request_never_approves(conn, good_pqc):
    ref = repository.create_report(conn, validate_intake(good_pqc).model)
    calls = [
        Turn(tool_calls=[ToolCall("1", "update_status", {"ref_id": ref, "target_status": "In Review", "reviewer_code": "REV-01"})]),
        Turn(tool_calls=[ToolCall("2", "update_status", {"ref_id": ref, "target_status": "Closed", "reviewer_code": "REV-01"})]),
        Turn(text="done"),
    ]
    run = Orchestrator(AgentContext(conn), MockBackend(calls)).handle(f"move {ref} through review")
    assert repository.get_report(conn, ref)["status"] == "In Review"
    assert run.reply == "done"
