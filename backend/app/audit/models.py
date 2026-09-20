"""
MetrIQ P5 Audit Trail & Traceability Domain Models
==================================================
Person 5: Workflow + Evidence Engineer

Defines domain entities, enums, and schema structures for statutory,
immutable, append-only audit trail logging across all Legal Metrology operations.
"""

from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import uuid


class AuditAction(str, Enum):
    """
    Statutory audit actions recording significant lifecycle, calibration,
    evidence, and supervisory decision events.
    """
    # Job Actions
    JOB_CREATED = "JOB_CREATED"
    JOB_STATE_CHANGED = "JOB_STATE_CHANGED"
    JOB_UPDATED = "JOB_UPDATED"
    JOB_VALIDATED = "JOB_VALIDATED"
    TEST_PLAN_GENERATED = "TEST_PLAN_GENERATED"
    INSPECTOR_ASSIGNED = "INSPECTOR_ASSIGNED"
    REPORT_GENERATED = "REPORT_GENERATED"

    # Equipment / Test Standards Actions
    EQUIPMENT_CREATED = "EQUIPMENT_CREATED"
    EQUIPMENT_UPDATED = "EQUIPMENT_UPDATED"
    EQUIPMENT_STATUS_CHANGED = "EQUIPMENT_STATUS_CHANGED"
    TEST_STANDARD_CREATED = "TEST_STANDARD_CREATED"
    TEST_STANDARD_UPDATED = "TEST_STANDARD_UPDATED"
    TEST_STANDARD_STATUS_CHANGED = "TEST_STANDARD_STATUS_CHANGED"
    JOB_EQUIPMENT_ASSOCIATED = "JOB_EQUIPMENT_ASSOCIATED"
    JOB_STANDARD_ASSOCIATED = "JOB_STANDARD_ASSOCIATED"

    # Environment Actions
    ENVIRONMENT_RECORDED = "ENVIRONMENT_RECORDED"
    ENVIRONMENT_UPDATED = "ENVIRONMENT_UPDATED"

    # Test Attempt Actions
    TEST_ATTEMPT_STARTED = "TEST_ATTEMPT_STARTED"
    TEST_ATTEMPT_COMPLETED = "TEST_ATTEMPT_COMPLETED"
    RETEST_REQUESTED = "RETEST_REQUESTED"

    # Evidence Actions
    EVIDENCE_UPLOADED = "EVIDENCE_UPLOADED"
    EVIDENCE_UPDATED = "EVIDENCE_UPDATED"
    EVIDENCE_DELETED_OR_ARCHIVED = "EVIDENCE_DELETED_OR_ARCHIVED"

    # Review Actions
    REVIEW_SUBMITTED = "REVIEW_SUBMITTED"
    REVIEW_APPROVED = "REVIEW_APPROVED"
    REVIEW_REJECTED = "REVIEW_REJECTED"
    REVIEW_RETURNED_FOR_CORRECTION = "REVIEW_RETURNED_FOR_CORRECTION"

    @classmethod
    def from_value(cls, val: Any) -> "AuditAction":
        if isinstance(val, cls):
            return val
        if hasattr(val, "value"):
            val = val.value
        clean = str(val or "").strip().upper().replace("-", "_").replace(" ", "_")
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        # Fallbacks/aliases
        if clean in ("EVIDENCE_DELETED", "EVIDENCE_ARCHIVED"):
            return cls.EVIDENCE_DELETED_OR_ARCHIVED
        if clean in ("REVIEW_ACCEPT", "REVIEW_ACCEPTED"):
            return cls.REVIEW_APPROVED
        if clean in ("REVIEW_FAIL", "REVIEW_FAILED"):
            return cls.REVIEW_REJECTED
        if clean in ("REVIEW_RETURN", "REVIEW_REWORK"):
            return cls.REVIEW_RETURNED_FOR_CORRECTION
        if clean in ("JOB_VALIDATE", "JOB_VALIDATION", "VALIDATED"):
            return cls.JOB_VALIDATED
        if clean in ("GENERATE_TEST_PLAN", "TEST_PLAN_GENERATED_EVENT"):
            return cls.TEST_PLAN_GENERATED
        if clean in ("ASSIGN_INSPECTOR", "INSPECTOR_ASSIGNMENT"):
            return cls.INSPECTOR_ASSIGNED
        if clean in ("GENERATE_REPORT", "REPORT_GENERATION"):
            return cls.REPORT_GENERATED
        raise ValueError(
            f"Invalid audit action '{val}'. Permitted actions: {[m.value for m in cls]}"
        )


class EntityType(str, Enum):
    """Domain entity categories subjected to statutory audit traceability."""
    JOB = "JOB"
    EQUIPMENT = "EQUIPMENT"
    TEST_STANDARD = "TEST_STANDARD"
    ENVIRONMENT = "ENVIRONMENT"
    TEST_ATTEMPT = "TEST_ATTEMPT"
    RETEST_REQUEST = "RETEST_REQUEST"
    EVIDENCE = "EVIDENCE"
    REVIEW = "REVIEW"

    @classmethod
    def from_value(cls, val: Any) -> "EntityType":
        if isinstance(val, cls):
            return val
        if hasattr(val, "value"):
            val = val.value
        clean = str(val or "JOB").strip().upper().replace("-", "_").replace(" ", "_")
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        # Common aliases
        if clean in ("TEST_JOB", "JOBS"):
            return cls.JOB
        if clean in ("STANDARD", "STANDARDS", "TEST_STANDARDS"):
            return cls.TEST_STANDARD
        if clean in ("ATTEMPT", "ATTEMPTS"):
            return cls.TEST_ATTEMPT
        if clean in ("ATTACHMENT", "ATTACHMENTS", "FILE"):
            return cls.EVIDENCE
        if clean in ("REVIEWS", "APPROVAL"):
            return cls.REVIEW
        if clean in ("ENV", "ENVIRONMENT_CONDITION"):
            return cls.ENVIRONMENT
        return cls.JOB


@dataclass(frozen=True)
class AuditLog:
    """
    Immutable Audit Log entity.
    Append-only statutory record tracking who did what, when, to which entity,
    along with before-and-after states and cryptographic/traceable metadata.
    """
    __test__ = False  # Avoid pytest collection warning

    id: str
    timestamp: str
    user_id: str
    action: AuditAction
    entity_type: EntityType
    entity_id: str
    old_value: Optional[Dict[str, Any]] = None
    new_value: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = dc_field(default_factory=dict)
    created_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def actor(self) -> str:
        """Alias for user_id."""
        return self.user_id

    @property
    def user(self) -> str:
        """Alias for user_id."""
        return self.user_id

    @property
    def job_id(self) -> Optional[str]:
        """Convenience accessor for job_id if entity is a job or recorded in metadata."""
        if self.entity_type == EntityType.JOB:
            return self.entity_id
        return self.metadata.get("job_id")

    def to_dict(self) -> Dict[str, Any]:
        """Converts immutable AuditLog entity to serializable dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "user_id": self.user_id,
            "actor": self.user_id,
            "action": self.action.value,
            "entity_type": self.entity_type.value,
            "entity_id": self.entity_id,
            "old_value": dict(self.old_value) if self.old_value is not None else None,
            "new_value": dict(self.new_value) if self.new_value is not None else None,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditLog":
        """Reconstructs AuditLog entity from dictionary."""
        a_id = str(data.get("id") or f"AUD-{uuid.uuid4().hex[:8].upper()}")
        ts = str(data.get("timestamp") or datetime.now(timezone.utc).isoformat())
        user_id = str(data.get("user_id") or data.get("actor") or "SYSTEM")
        action = AuditAction.from_value(data.get("action", AuditAction.JOB_UPDATED))
        entity_type = EntityType.from_value(data.get("entity_type", EntityType.JOB))
        entity_id = str(data.get("entity_id") or "")
        old_val = data.get("old_value")
        new_val = data.get("new_value")
        metadata = dict(data.get("metadata") or {})
        created_at = str(data.get("created_at") or ts)

        return cls(
            id=a_id,
            timestamp=ts,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=dict(old_val) if isinstance(old_val, dict) else None,
            new_value=dict(new_val) if isinstance(new_val, dict) else None,
            metadata=metadata,
            created_at=created_at,
        )
