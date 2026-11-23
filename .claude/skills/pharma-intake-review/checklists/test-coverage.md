# Test coverage checklist

- [ ] Schema tests: lot/ref/reviewer regexes, date rules, AE conditional fields, `extra="forbid"`.
- [ ] Auto-repair and PII-guard tests, including repair reporting.
- [ ] Reference IDs are unique, including under concurrent creation.
- [ ] Every valid and invalid workflow transition is tested; HITL freeze while approval pending.
- [ ] Audit: UPDATE/DELETE blocked; tampering detected by `verify_chain()`.
- [ ] Router classification table and guardrail refusals (causality, treatment, reportability).
- [ ] Circuit breaker: 3rd identical invalid call halts; valid call resets the counter.
- [ ] RAG: BM25 exact lot hit, RRF math (k=60), 0.40 threshold with a fake cross-encoder; model-backed tests marked `@pytest.mark.models`.
- [ ] Integration: intake -> dashboard -> In Review -> pending -> approve -> Closed using a temp DB; agent loop with `MockBackend`.
- [ ] Hook test proves output contains no content fields.
- [ ] Tests never touch `logs/app.db` or the network.
