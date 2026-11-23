# Error handling checklist

- [ ] Every mandatory field has an explicit, context-sensitive message naming the field and the rule (e.g. AE onset date required only for Suspected Adverse Events).
- [ ] Pydantic `ValidationError`s are converted to user-readable messages; no raw tracebacks reach the UI.
- [ ] Invalid transitions raise `InvalidTransition`; the UI shows the allowed next states.
- [ ] Tool-call validation failures return structured `is_error` results, not exceptions that kill the loop.
- [ ] Circuit breaker trips after more than 2 consecutive identical invalid calls and is audited; iteration cap exists.
- [ ] Claude backend handles `refusal`, `max_tokens`, `pause_turn`, and catches SDK errors most-specific first; missing key/flag degrades to the offline backend.
- [ ] RAG returns a clear "no sufficiently relevant record" result below the 0.40 threshold; missing models give an actionable message.
- [ ] DB writes are transactional; a failure leaves no half-created report or orphan audit row.
