# Data minimization checklist

- [ ] No form field, schema field, column or tool argument collects patient name, initials, DOB, address, phone, email, MRN or medical history.
- [ ] Only PDF-specified fields are stored (product, batch/lot, date received, reporter type, description, AE event description + onset date, channel).
- [ ] Free-text fields pass the PII guard (`validation.py`) before persistence.
- [ ] Audit rows hold action, timestamps, ref ID, from/to status and changed field *names* only; never free-text values.
- [ ] Logging uses IDs only; no report descriptions in logs, exceptions, hook output or UI error text.
- [ ] RAG corpus contains only fictional SOPs and report fields (no audit/reviewer data).
- [ ] Seed data, fixtures and docs are obviously synthetic.
- [ ] `.claude/hooks/audit_file_edit.py` writes no file content, diffs or descriptions.
