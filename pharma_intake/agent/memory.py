"""Step 2: dual-memory engine. Short-term = volatile ReAct trace; long-term = SQLite (repository + audit)."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from .. import audit, repository


@dataclass
class TraceStep:
    kind: str   # "Thought" | "Action" | "Observation"
    text: str


@dataclass
class ShortTermMemory:
    """Volatile Thought-Action-Observation trace for the current multi-step run (never persisted)."""
    steps: list[TraceStep] = field(default_factory=list)

    def add(self, kind: str, text: str) -> None:
        self.steps.append(TraceStep(kind, text[:500]))

    def clear(self) -> None:
        self.steps.clear()

    def render(self) -> list[dict]:
        return [{"step": i + 1, "type": s.kind, "text": s.text} for i, s in enumerate(self.steps)]


class LongTermMemory:
    """Persistent report state, status transition logs and audit histories (SQLite)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def report(self, ref_id: str) -> dict | None:
        return repository.get_report(self.conn, ref_id)

    def history(self, ref_id: str) -> list[dict]:
        return audit.list_events(self.conn, ref_id)
