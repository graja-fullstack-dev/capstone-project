import pytest

from pharma_intake import audit, repository, workflow
from pharma_intake.agent.llm import RuleBasedBackend
from pharma_intake.agent.orchestrator import Orchestrator
from pharma_intake.agent.tools import AgentContext
from pharma_intake.rag.models import ModelsUnavailable, models_ready


def test_lifecycle_through_agent_and_reviewer(conn):
    orch = Orchestrator(AgentContext(conn), RuleBasedBackend())
    run = orch.handle(
        "log report: type=AE; product=Fictazol 10 mg Tablets; lot=lot 88392; date=2026-03-04; reporter=hcp; "
        "channel=phone; description=Fictional case: mild nausea reported after first dose.; "
        "event=Mild nausea after first dose; onset=2026-03-03")
    assert run.route.value == "intake_form_tool" and "REF-" in run.reply, run.reply
    ref = run.reply.split("reference ")[1].split(" ")[0]
    assert repository.get_report(conn, ref)["batch_id"] == "LOT-88392"  # auto-repaired
    assert "In Review" in orch.handle(f"move {ref} to In Review reviewer REV-01").reply
    assert "frozen until a human reviewer approves" in orch.handle(f"close {ref} reviewer REV-01").reply
    assert repository.get_report(conn, ref)["status"] == "In Review"  # agent cannot close
    assert any(a["state"] == "PENDING" for a in repository.pending_approvals(conn))
    workflow.decide_approval(conn, ref, "REV-02", True)
    assert repository.get_report(conn, ref)["status"] == "Closed"
    assert audit.verify_chain(conn)[0]


def test_invalid_chat_intake_returns_field_errors_and_saves_nothing(conn):
    run = Orchestrator(AgentContext(conn), RuleBasedBackend()).handle(
        "log report: type=PQC; product=Fictazol; lot=LOT-12; date=2026-03-04; reporter=Consumer; channel=Email; description=short")
    assert "Batch/Lot number must look like LOT-12345" in run.reply
    assert repository.list_reports(conn) == []


def test_rag_route_without_models_gives_actionable_message(conn):
    def factory():
        raise ModelsUnavailable("run download_models")

    run = Orchestrator(AgentContext(conn, retriever_factory=factory), RuleBasedBackend()).handle("LOT-88392")
    assert run.route.value == "hybrid_rag" and "download_models" in run.reply


@pytest.mark.models
def test_real_models_hybrid_rag(conn, tmp_path):
    if not models_ready():
        pytest.skip("run scripts/download_models.py first")
    from pharma_intake.rag.pipeline import build_retriever
    from scripts.seed_data import seed
    seed(conn)
    r = build_retriever(conn, cache_dir=tmp_path)
    res = r.search("difficulty breathing")
    assert any("SOP-004" in h["doc_id"] or "88392" in h["text"] for h in res.hits)
    res = r.search("LOT-88392")
    assert any("LOT-88392" in h["text"] for h in res.hits)
    assert not r.search("quarterly cafeteria menu zebra").hits
