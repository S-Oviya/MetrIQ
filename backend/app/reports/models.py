"""Typed report-domain models for the P6 reporting foundation.

These models describe report records only. They intentionally do not calculate
metrology results or make regulatory decisions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp suitable for in-memory records."""
    return datetime.now(timezone.utc).isoformat()


class ReportType(str, Enum):
    OIML_R76_2_TYPE_EVALUATION = "OIML_R76_2_TYPE_EVALUATION"
    GATC_THIRD_SCHEDULE_VERIFICATION = "GATC_THIRD_SCHEDULE_VERIFICATION"
    GENERIC_VERIFICATION = "GENERIC_VERIFICATION"
    REJECTION_DOCUMENT = "REJECTION_DOCUMENT"
    TECHNICAL_EVIDENCE_ANNEX = "TECHNICAL_EVIDENCE_ANNEX"


class ReportStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    ISSUED = "ISSUED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


@dataclass
class ReportMetadata:
    """Traceability fields used for report listing and archive retrieval."""

    report_number: str
    job_id: str
    instrument_id: str
    serial_number: Optional[str] = None
    approval_number: Optional[str] = None
    report_type: ReportType = ReportType.GENERIC_VERIFICATION
    status: ReportStatus = ReportStatus.DRAFT
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    title: str = ""
    state: Optional[str] = None
    testing_centre: Optional[str] = None
    generated_by: Optional[str] = None
    template_name: Optional[str] = None
    template_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["report_type"] = self.report_type.value
        data["status"] = self.status.value
        return data


@dataclass
class Report:
    """A report record with extensible backend-supplied content references."""

    metadata: ReportMetadata
    report_id: str = field(default_factory=lambda: f"RPT-{uuid4().hex[:12].upper()}")
    source_snapshot: Dict[str, Any] = field(default_factory=dict)
    evidence_metadata: Dict[str, Any] = field(default_factory=dict)
    created_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = self.metadata.to_dict()
        data.update({
            "report_id": self.report_id,
            "source_snapshot": dict(self.source_snapshot),
            "evidence_metadata": dict(self.evidence_metadata),
            "created_by": self.created_by,
        })
        return data
