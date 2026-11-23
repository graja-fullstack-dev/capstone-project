"""Step 3: deterministic semantic router. Runs BEFORE any tool/LLM call (no model involved)."""
from __future__ import annotations

import re
from enum import Enum

from .. import guardrails

REF_RE = re.compile(r"(?i)\bref[\s_-]*\d{4}[\s_-]*\d{1,4}\b")
_GREETING = re.compile(r"(?i)^\s*(hi|hello|hey|good (morning|afternoon|evening)|thanks|thank you|help|what can you do)\b[\s\S]{0,25}$")
_QUESTION = re.compile(r"(?i)^\s*(what|how|which|when|why|where|who|show|find|search|list|explain|tell me|any|are there|is there)\b|\bsop\b|\?\s*$")
_STATUS_VERB = re.compile(r"(?i)\b(move|set|update|change|close|mark|transition|advance|promote|escalate|start review)\b")
_INTAKE_VERB = re.compile(r"(?i)\b(log|submit|create|file|record|register|new|received|capture)\b")
_INTAKE_NOUN = re.compile(r"(?i)\b(report|complaint|adverse event|intake|case)\b")


class Route(str, Enum):
    DIRECT = "direct_response"
    RAG = "hybrid_rag"
    INTAKE = "intake_form_tool"
    STATUS = "status_workflow_manager"
    REFUSE = "out_of_scope_refusal"


def route(text: str) -> tuple[Route, str | None]:
    """Return (route, refusal_category). Guardrails take precedence over everything."""
    blocked = guardrails.check_scope(text)
    if blocked:
        return Route.REFUSE, blocked[0]
    if _GREETING.match(text):
        return Route.DIRECT, None
    is_question = bool(_QUESTION.search(text))
    if REF_RE.search(text) and _STATUS_VERB.search(text) and not is_question:
        return Route.STATUS, None
    if _INTAKE_VERB.search(text) and _INTAKE_NOUN.search(text) and not is_question:
        return Route.INTAKE, None
    return Route.RAG, None


DIRECT_REPLY = (
    "Hello! I can (1) look up SOPs and past reports (try a lot number like LOT-88392 or a question), "
    "(2) help log a new intake report, and (3) request status changes (e.g. 'move REF-2026-0001 to In Review, "
    "reviewer REV-01'). I never assess causality, advise on treatment, or decide reportability."
)
