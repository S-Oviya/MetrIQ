"""
MetrIQ P5 Test Attempt & Retest Models
======================================
Person 5: Workflow + Evidence Engineer

Defines domain entities, lifecycle statuses, and attempt tracking structures
for statutory NAWI test executions and non-destructive retest handling.
Integrates with P4 Verdict results (PASS / FAIL / INCONCLUSIVE) without duplicating calculation logic.
"""

from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import uuid

# Re-export and integrate Person 4 Verdict
from app.calculations.models import Verdict


class AttemptStatus(str, Enum):
    """Lifecycle status of a single test attempt."""
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

    @classmethod
    def from_value(cls, val: Any) -> "AttemptStatus":
        if isinstance(val, cls):
            return val
        if hasattr(val, "value"):
            val = val.value
        clean = str(val or "IN_PROGRESS").strip().upper().replace("-", "_").replace(" ", "_")
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        return cls.IN_PROGRESS


@dataclass
class TestAttempt:
    """
    Test Attempt entity tracking a single sequential attempt of a specific Test
    within a Test Job. Preserves immutable history across multiple attempts (retests).
    """
    __test__ = False  # Avoid pytest collection warning

    id: str
    test_id: str
    job_id: str
    attempt_number: int
    status: AttemptStatus = AttemptStatus.IN_PROGRESS
    result: Optional[Verdict] = None
    entered_values: Dict[str, Any] = dc_field(default_factory=dict)
    test_run_id: Optional[str] = None
    result_data: Optional[Dict[str, Any]] = None
    reason: str = ""
    comments: str = ""
    operator: str = ""
    completed_by: Optional[str] = None
    started_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    created_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def attempt_id(self) -> str:
        """Alias for id."""
        return self.id

    @property
    def user(self) -> str:
        """Alias for operator."""
        return self.operator

    @property
    def is_completed(self) -> bool:
        """Indicates whether this attempt has finished execution."""
        return self.status == AttemptStatus.COMPLETED or self.completed_at is not None

    @property
    def is_pass(self) -> bool:
        """Convenience property indicating whether the attempt passed."""
        return self.result == Verdict.PASS

    @property
    def is_fail(self) -> bool:
        """Convenience property indicating whether the attempt failed."""
        return self.result == Verdict.FAIL

    def to_dict(self) -> Dict[str, Any]:
        """Serializes TestAttempt entity to a dictionary."""
        return {
            "id": self.id,
            "attempt_id": self.id,
            "test_id": self.test_id,
            "job_id": self.job_id,
            "attempt_number": self.attempt_number,
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "result": self.result.value if isinstance(self.result, Enum) else (str(self.result) if self.result else None),
            "entered_values": dict(self.entered_values),
            "test_run_id": self.test_run_id,
            "result_data": self.result_data,
            "reason": self.reason,
            "comments": self.comments,
            "operator": self.operator,
            "user": self.operator,
            "completed_by": self.completed_by,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestAttempt":
        """Reconstructs TestAttempt entity from a dictionary."""
        status_raw = data.get("status") or "IN_PROGRESS"
        result_raw = data.get("result")
        res_enum: Optional[Verdict] = None
        if result_raw:
            try:
                res_enum = Verdict(str(result_raw).strip().upper())
            except ValueError:
                res_enum = None

        return cls(
            id=str(data.get("id") or data.get("attempt_id") or f"ATT-{uuid.uuid4().hex[:8].upper()}"),
            test_id=str(data.get("test_id", "")),
            job_id=str(data.get("job_id", "")),
            attempt_number=int(data.get("attempt_number", 1)),
            status=AttemptStatus.from_value(status_raw),
            result=res_enum,
            entered_values=dict(data.get("entered_values", {})),
            test_run_id=data.get("test_run_id"),
            result_data=data.get("result_data"),
            reason=str(data.get("reason", "")),
            comments=str(data.get("comments", "")),
            operator=str(data.get("operator") or data.get("user") or ""),
            completed_by=data.get("completed_by"),
            started_at=str(data.get("started_at") or datetime.now(timezone.utc).isoformat()),
            completed_at=data.get("completed_at"),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            updated_at=str(data.get("updated_at") or datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class RetestRequest:
    """
    Audit record for a statutory retest request following a failed test attempt.
    """
    __test__ = False

    retest_id: str
    job_id: str
    test_id: str
    attempt_id: str
    attempt_number: int
    reason: str
    requested_by: str
    requested_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = dc_field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "retest_id": self.retest_id,
            "job_id": self.job_id,
            "test_id": self.test_id,
            "attempt_id": self.attempt_id,
            "attempt_number": self.attempt_number,
            "reason": self.reason,
            "requested_by": self.requested_by,
            "requested_at": self.requested_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RetestRequest":
        return cls(
            retest_id=str(data.get("retest_id") or f"RET-{uuid.uuid4().hex[:8].upper()}"),
            job_id=str(data.get("job_id", "")),
            test_id=str(data.get("test_id", "")),
            attempt_id=str(data.get("attempt_id", "")),
            attempt_number=int(data.get("attempt_number", 1)),
            reason=str(data.get("reason", "")),
            requested_by=str(data.get("requested_by") or data.get("operator") or "SYSTEM"),
            requested_at=str(data.get("requested_at") or datetime.now(timezone.utc).isoformat()),
            metadata=dict(data.get("metadata", {})),
        )
