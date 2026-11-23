"""Pydantic v2 schemas. All inputs (UI and agent tools) validate through these."""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LOT_PATTERN = r"^LOT-\d{5}$"
REF_PATTERN = r"^REF-\d{4}-\d{4}$"
REVIEWER_PATTERN = r"^REV-\d{2}$"


class ReportType(str, Enum):
    AE = "Suspected Adverse Event"
    PQC = "Product Quality Complaint"


class Status(str, Enum):
    NEW = "New"
    IN_REVIEW = "In Review"
    CLOSED = "Closed"


class ReporterType(str, Enum):
    HCP = "Healthcare Professional"
    CONSUMER = "Consumer"
    SALES = "Sales Representative"
    OTHER = "Other"


class Channel(str, Enum):
    EMAIL = "Email"
    TELEPHONE = "Telephone"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, use_enum_values=False)


class SubmitIntakeReportArgs(_Strict):
    """Intake payload (also the `submit_intake_report` tool schema)."""

    report_type: ReportType
    product_name: str = Field(min_length=2, max_length=120)
    batch_id: str = Field(pattern=LOT_PATTERN, description="Format LOT-12345")
    date_received: date
    reporter_type: ReporterType
    channel: Channel
    description: str = Field(min_length=20, max_length=2000)
    event_description: Optional[str] = Field(default=None, min_length=10, max_length=1000)
    event_onset_date: Optional[date] = None

    @field_validator("date_received")
    @classmethod
    def _not_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("Date received cannot be in the future")
        return v

    @model_validator(mode="after")
    def _ae_rules(self) -> "SubmitIntakeReportArgs":
        if self.report_type == ReportType.AE:
            if not self.event_description:
                raise ValueError("Event description is required for Suspected Adverse Events")
            if self.event_onset_date is None:
                raise ValueError("Event onset date is required for Suspected Adverse Events")
            if self.event_onset_date > self.date_received:
                raise ValueError("Event onset date cannot be after the date received")
        elif self.event_description or self.event_onset_date:
            raise ValueError("Event description/onset date apply only to Suspected Adverse Events")
        return self


class UpdateStatusArgs(_Strict):
    """`update_status` tool schema: request a lifecycle transition."""

    ref_id: str = Field(pattern=REF_PATTERN, description="Format REF-2026-0001")
    target_status: Status
    reviewer_code: str = Field(pattern=REVIEWER_PATTERN, description="Format REV-01")
    note: Optional[str] = Field(default=None, max_length=300)


class SearchKnowledgeArgs(_Strict):
    """`search_knowledge` tool schema: hybrid RAG over SOPs and saved reports."""

    query: str = Field(min_length=3, max_length=300)


class ApprovalDecisionArgs(_Strict):
    ref_id: str = Field(pattern=REF_PATTERN)
    reviewer_code: str = Field(pattern=REVIEWER_PATTERN)
    approve: bool
