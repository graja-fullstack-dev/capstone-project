# Auditability checklist

- [ ] Every create, status change, approval, rejection, refusal and circuit-open event writes an audit row via `audit.py`.
- [ ] `audit_log` has BEFORE UPDATE/DELETE triggers; no code path issues UPDATE/DELETE on it.
- [ ] Rows are hash-chained and `verify_chain()` is exercised by tests and shown on the Audit Log page.
- [ ] Audit write and the state change happen in the same transaction.
- [ ] Timestamps are UTC ISO-8601; reviewer approvals record the reviewer code.
- [ ] In Review -> Closed cannot complete without an `APPROVED` audit record from a human; agents cannot approve.
- [ ] The edit-audit hook is registered in `.claude/settings.json` and its log is hash-linked and content-free.
