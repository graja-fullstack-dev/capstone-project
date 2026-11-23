"""Non-clinical scope guardrail. Runs before routing and before any tool/LLM call."""
from __future__ import annotations

import re

_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("causality", re.compile(
        r"(?i)\b(causal(ity)?|(did|does|do|could|can|might)\b.{0,40}\bcaus(e|ed|ing)\b|caused by|due to the (drug|product|medicine)|"
        r"related to the (drug|product|medicine)|attributable to)")),
    ("treatment", re.compile(
        r"(?i)\b(what should (the|a|my) (patient|person)|should (the|a) patient|recommend(ed)? (a )?(treatment|therapy|medication|dose)|"
        r"(treatment|therapy) (for|plan)|how (do|should) (we|i|you) treat|dosage (for|of)|prescribe|antidote)\b")),
    ("reportability", re.compile(
        r"(?i)\b(is (this|it) reportable|reportab(le|ility)|required to report|must (we|i) report|report (this )?to (the )?(fda|ema|mhra|regulator|authority)|"
        r"expedited report|serious(ness)? (assessment|criteria)|15-day)\b")),
]

REFUSALS = {
    "causality": "I can't assess causality between a product and an event. That judgement belongs to qualified safety professionals.",
    "treatment": "I can't recommend medical treatment or dosing. Please refer to qualified medical professionals.",
    "reportability": "I can't determine regulatory reportability. That decision belongs to the enterprise pharmacovigilance process.",
}


def check_scope(text: str) -> tuple[str, str] | None:
    """Return (category, refusal message) if the request is out of scope, else None."""
    for category, pat in _RULES:
        if pat.search(text or ""):
            return category, REFUSALS[category] + " I can log intake reports, track status, and look up SOPs and past records."
    return None
