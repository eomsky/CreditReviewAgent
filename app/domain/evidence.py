"""Normalized evidence and validation contracts used across the workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class EvidenceSourceType(StrEnum):
    STRUCTURED_DB = "structured_db"
    CASE_DOCUMENT = "case_document"
    POLICY_DOCUMENT = "policy_document"
    ATTACHMENT = "attachment"


class ValueType(StrEnum):
    ACTUAL = "actual"
    FORECAST = "forecast"
    ESTIMATE = "estimate"
    UNKNOWN = "unknown"


class IssueType(StrEnum):
    FACTUAL_ERROR = "factual_error"
    NUMERIC_ERROR = "numeric_error"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    RISK_OMISSION = "risk_omission"
    WRITING_ISSUE = "writing_issue"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    SOURCE_CONFLICT = "source_conflict"
    VALIDATION_FAILURE = "validation_failure"


class WorkflowStatus(StrEnum):
    RUNNING = "running"
    APPROVED = "approved"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    FAILED = "failed"


@dataclass(slots=True)
class Evidence:
    evidence_id: str
    source_type: EvidenceSourceType
    source_id: str
    case_id: str | None
    title: str
    content: str
    document_id: str | None = None
    filename: str | None = None
    page: int | None = None
    section: str | None = None
    chunk_id: str | None = None
    as_of_date: str | None = None
    period: str | None = None
    value_type: ValueType = ValueType.UNKNOWN
    metric: str | None = None
    value: float | str | None = None
    retrieval_score: float | None = None
    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_prompt_block(self) -> str:
        location = "/".join(str(item) for item in (self.page, self.section, self.chunk_id) if item)
        return f"[EVIDENCE {self.evidence_id} | {self.source_type} | {self.title} | {location or '-'}]\n{self.content}"


@dataclass(slots=True)
class EvidenceConflict:
    conflict_key: str
    evidence_ids: list[str]
    values: list[float | str]
    message: str


@dataclass(slots=True)
class ValidationIssue:
    type: IssueType
    message: str
    evidence_ids: list[str] = field(default_factory=list)

