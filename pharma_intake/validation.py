"""Auto-repair, PII guard, and context-sensitive error messages."""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ValidationError

from .schemas import (
    REF_PATTERN, Channel, ReporterType, ReportType, Status, SubmitIntakeReportArgs,
)

FIELD_LABELS = {
    "report_type": "Report type",
    "product_name": "Product name",
    "batch_id": "Batch/Lot number",
    "date_received": "Date received",
    "reporter_type": "Reporter type",
    "channel": "Intake channel",
    "description": "Description",
    "event_description": "Event description",
    "event_onset_date": "Event onset date",
    "ref_id": "Reference ID",
    "target_status": "Target status",
    "reviewer_code": "Reviewer code",
    "note": "Note",
    "query": "Query",
}
FIELD_HINTS = {
    "batch_id": "must look like LOT-12345 (LOT- followed by exactly 5 digits)",
    "ref_id": "must look like REF-2026-0001",
    "reviewer_code": "must look like REV-01",
    "description": "must be between 20 and 2000 characters",
    "event_description": "must be between 10 and 1000 characters",
    "product_name": "must be between 2 and 120 characters",
    "query": "must be between 3 and 300 characters",
}

_ENUM_ALIASES: dict[str, dict[str, Any]] = {
    "report_type": {
        "ae": ReportType.AE, "adverse event": ReportType.AE, "suspected adverse event": ReportType.AE,
        "pqc": ReportType.PQC, "quality complaint": ReportType.PQC, "product quality complaint": ReportType.PQC,
    },
    "reporter_type": {
        "hcp": ReporterType.HCP, "healthcare professional": ReporterType.HCP, "health care professional": ReporterType.HCP,
        "consumer": ReporterType.CONSUMER, "sales rep": ReporterType.SALES,
        "sales representative": ReporterType.SALES, "other": ReporterType.OTHER,
    },
    "channel": {"email": Channel.EMAIL, "e-mail": Channel.EMAIL, "phone": Channel.TELEPHONE,
                "telephone": Channel.TELEPHONE, "call": Channel.TELEPHONE},
    "target_status": {"new": Status.NEW, "in review": Status.IN_REVIEW, "review": Status.IN_REVIEW,
                      "in-review": Status.IN_REVIEW, "closed": Status.CLOSED, "close": Status.CLOSED},
}


def repair_lot(value: str) -> str | None:
    m = re.fullmatch(r"(?i)\s*lot[\s_-]*(\d{5})\s*", value)
    return f"LOT-{m.group(1)}" if m else None


def repair_ref(value: str) -> str | None:
    m = re.fullmatch(r"(?i)\s*ref[\s_-]*(\d{4})[\s_-]*(\d{1,4})\s*", value)
    return f"REF-{m.group(1)}-{int(m.group(2)):04d}" if m else None


def repair_payload(raw: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalize obvious typos. Returns (repaired_copy, human-readable repair notes)."""
    data, notes = dict(raw), []
    for key, val in list(data.items()):
        if isinstance(val, str):
            stripped = val.strip()
            if stripped != val:
                data[key] = val = stripped
    if isinstance(data.get("batch_id"), str):
        fixed = repair_lot(data["batch_id"])
        if fixed and fixed != data["batch_id"]:
            notes.append(f"Batch/Lot number '{data['batch_id']}' normalized to '{fixed}'")
            data["batch_id"] = fixed
    if isinstance(data.get("ref_id"), str):
        fixed = repair_ref(data["ref_id"])
        if fixed and fixed != data["ref_id"]:
            notes.append(f"Reference ID '{data['ref_id']}' normalized to '{fixed}'")
            data["ref_id"] = fixed
    if isinstance(data.get("reviewer_code"), str):
        m = re.fullmatch(r"(?i)rev[\s_-]*(\d{1,2})", data["reviewer_code"])
        if m:
            fixed = f"REV-{int(m.group(1)):02d}"
            if fixed != data["reviewer_code"]:
                notes.append(f"Reviewer code '{data['reviewer_code']}' normalized to '{fixed}'")
                data["reviewer_code"] = fixed
    for key, aliases in _ENUM_ALIASES.items():
        v = data.get(key)
        if isinstance(v, str):
            hit = aliases.get(v.strip().lower())
            if hit is not None and hit.value != v:
                notes.append(f"{FIELD_LABELS[key]} '{v}' interpreted as '{hit.value}'")
                data[key] = hit.value
    return data, notes


# --- PII guard (synthetic-data enforcement) ---
_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("an email address", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("a phone number", re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")),
    ("a date of birth", re.compile(r"(?i)\b(dob|date of birth|born on)\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b")),
    ("a patient identifier", re.compile(r"(?i)\b(patient'?s? (full )?name|patient initials|mrn|medical record( number)?|ssn|social security|my name is)\b")),
    ("an address", re.compile(r"(?i)\b\d{1,5}\s+\w+(\s\w+)?\s(street|st|avenue|ave|road|rd|lane|ln|drive|dr)\b")),
]


def find_pii(text: str) -> list[str]:
    return [label for label, pat in _PII_PATTERNS if pat.search(text or "")]


def pii_errors(data: dict[str, Any]) -> list[str]:
    errs = []
    for key in ("description", "event_description", "note", "product_name"):
        v = data.get(key)
        if isinstance(v, str):
            for label in find_pii(v):
                errs.append(
                    f"{FIELD_LABELS[key]} appears to contain {label}. This prototype accepts "
                    "fictional, de-identified text only - remove personal details and resubmit."
                )
    return errs


def format_errors(exc: ValidationError) -> list[str]:
    """Turn Pydantic errors into explicit, field-aware messages."""
    out: list[str] = []
    for e in exc.errors():
        loc = e["loc"][0] if e["loc"] else None
        msg, typ = e["msg"], e["type"]
        if typ == "extra_forbidden":
            out.append(f"Unknown field '{loc}' is not allowed")
            continue
        if loc is None:
            out.append(msg.removeprefix("Value error, "))
            continue
        label = FIELD_LABELS.get(str(loc), str(loc))
        got = e.get("input")
        if typ == "missing":
            out.append(f"{label} is required but missing")
        elif typ in ("string_pattern_mismatch", "string_too_short", "string_too_long"):
            hint = FIELD_HINTS.get(str(loc), "has an invalid format")
            shown = "" if got in (None, "") else f" (you entered '{str(got)[:40]}')"
            out.append(f"{label} {hint}{shown}")
        elif typ.startswith("enum"):
            out.append(f"{label} '{got}' is not a valid choice: {msg.split(':', 1)[-1].strip()}")
        elif typ.startswith("date"):
            out.append(f"{label} must be a valid date in YYYY-MM-DD format (you entered '{got}')")
        else:
            out.append(f"{label}: {msg.removeprefix('Value error, ')}")
    return out


class ValidationOutcome(BaseModel):
    ok: bool
    model: Any | None = None
    errors: list[str] = []
    repairs: list[str] = []


def validate_with(model_cls: type[BaseModel], raw: dict[str, Any], check_pii: bool = True) -> ValidationOutcome:
    """Repair -> validate -> PII guard. Single entry point for UI and agent tools."""
    data, repairs = repair_payload(raw)
    try:
        obj = model_cls.model_validate(data)
    except ValidationError as exc:
        return ValidationOutcome(ok=False, errors=format_errors(exc) + (pii_errors(data) if check_pii else []), repairs=repairs)
    errs = pii_errors(data) if check_pii else []
    if errs:
        return ValidationOutcome(ok=False, errors=errs, repairs=repairs)
    return ValidationOutcome(ok=True, model=obj, repairs=repairs)


def validate_intake(raw: dict[str, Any]) -> ValidationOutcome:
    return validate_with(SubmitIntakeReportArgs, raw)


__all__ = ["REF_PATTERN", "validate_intake", "validate_with", "repair_payload", "find_pii", "format_errors"]
