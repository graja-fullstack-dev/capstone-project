# CLAUDE.md — Pharma Safety Intake & Triage Tracker

Persistent contract for AI coding agents working in this repo. Source of truth for requirements: `Pharma_Safety_Intake_Tracker_Advanced_Capstone_Case_Study.pdf`. The approved build plan is `docs/plan.md`.

## 1. What this is
A local, training-only Streamlit app that captures fictional product-quality complaints (PQC) and suspected adverse event (AE) reports, validates them, tracks New → In Review → Closed, keeps a tamper-evident audit trail, and answers historical/SOP questions with a 4-stage hybrid RAG pipeline driven by a 5-step agentic control plane.

## 2. Hard scope limits (never violate)
- **Non-clinical.** The app and any code/prompt/test you write must NEVER assess causality, recommend medical treatment, determine regulatory reportability, replace a pharmacovigilance system, or make clinical/regulatory decisions. Requests to do so get a fixed refusal from `pharma_intake/guardrails.py`.
- **Fictional data only.** No real patient names, initials, DOB, contact details, MRNs, medical history, or real company/product data. Seed data, fixtures, tests and docs use obviously synthetic values (e.g. `LOT-88392`, "Examplomab").
- **Data minimization.** Collect only the fields in the PDF. No patient-identifier fields in forms. Audit entries record action, timestamps, ref ID, status change, and the *names* of changed fields — never free-text values.
- **Local only.** No cloud infrastructure, remote DBs, telemetry, or external APIs. Single documented exception: the Claude agent backend, opt-in via `PHARMA_ENABLE_CLAUDE=1` (off by default; tests never use it).

## 3. Stack
Python 3.10+ (dev on 3.12), Streamlit, Pydantic v2, SQLite (stdlib `sqlite3`), `rank-bm25`, `sentence-transformers` (local bi-encoder `all-MiniLM-L6-v2`, cross-encoder `ms-marco-MiniLM-L-6-v2`), `numpy`, `anthropic` (opt-in only), `pytest`. Pin changes go through `requirements.txt`; do not add dependencies without need.

## 4. Architecture rules
Layout: `app.py` + `pages/` (UI) → `pharma_intake/` services → repository/SQLite. Details in `docs/plan.md`.
- UI pages contain no SQL and no business rules; they call services.
- **Every status change goes through `pharma_intake/workflow.py`.** Allowed: New→In Review, In Review→Closed. Closed is terminal. In Review→Closed requires human reviewer approval recorded in the audit trail; the report is frozen while pending. Agents can request closure, never approve it.
- `audit_log` is append-only (SQLite triggers block UPDATE/DELETE) and hash-chained; never bypass `audit.py`.
- All tool calls (`submit_intake_report`, `update_status`, `search_knowledge`) are validated by Pydantic models with `extra="forbid"` and strict regexes: `batch_id ^LOT-\d{5}$`, `ref_id ^REF-\d{4}-\d{4}$`, `reviewer_code ^REV-\d{2}$`.
- Router runs deterministically **before** any LLM/tool call: greeting → direct reply; SOP/history → hybrid RAG; new submission → intake tool; triage update → status workflow manager. Guardrails run before the router.
- Circuit breaker: same tool + identical argument signature failing validation more than 2 consecutive times halts the loop and writes an audit event. Hard cap of 8 agent iterations.
- RAG constants live in `pharma_intake/config.py` only: BM25 k1=1.3, b=0.75; chunks 512 tokens / 64 overlap; top-50 per retriever; RRF k=60; cross-encoder threshold 0.40; pass top 3–5 chunks. RAG answers are extractive and cited; if nothing clears 0.40, say so — never fabricate.
- Claude backend (when enabled): model `claude-opus-5-5` (override `PHARMA_LLM_MODEL`), manual tool loop, `thinking={"type":"adaptive"}`, `tool_choice` auto (forced tool choice is rejected by this model), all `tool_result` blocks returned in one user message, `is_error: true` on validation failure, check `stop_reason` (incl. `refusal`, `max_tokens`).

## 5. Coding guidelines
- Type hints everywhere; Pydantic models for all external input; small pure functions in services.
- Validation errors must be explicit and context-sensitive (name the field, the rule, and the offending shape), e.g. "Batch/Lot number must look like LOT-12345".
- Don't log, print, or persist report descriptions outside the DB. No `print` of report content; use `logging` with IDs only.
- Dates are ISO-8601 UTC for audit; date-received cannot be in the future; AE onset cannot be after date-received.
- Prefer editing existing modules over creating new ones; keep functions short; no speculative abstraction.

## 6. Testing conventions
- Run `pytest -q` before declaring work done. Model-dependent tests are marked `@pytest.mark.models` (run `pytest -q -m models` after `python scripts/download_models.py`).
- Every new validation rule, transition, guardrail, or breaker behavior needs a unit test; cross-module flows get an integration test using a temp SQLite DB (never `logs/app.db`).
- Required coverage: schema validation, storage integrity (incl. audit append-only + hash chain), workflow + HITL freeze, router table, circuit-breaker limits, RAG stages (BM25 exact lot hit, RRF math, 0.40 threshold with a fake cross-encoder).
- Agent tests use `MockBackend`; no network in tests.

## 7. Governance tooling
- **Hook:** `.claude/settings.json` registers a `PostToolUse` hook (`Edit|Write|MultiEdit|NotebookEdit`) running `.claude/hooks/audit_file_edit.py`, which appends tool name, relative path, timestamp, session ID and a hash link to `logs/claude_edit_audit.jsonl`. It must never record file contents, diffs, or user descriptions. Do not disable or edit it to widen what it logs.
- **Review skill:** `.claude/skills/pharma-intake-review/` holds checklists (data minimization, error handling, auditability, test coverage). Invoke it before finishing a milestone and on any review request.
- Rules that must hold deterministically belong in hooks/code; judgment-based guidance belongs here or in skills.

## 8. Workflow for agents
1. Read `docs/plan.md` and build one milestone at a time: A skeleton → B intake/schemas → C validation/persistence → D dashboard/lifecycle → E RAG → F agent control plane → G tests/demo.
2. Keep changes within the active milestone; run tests; summarize what changed.
3. Ask before adding dependencies, changing the schema of persisted tables, or touching `.claude/` governance files.
4. Never commit `logs/`, `*.db`, downloaded models, or `.env`.
