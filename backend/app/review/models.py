"""
MetrIQ P5 Review & Approval Domain Models
=========================================
Person 5: Workflow + Evidence Engineer

Defines domain entities, enums, and schema structures for statutory review
and supervisory approval of Legal Metrology test jobs.
"""

from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import uuid


class ReviewStatus(str, Enum):
    """Lifecycle status for a review record."""
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"

    @classmethod
    def from_value(cls, val: Any) -> "ReviewStatus":
        if isinstance(val, cls):
            return val
        if hasattr(val, "value"):
            val = val.value
        clean = str(val or "PENDING").strip().upper()
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        return cls.PENDING


class ReviewDecision(str, Enum):
    """
    Statutory decisions available to an authorized reviewer:
    - APPROVE: Job approved for certification and report generation (REVIEW -> APPROVED)
    - REJECT: Job rejected due to non-compliance (REVIEW -> REJECTED)
    - RETURN_FOR_CORRECTION: Job returned for rework/additional tests (REVIEW -> IN_PROGRESS)
    """
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    RETURN_FOR_CORRECTION = "RETURN_FOR_CORRECTION"

    @classmethod
    def from_value(cls, val: Any) -> "ReviewDecision":
        if isinstance(val, cls):
            return val
        if hasattr(val, "value"):
            val = val.value
        clean = str(val or "").strip().upper().replace("-", "_").replace(" ", "_")
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        if clean in ("APPROVED", "ACCEPT", "ACCEPTED", "PASS"):
            return cls.APPROVE
        if clean in ("REJECTED", "FAIL", "FAILED", "DISAPPROVED"):
            return cls.REJECT
        if clean in ("RETURN", "CORRECTION", "REWORK", "REQUEST_CHANGES", "RETURNED"):
            return cls.RETURN_FOR_CORRECTION
        raise ValueError(
            f"Invalid review decision '{val}'. Permitted decisions: {[m.value for m in cls]}"
        )


class ReviewRole(str, Enum):
    """Statutory role definitions for authorization and four-eyes review."""
    OPERATOR = "OPERATOR"
    REVIEWER = "REVIEWER"
    SENIOR_INSPECTOR = "SENIOR_INSPECTOR"
    CONTROLLER = "CONTROLLER"
    LEGAL_METROLOGY_OFFICER = "LEGAL_METROLOGY_OFFICER"
    SUPERVISOR = "SUPERVISOR"
    ADMIN = "ADMIN"

    @classmethod
    def from_value(cls, val: Any) -> "ReviewRole":
        if isinstance(val, cls):
            return val
        if hasattr(val, "value"):
            val = val.value
        clean = str(val or "OPERATOR").strip().upper().replace("-", "_").replace(" ", "_")
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        return cls.OPERATOR

    @property
    def is_authorized_reviewer(self) -> bool:
        """Determines if the role possesses review and approval authority."""
        return self != ReviewRole.OPERATOR


@dataclass
class Review:
    """
    Central Review entity tracking a supervisory review cycle on a Test Job.
    Preserves audit history across multiple submission/rejection/rework cycles.
    """
    __test__ = False  # Avoid pytest collection warning

    id: str
    job_id: str
    reviewer: str = "UNASSIGNED"
    status: ReviewStatus = ReviewStatus.PENDING
    decision: Optional[ReviewDecision] = None
    comments: str = ""
    reviewed_at: Optional[str] = None
    created_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = dc_field(default_factory=dict)

    @property
    def review_id(self) -> str:
        """Alias for id."""
        return self.id

    @property
    def reviewer_id(self) -> str:
        """Alias for reviewer."""
        return self.reviewer

    @property
    def decision_date(self) -> Optional[str]:
        """Alias for reviewed_at."""
        return self.reviewed_at

    def to_dict(self) -> Dict[str, Any]:
        """Converts Review entity to dictionary representation."""
        return {
            "id": self.id,
            "review_id": self.id,
            "job_id": self.job_id,
            "reviewer": self.reviewer,
            "reviewer_id": self.reviewer,
            "status": self.status.value,
            "decision": self.decision.value if self.decision else None,
            "comments": self.comments,
            "reviewed_at": self.reviewed_at,
            "decision_date": self.reviewed_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Review":
        """Reconstructs Review entity from dictionary."""
        r_id = str(data.get("id") or data.get("review_id") or f"REV-{uuid.uuid4().hex[:8].upper()}")
        job_id = str(data.get("job_id") or "")
        reviewer = str(data.get("reviewer") or data.get("reviewer_id") or "UNASSIGNED")
        status = ReviewStatus.from_value(data.get("status", "PENDING"))
        decision_val = data.get("decision")
        decision = ReviewDecision.from_value(decision_val) if decision_val else None

        return cls(
            id=r_id,
            job_id=job_id,
            reviewer=reviewer,
            status=status,
            decision=decision,
            comments=str(data.get("comments") or ""),
            reviewed_at=data.get("reviewed_at") or data.get("decision_date"),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            updated_at=str(data.get("updated_at") or datetime.now(timezone.utc).isoformat()),
            metadata=dict(data.get("metadata") or {}),
        )
