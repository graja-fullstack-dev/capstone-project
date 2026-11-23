import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude" / "hooks" / "audit_file_edit.py"


def run_hook(tmp_path, payload):
    log = tmp_path / "edits.jsonl"
    import os
    env = {**os.environ, "PHARMA_EDIT_AUDIT_LOG": str(log)}
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), text=True, capture_output=True, env=env)
    return p.returncode, log


def test_hook_records_metadata_only_and_chains(tmp_path):
    secret = "SECRET DESCRIPTION patient text"
    payload = {"session_id": "s1", "tool_name": "Edit",
               "tool_input": {"file_path": str(ROOT / "pharma_intake" / "schemas.py"),
                              "old_string": secret, "new_string": secret, "content": secret}}
    rc, log = run_hook(tmp_path, payload)
    assert rc == 0
    run_hook(tmp_path, payload)
    text = log.read_text()
    lines = text.splitlines()
    assert len(lines) == 2 and secret not in text
    first, second = map(json.loads, lines)
    assert set(first) == {"event_seq", "ts_utc", "session_id", "tool_name", "file_path", "prev_sha256"}
    assert first["file_path"] == "pharma_intake/schemas.py" and second["event_seq"] == 2
    assert second["prev_sha256"] == hashlib.sha256(lines[0].encode()).hexdigest()


def test_hook_ignores_other_tools_and_never_fails(tmp_path):
    rc, log = run_hook(tmp_path, {"tool_name": "Read", "tool_input": {"file_path": "x"}})
    assert rc == 0 and not log.exists()
    p = subprocess.run([sys.executable, str(HOOK)], input="not json", text=True, capture_output=True)
    assert p.returncode == 0
