---
name: pharma-intake-review
description: Review code in the Pharma Safety Intake & Triage Tracker for data minimization, error handling, auditability and test coverage. Use when reviewing a milestone, a diff, or before declaring work done.
---

# Pharma Intake Review

Review the target (current diff, a file, or a milestone) against the four checklists. Read each checklist file before judging that dimension:

1. [checklists/data-minimization.md](checklists/data-minimization.md)
2. [checklists/error-handling.md](checklists/error-handling.md)
3. [checklists/auditability.md](checklists/auditability.md)
4. [checklists/test-coverage.md](checklists/test-coverage.md)

Also confirm the hard scope limits in the root `CLAUDE.md` (non-clinical, fictional data, local-only).

## Output format

Report a findings table, most severe first. Cite real `file:line` locations only; do not invent findings.

| Severity | Checklist item | file:line | Finding | Suggested fix |
|---|---|---|---|---|

Severity: **blocker** (violates a hard scope limit or breaks an invariant), **major**, **minor**. End with a one-line verdict per checklist (PASS / FAIL) and the test command to re-verify (`pytest -q`).
