# Plan — Pharma Safety Intake & Triage Tracker (Capstone)

## Context
The workspace `c:\Users\vmadmin\Downloads\capstone` contains only the case-study PDF. It is a new project. The PDF asks for a local Streamlit app that does these things:
- capture fictional adverse-event (AE) and product-quality-complaint (PQC) reports
- enforce validation
- track the New → In Review → Closed lifecycle
- keep an immutable audit trail
- answer historical and SOP questions through a 4-stage hybrid RAG pipeline (BM25 → bi-encoder → RRF → cross-encoder)
- run a 5-step agentic control plane: Pydantic tool validation, dual memory, deterministic router, human-in-the-loop (HITL) gate, circuit breaker

It also needs governance artifacts: CLAUDE.md, a review skill, a PostToolUse audit hook, tests, demo evidence and a reflection. This plan is Deliverable 3 ("Plan Mode output").

**Decisions confirmed with the user**
- RAG models are local Hugging Face models, downloaded once and then run offline on CPU:
  - bi-encoder `sentence-transformers/all-MiniLM-L6-v2`
  - cross-encoder `cross-encoder/ms-marco-MiniLM-L-6-v2`
- RAG answers are **extractive**: cited chunks, no generative LLM.
- The agent uses **Claude tool calling** (`claude-opus-5-5`, can be overridden with `PHARMA_LLM_MODEL`). It is opt-in, behind `PHARMA_ENABLE_CLAUDE=1`.
  - Default and tests: an offline `RuleBasedBackend` / `MockBackend` uses the same tool interface.
  - The README notes that turning Claude on is the one documented exception to "no external APIs".
- Environment: Python 3.12, no GPU, nothing installed yet. Not a git repo; `git init` happens in milestone 0.

## Target layout
```
CLAUDE.md  README.md  requirements.txt  pyproject.toml  app.py
.claude/settings.json                         # PostToolUse hook registration
.claude/hooks/audit_file_edit.py              # deterministic edit logger
.claude/skills/pharma-intake-review/SKILL.md  (+ checklists/*.md)
pharma_intake/
  config.py            # paths, flags, thresholds (k1, b, k=60, 0.40, top-k)
  schemas.py           # Pydantic v2 enums + models + tool-arg models
  validation.py        # context-sensitive errors, auto-repair, PII guard
  refgen.py            # REF-YYYY-NNNN
  db.py / repository.py# SQLite schema, migrations, CRUD
  audit.py             # append-only, hash-chained audit log
  workflow.py          # state machine + HITL approvals
  guardrails.py        # non-clinical refusal filter
  rag/{chunker,bm25,dense,fusion,rerank,pipeline,answer,corpus}.py
  agent/{router,tools,memory,circuit_breaker,llm,orchestrator}.py
pages/ 1_Intake.py 2_Dashboard.py 3_Review_Approvals.py 4_Knowledge_Assistant.py 5_Audit_Log.py
data/seed/sops/*.md  data/seed/reports.json    # fictional only
scripts/ download_models.py  seed_data.py  build_index.py
tests/ unit/  integration/  conftest.py
docs/ demo/  reflection.md
logs/  (gitignored: app.db, claude_edit_audit.jsonl, models/)
```

## Milestone 0 — Governance first (Phases I, IV, V)
Done before any app code, so the hook captures every later edit.
- **CLAUDE.md** covers:
  - scope and non-clinical limits: never assess causality, recommend treatment, or decide reportability
  - synthetic data only, no PII, no patient identifiers
  - local-only stack, with the Claude opt-in exception
  - module boundaries: UI → services → repository. The UI never writes SQL; every status change goes through `workflow.py`.
  - coding rules: Pydantic v2, type hints, no `print` logging of report content
  - testing: `pytest -q`, a new rule needs a test, model-dependent tests marked `@pytest.mark.models`
  - a pointer to the review skill
- **Skill** `.claude/skills/pharma-intake-review/SKILL.md`, with frontmatter (name, description, when to invoke) and four checklists:
  - `data-minimization.md`
  - `error-handling.md`
  - `auditability.md`
  - `test-coverage.md`

  The skill's output format is a findings table with file:line, checklist item, severity.
- **Hook** in `.claude/settings.json`:
  - registration: `PostToolUse`, matcher `Edit|Write|MultiEdit|NotebookEdit`, command `python .claude/hooks/audit_file_edit.py`
  - the script reads the hook JSON from stdin and appends one JSONL line to `logs/claude_edit_audit.jsonl`
  - each line holds only `ts_utc`, `session_id`, `tool_name`, the repo-relative `file_path`, `event_seq`, and `sha256(prev_line)`
  - it **never** writes `content`, `old_string`, `new_string` or descriptions
  - it always exits 0 so it never blocks work, and it is pure stdlib

## Milestone A — Skeleton
- `requirements.txt`: streamlit, pydantic>=2, rank-bm25, sentence-transformers, numpy, anthropic, pytest. `pyproject.toml` holds the pytest config and markers.
- The Streamlit multipage shell has a sidebar banner: "Training prototype – fictional data – non-clinical".
- `config.py` and `db.py`: create the SQLite file at `logs/app.db` with these tables:
  - `reports`
  - `ae_details`
  - `status_transitions`
  - `approvals`
  - `audit_log`
  - `ref_sequence`
- `audit_log` gets SQLite `BEFORE UPDATE/DELETE` triggers that `RAISE(ABORT)`. This makes it append-only.

## Milestone B — Intake form and schemas
- `schemas.py`:
  - enums:
    - `ReportType` (Suspected Adverse Event, Product Quality Complaint)
    - `Status` (New, In Review, Closed)
    - `ReporterType` (Healthcare Professional, Consumer, Sales Representative, Other)
    - `Channel` (Email, Telephone)
  - `IntakeReport`: product_name, `batch_id` matching `^LOT-\d{5}$`, date_received (not in the future), reporter_type, channel, description (20–2000 characters)
  - `AdverseEventDetails`: event_description, event_onset_date (not after date_received). It is required when type = AE and must be absent for PQC.
  - tool-arg models: `SubmitIntakeReportArgs`, `UpdateStatusArgs` (`ref_id` matching `^REF-\d{4}-\d{4}$`, target_status, reviewer_code `^REV-\d{2}$`, note), `SearchKnowledgeArgs`. Every model uses `extra="forbid"`.
- `refgen.py`: the sequence increments inside a `BEGIN IMMEDIATE` transaction, giving a unique `REF-2026-0001` style ID. The ID is shown as soon as the form is started.
- `pages/1_Intake.py`: the AE fields appear only when the AE type is chosen. There are no fields for patient name, DOB, initials or contact details.

## Milestone C — Validation and persistence
- `validation.py` turns Pydantic errors into messages that name the field and the context. Example: "Batch/Lot number must look like LOT-12345 (you entered 'lot 1234')", or "Event onset date is required for Suspected Adverse Events".
- **Auto-repair** normalizes `lot 12345` / `LOT12345` → `LOT-12345`, `ref-2026-1` → `REF-2026-0001`, trims whitespace, and maps case-insensitive enum aliases. Every repair is reported back to the user.
- **PII guard** uses regexes for email, phone, DOB patterns and phrases like "patient name", "MRN" or "SSN". A match rejects the free-text fields with a message to use fictional, de-identified text.
- `repository.py` writes the report, the AE details and an audit `CREATE` event in one transaction.
- Audit events (`audit.py`) contain ts, actor_role/reviewer_code, action, ref_id, from/to status, the **names** of changed fields (never their values), `prev_hash` and `hash`. `verify_chain()` detects tampering.

## Milestone D — Dashboard and lifecycle
- `pages/2_Dashboard.py`: a `st.dataframe` with multiselect filters for status and type, plus a detail expander.
- `workflow.py` holds the allowed-transition map `{New: [In Review], In Review: [Closed]}`. `Closed` is terminal and anything else raises `InvalidTransition`.
  - **HITL**: In Review → Closed creates a `PENDING` approval and leaves the report frozen; any other change is refused while the approval is pending.
  - `3_Review_Approvals.py` lets a reviewer approve or reject with a reviewer code. Approval writes an `APPROVED` audit event and then applies the transition. Rejection keeps the report In Review.
- `5_Audit_Log.py` shows the audit log read-only, with the result of the chain check.

## Milestone E — Multi-stage hybrid RAG (`pharma_intake/rag/`)
- **Corpus**: about 8 fictional SOP markdown files plus the saved reports, rendered as text. Only ref, type, product, lot, status and description are included; no audit or reviewer data.
- `chunker.py`: 512-token chunks with 64-token overlap, using the bi-encoder's tokenizer.
- `bm25.py`: `rank_bm25.BM25Okapi(k1=1.3, b=0.75)` with a tokenizer that keeps codes such as `LOT-88392` and `REF-2026-0001` intact. Returns the top 50.
- `dense.py`: SentenceTransformer embeddings, normalized, compared with numpy cosine. The index is cached to `logs/index/` and rebuilt when the corpus hash changes. Returns the top 50.
- `fusion.py`: RRF, `score = Σ 1/(60 + rank)`.
- `rerank.py`: `CrossEncoder` scores passed through a sigmoid; anything below **0.40** is dropped and the top 3–5 are kept.
- `pipeline.py`: `HybridRetriever.search(q)` returns the chunks plus per-stage diagnostics. The Knowledge Assistant page shows these as the stage evidence for the demo.
- `answer.py`: an extractive answer listing the quoted chunks with their sources and a non-clinical disclaimer. If nothing clears 0.40 it says "No sufficiently relevant record found" and makes nothing up.
- `scripts/download_models.py` fetches both models once into `logs/models/`. At runtime `HF_HUB_OFFLINE=1` is set.

## Milestone F — Agentic control plane (`pharma_intake/agent/`)
1. **Type-safe tool validation** (`tools.py`):
   - A registry maps each tool name to its Pydantic model and handler. The Claude `input_schema` comes from `model_json_schema()`, with `additionalProperties: false` and `strict: true`.
   - Every call passes through auto-repair and then `Model.model_validate`. A failure returns a structured `tool_result` with `is_error: true` and a field-level message.
2. **Dual memory** (`memory.py`):
   - `ShortTermMemory` is a volatile Thought/Action/Observation list held in session state, which the UI can display.
   - `LongTermMemory` is a facade over the repository and audit log in SQLite.
3. **Deterministic router** (`router.py`) runs these ordered rules before any LLM call:
   - greeting regex → **direct canned response**
   - `REF-…` plus status verbs → **Status Workflow Manager**
   - intake verbs (report, complaint, received) → **Intake Form Tool**
   - otherwise → **Hybrid RAG**

   `guardrails.py` runs first and refuses causality, treatment and reportability questions. The route determines which tools are offered to the LLM, and RAG never calls the LLM.
4. **HITL gate**: when `update_status` targets Closed it creates a pending approval and returns "awaiting human approval". The agent cannot approve.
5. **Circuit breaker** (`circuit_breaker.py`):
   - signature = tool name + sha256 of the canonical sorted-JSON arguments
   - the counter rises for each invalid result with the same signature and resets after a valid call
   - more than 2 consecutive failures trips it; the loop stops and a `CIRCUIT_OPEN` audit event is written
   - there is also an overall limit of 8 iterations

`llm.py` defines the `LLMBackend` protocol and three backends:
- `ClaudeBackend`, which uses the official `anthropic` SDK and a manual loop over `client.beta.messages.create`:
  - model `claude-opus-5-5`, `max_tokens=16000`, `thinking={"type":"adaptive"}`, `tool_choice` auto
  - server-side fallbacks: `betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`
  - handles `stop_reason`: `end_turn`, `tool_use` (all tool_results go back in one user message), `pause_turn`, `refusal`, `max_tokens`
  - SDK errors are caught most-specific first
- `RuleBasedBackend`, which turns text into tool calls with regexes (the offline default)
- `MockBackend`, which replays scripted tool calls for the tests

## Milestone G — Tests, demo, reflection
- **Unit tests**:
  - schemas: regex, dates, AE conditional fields, extra-field rejection
  - auto-repair
  - PII guard
  - refgen uniqueness, including under concurrency
  - every valid and invalid workflow transition
  - HITL freeze
  - audit triggers block UPDATE and DELETE; `verify_chain` catches edits
  - router classification table
  - guardrail refusals
  - circuit breaker: 3 identical invalid calls → halt; valid call resets
  - BM25 exact-lot hit
  - RRF math (k=60)
  - the 0.40 threshold, using a fake cross-encoder
  - the hook script's output contains no content fields
- **Integration tests** use a temp SQLite DB:
  - intake → dashboard query → In Review → pending approval → approve → Closed, with the audit trail checked
  - an agent loop with `MockBackend`, including a circuit trip
  - `@pytest.mark.models` full RAG run: 'difficulty breathing' retrieves the dyspnea SOP, and `LOT-88392` retrieves the right report
- **Demo** (`docs/demo/`):
  - seed two fictional reports (one AE, one PQC)
  - one status transition with approval
  - a RAG query with the per-stage table
  - an audit-log export
  - an excerpt of `claude_edit_audit.jsonl`
  - evidence of a `/pharma-intake-review` run, using screenshots or Markdown captures
- `docs/reflection.md` answers the 5 defense questions in Section 8.

## Verification
1. `pip install -r requirements.txt`, then `python scripts/download_models.py`, then `python scripts/seed_data.py` and `python scripts/build_index.py`.
2. Run `pytest -q`, then `pytest -q -m models` once the models are downloaded.
3. Run `streamlit run app.py`:
   - submit invalid reports (bad lot, missing onset date, an email address in the description) and check the messages
   - submit valid AE and PQC reports
   - filter the dashboard
   - move New → In Review → Closed and confirm the report stays frozen until approval
   - query "difficulty breathing" and `LOT-88392`
   - confirm the audit chain check passes
4. Confirm `logs/claude_edit_audit.jsonl` grew after edits and contains no file content.
5. Optional: run with `PHARMA_ENABLE_CLAUDE=1` and a credential, and check that the Claude path drives `submit_intake_report` / `update_status` through the same validators.
