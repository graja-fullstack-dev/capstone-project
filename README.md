# Pharma Safety Intake & Triage Tracker (capstone prototype)

Local Streamlit app for **fictional** product-quality complaints and suspected adverse event reports.
It validates intake, tracks New -> In Review -> Closed (closure needs human approval), keeps a hash-chained
audit trail, and answers SOP/history questions through a 4-stage hybrid RAG pipeline driven by a 5-step agent control plane.

> Training prototype, synthetic data only. It never assesses causality, recommends treatment, determines regulatory
> reportability, or makes clinical/regulatory decisions.

## Quick start (Windows / any OS, Python 3.10+)
```bash
pip install -r requirements.txt
python scripts/download_models.py     # one-time (needs internet); afterwards fully offline
python scripts/seed_data.py           # 4 fictional reports
streamlit run app.py
```
Tests: `pytest` (fast, offline) and `pytest -m models` (real local models, after the download).
Demo evidence: `python scripts/generate_demo.py` -> `docs/demo/walkthrough.md`.

## Pages
| Page | Purpose |
|---|---|
| Intake | Form with context-sensitive errors, auto-repair notes, PII guard; AE fields appear only for adverse events |
| Dashboard | Table filtered by status / type, detail + audit history, transitions |
| Review Approvals | HITL gate: a human reviewer (different from the requester) approves or rejects closure |
| Knowledge Assistant | Chat: router -> hybrid RAG / intake tool / status tool, with retrieval-stage and ReAct trace views |
| Audit Log | Read-only log, hash-chain verification, CSV export |

## Architecture (see `docs/plan.md`, `CLAUDE.md`)
- `pharma_intake/schemas.py, validation.py` - Pydantic v2 schemas (`^LOT-\d{5}$`, `extra=forbid`), auto-repair, PII guard
- `repository.py, workflow.py, audit.py, db.py` - SQLite; only `workflow.py` changes status; `audit_log` is append-only (triggers) and hash-chained
- `rag/` - BM25 (k1=1.3, b=0.75) -> bi-encoder (512/64 chunks, cosine) -> RRF (k=60, top-50 each) -> cross-encoder (threshold 0.40, top 3-5); extractive cited answers only
- `agent/` - Pydantic-validated tool registry, short-term ReAct trace + long-term SQLite memory, deterministic router (guardrails first), HITL gate, circuit breaker (>2 identical invalid calls halts; 8-step cap)
- Governance: `CLAUDE.md`, `.claude/skills/pharma-intake-review/`, `.claude/settings.json` + `.claude/hooks/audit_file_edit.py` (metadata-only edit log in `logs/claude_edit_audit.jsonl`)

## Optional: Claude as the agent LLM
Default backend is an offline rule-based translator. Setting `PHARMA_ENABLE_CLAUDE=1` (plus `ANTHROPIC_API_KEY`) switches the
intake/status routes to Claude tool use (`claude-opus-5-5`, override with `PHARMA_LLM_MODEL`). **This is the one deliberate exception to the
"no external APIs" rule**; every tool call still passes through the same Pydantic validation, HITL gate and circuit breaker.
Chat intake without Claude uses `key=value` pairs, e.g. `log report: type=PQC; product=Fictazol 10 mg Tablets; lot=LOT-45210; date=2026-03-04; reporter=Consumer; channel=Email; description=Fictional note about a damaged strip.`

## Production gaps (not addressed by this prototype)
Authentication/RBAC and real reviewer identity, e-signature (21 CFR Part 11), encrypted storage, a managed DB, backups and retention,
validated (GxP) model/versioning, monitoring, and integration with an enterprise pharmacovigilance system.
