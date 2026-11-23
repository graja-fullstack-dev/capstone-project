# Capstone Defense & Technical Reflection

Draft answers grounded in what was built. Edit them with your own experience of the build before submitting.

## 1. Architectural boundary: CLAUDE.md vs. skills
`CLAUDE.md` holds what must be true on **every** task and is loaded every session: scope limits (non-clinical, fictional data, local only), architecture rules (all status changes go through `workflow.py`, audit is append-only), coding and testing conventions. A skill (`pharma-intake-review`) holds **task-specific procedure** that is only useful when reviewing: four checklists and an output format. Keeping checklists out of CLAUDE.md keeps the always-loaded context short and focused, and lets the review procedure evolve independently. Anything that must hold *deterministically* belongs in code or hooks, not in prose in either file.

## 2. Planning efficiency
Plan Mode forced decisions before code: the data model (separate `ae_details`, append-only `audit_log`), the transition map and where the HITL gate sits, that audit rows store field *names* not values, how the 512/64 chunking and RRF/threshold constants are centralised in `config.py`, and that "no external APIs" conflicts with an LLM-driven agent (resolved with an opt-in backend). Edge cases surfaced early: AE-only fields, onset-after-received, frozen report while approval is pending, four-eyes approval, tool-call retry loops. These each became a test.

## 3. Governance control: why hooks are deterministic
A `PostToolUse` hook is code the harness executes on every matching tool event: same input, same output, no model judgment, cannot be talked out of running. Our hook writes tool name, relative path, timestamp, session id and a hash link, and its test proves no content fields can appear. Model-driven review (the skill) is probabilistic and may miss or vary. Use hooks for invariants and audit; use model review for judgment.

## 4. Multi-stage RAG precision
BM25 nails exact tokens (`LOT-88392`) that embeddings blur; the bi-encoder bridges vocabulary ("difficulty breathing" -> dyspnea SOP) that BM25 misses; RRF merges them without score calibration; the cross-encoder jointly reads query+passage to demote lookalikes, and the 0.40 threshold lets the system return **nothing** rather than a guess (demonstrated by the unrelated-query test). Answers are extractive and cited, so the output is quoted source text. Honest caveat: this *reduces* hallucination and makes it auditable; it does not mathematically eliminate wrong retrieval (e.g. the threshold and models are not validated on real pharmacovigilance data).

## 5. Production readiness
Authentication, role-based access and real reviewer identity (replacing typed `REV-NN` codes); electronic signatures and Part 11/GxP validation; encrypted storage, managed DB, backup/retention and tamper-evidence anchored outside the DB file; PII/PHI handling, privacy review and data-subject processes; validated, version-pinned models with evaluation on representative data; monitoring/alerting; secure deployment (TLS, secrets management); and integration with the enterprise pharmacovigilance system. If the Claude backend were used, a data-processing agreement and review of what leaves the network.
