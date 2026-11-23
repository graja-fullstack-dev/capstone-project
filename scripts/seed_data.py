"""Load the fictional seed reports into the local DB (idempotent: skips if reports already exist)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pharma_intake import config, db, repository, workflow  # noqa: E402
from pharma_intake.schemas import Status  # noqa: E402
from pharma_intake.validation import validate_intake  # noqa: E402


def seed(conn, move_first_to_review: bool = True) -> list[str]:
    if conn.execute("SELECT COUNT(*) AS n FROM reports").fetchone()["n"]:
        return []
    refs = []
    for raw in json.loads(config.SEED_REPORTS.read_text(encoding="utf-8")):
        out = validate_intake(raw)
        if not out.ok:
            raise SystemExit(f"Seed report invalid: {out.errors}")
        refs.append(repository.create_report(conn, out.model, actor="seed-script"))
    if move_first_to_review and refs:
        workflow.request_transition(conn, refs[0], Status.IN_REVIEW, actor="REV-01")
    return refs


if __name__ == "__main__":
    conn = db.connect()
    created = seed(conn)
    print(f"Seeded {len(created)} fictional reports: {', '.join(created)}" if created else "Database already has reports; nothing seeded.")
