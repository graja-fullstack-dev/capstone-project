"""PostToolUse governance hook: append one metadata-only line per file edit.

Deterministic and content-free: records tool name, repo-relative path, UTC
timestamp, session id, sequence number and a hash link to the previous line.
It NEVER records file content, diffs, prompts or descriptions.
Always exits 0 so it can never block development.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = Path(os.environ.get("PHARMA_EDIT_AUDIT_LOG", ROOT / "logs" / "claude_edit_audit.jsonl"))
ALLOWED_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def build_event(payload: dict, prev_line: str, seq: int) -> dict:
    tool_input = payload.get("tool_input") or {}
    raw_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    try:
        rel = str(Path(raw_path).resolve().relative_to(ROOT)).replace("\\", "/")
    except (ValueError, OSError):
        rel = "<outside-repo>"
    return {
        "event_seq": seq,
        "ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session_id": str(payload.get("session_id", "unknown")),
        "tool_name": str(payload.get("tool_name", "unknown")),
        "file_path": rel,
        "prev_sha256": hashlib.sha256(prev_line.encode("utf-8")).hexdigest(),
    }


def append_event(payload: dict) -> dict | None:
    if payload.get("tool_name") not in ALLOWED_TOOLS:
        return None
    LOG.parent.mkdir(parents=True, exist_ok=True)
    prev_line, seq = "", 1
    if LOG.exists():
        lines = LOG.read_text(encoding="utf-8").splitlines()
        if lines:
            prev_line, seq = lines[-1], len(lines) + 1
    event = build_event(payload, prev_line, seq)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def main() -> int:
    try:
        append_event(json.load(sys.stdin))
    except Exception:  # never block the tool call
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
