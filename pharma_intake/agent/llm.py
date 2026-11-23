"""LLM backends behind one interface: offline rule-based (default), scripted mock (tests), Claude (opt-in)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from .. import config
from .router import REF_RE, Route


@dataclass
class ToolCall:
    id: str
    name: str
    args: Any


@dataclass
class Turn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_content: Any = None          # what to append as the assistant message (blocks preserved unchanged)
    stop_reason: str = "end_turn"


class LLMBackend(Protocol):
    name: str

    def respond(self, system: str, messages: list[dict], tools: list[dict], route: Route) -> Turn: ...


def _text_of(msg: dict) -> str:
    c = msg["content"]
    return c if isinstance(c, str) else ""


def _tool_results(messages: list[dict]) -> list[dict] | None:
    last = messages[-1]
    if last["role"] == "user" and isinstance(last["content"], list):
        return [b for b in last["content"] if isinstance(b, dict) and b.get("type") == "tool_result"]
    return None


def summarize_results(results: list[dict]) -> str:
    parts = []
    for r in results:
        try:
            data = json.loads(r["content"])
        except (ValueError, TypeError):
            data = {"raw": r["content"]}
        if r.get("is_error"):
            details = data.get("details") or [data.get("error", "unknown error")]
            parts.append("I could not complete that request:\n- " + "\n- ".join(map(str, details)))
        elif data.get("status") == "saved":
            parts.append(f"Report saved with reference {data['ref_id']} (status {data['report_status']}).")
        elif data.get("status") == "awaiting_human_approval":
            parts.append(f"{data['ref_id']}: {data['message']}")
        elif data.get("status") == "updated":
            parts.append(f"{data['ref_id']} is now '{data['report_status']}'.")
        else:
            parts.append(json.dumps(data))
    return "\n".join(parts)


# ---------------- offline rule-based backend (default) ----------------
_KV_ALIASES = {
    "type": "report_type", "report_type": "report_type", "category": "report_type",
    "product": "product_name", "product_name": "product_name",
    "lot": "batch_id", "batch": "batch_id", "batch_id": "batch_id", "batch/lot": "batch_id",
    "date": "date_received", "date_received": "date_received", "received": "date_received",
    "reporter": "reporter_type", "reporter_type": "reporter_type",
    "channel": "channel",
    "description": "description", "desc": "description",
    "event": "event_description", "event_description": "event_description",
    "onset": "event_onset_date", "event_onset_date": "event_onset_date",
}
_INTAKE_HELP = ("To log a report from chat, give key=value pairs separated by ';', for example:\n"
                "log report: type=Product Quality Complaint; product=Fictazol 10 mg Tablets; lot=LOT-45210; "
                "date=2026-03-04; reporter=Consumer; channel=Email; description=Fictional note about damaged blister strip.\n"
                "Adverse events also need event=... and onset=YYYY-MM-DD. Or use the Intake page.")


class RuleBasedBackend:
    """Deterministic text -> tool-call translator. Offline; no external calls."""
    name = "rule-based (offline)"

    def respond(self, system: str, messages: list[dict], tools: list[dict], route: Route) -> Turn:
        results = _tool_results(messages)
        if results is not None:
            return Turn(text=summarize_results(results))
        text = _text_of(messages[-1])
        if route == Route.STATUS:
            return self._status(text)
        return self._intake(text)

    @staticmethod
    def _status(text: str) -> Turn:
        args: dict[str, Any] = {}
        m = REF_RE.search(text)
        if m:
            args["ref_id"] = m.group(0)
        low = text.lower()
        if re.search(r"\bclos", low):
            args["target_status"] = "Closed"
        elif re.search(r"in[\s-]*review|\breview\b", low):
            args["target_status"] = "In Review"
        m = re.search(r"(?i)\brev[\s_-]*\d{1,2}\b", text)
        if m:
            args["reviewer_code"] = m.group(0)
        call = ToolCall("rule_1", "update_status", args)
        return Turn(tool_calls=[call], raw_content=[{"type": "tool_use", "id": call.id, "name": call.name, "input": args}])

    @staticmethod
    def _intake(text: str) -> Turn:
        body = text.split(":", 1)[1] if ":" in text.split("=", 1)[0] else text
        args: dict[str, Any] = {}
        for piece in re.split(r";|\n", body):
            if "=" in piece:
                k, v = piece.split("=", 1)
                key = _KV_ALIASES.get(k.strip().lower())
                if key:
                    args[key] = v.strip()
        if not args:
            return Turn(text=_INTAKE_HELP)
        call = ToolCall("rule_1", "submit_intake_report", args)
        return Turn(tool_calls=[call], raw_content=[{"type": "tool_use", "id": call.id, "name": call.name, "input": args}])


# ---------------- scripted mock (tests) ----------------
class MockBackend:
    name = "mock"

    def __init__(self, script: list[Turn]):
        self.script = list(script)
        self.calls = 0

    def respond(self, system: str, messages: list[dict], tools: list[dict], route: Route) -> Turn:
        self.calls += 1
        if not self.script:
            return Turn(text="(mock script exhausted)")
        turn = self.script.pop(0)
        if turn.raw_content is None and turn.tool_calls:
            turn.raw_content = [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.args} for c in turn.tool_calls]
        return turn


# ---------------- Claude (opt-in) ----------------
class ClaudeBackend:
    """Claude tool use via the official SDK. Enabled only with PHARMA_ENABLE_CLAUDE=1 (external API)."""

    def __init__(self, model: str | None = None, client: Any = None):
        import anthropic  # imported lazily: the app runs without it
        self._anthropic = anthropic
        self.client = client or anthropic.Anthropic()
        self.model = model or config.LLM_MODEL
        self.name = f"Claude ({self.model})"

    def respond(self, system: str, messages: list[dict], tools: list[dict], route: Route) -> Turn:
        a = self._anthropic
        msgs = list(messages)
        try:
            for _ in range(3):  # resume paused turns a bounded number of times
                resp = self.client.beta.messages.create(
                    model=self.model, max_tokens=16000, system=system, tools=tools, messages=msgs,
                    thinking={"type": "adaptive"}, output_config={"effort": "medium"},
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                )
                if resp.stop_reason == "pause_turn":
                    msgs.append({"role": "assistant", "content": resp.content})
                    continue
                break
        except a.AuthenticationError:
            return Turn(text="Claude is enabled but no valid API credential was found. Set ANTHROPIC_API_KEY or unset PHARMA_ENABLE_CLAUDE.", stop_reason="error")
        except a.RateLimitError:
            return Turn(text="Claude rate limit reached. Please retry shortly.", stop_reason="error")
        except a.APIConnectionError:
            return Turn(text="Could not reach the Claude API (network). Unset PHARMA_ENABLE_CLAUDE to use the offline backend.", stop_reason="error")
        except a.APIStatusError as exc:
            return Turn(text=f"Claude API error (HTTP {exc.status_code}).", stop_reason="error")
        if resp.stop_reason == "refusal":
            return Turn(text="The model declined this request.", raw_content=resp.content, stop_reason="refusal")
        text = "\n".join(b.text for b in resp.content if b.type == "text")
        calls = [ToolCall(b.id, b.name, b.input) for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason == "max_tokens":
            text = (text + "\n(The response was cut off at the token limit.)").strip()
        return Turn(text=text, tool_calls=calls, raw_content=resp.content, stop_reason=resp.stop_reason)


def default_backend() -> LLMBackend:
    """Claude only when explicitly enabled AND the SDK is importable; otherwise the offline backend."""
    if config.claude_enabled():
        try:
            return ClaudeBackend()
        except Exception:
            pass
    return RuleBasedBackend()
