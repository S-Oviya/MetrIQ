"""
MetrIQ Test Job Models — Person 3 (Job / Instrument Engineer)
=============================================================
Defines statutory test job lifecycle models and verification workflows
under the Legal Metrology Act, 2009 and OIML R 76-1:2006.

Captures job types, assigned inspectors, statutory routing decisions (GATC vs State),
attached Person 2 test plans, regulatory profile/version references, and audit state histories.
"""

from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

# Re-export and integrate Person 2 JobType
from app.regulatory.models import JobType as P2JobType


class JobType(str, Enum):
    """
    Statutory verification job types for NAWI instruments.
    Supports statutory Legal Metrology workflows:
    - MODEL_APPROVAL: Pattern evaluation under Model Approval Rules, 2011
    - INITIAL_VERIFICATION: First statutory stamping before entry into trade
    - RE_VERIFICATION: Periodic statutory verification (General Rules, 2011)
    - POST_REPAIR: Verification after servicing, replacement of load receptors or load cells
    - POST_RELOCATION: Verification after moving to a new operational site
    - REINSTALLATION: Reassembly and re-commissioning of dismantled instruments
    - RETEST: Re-inspection following failure rectification
    - OTHER: Configurable non-standard metrological audits
    """
    MODEL_APPROVAL = "MODEL_APPROVAL"
    INITIAL_VERIFICATION = "INITIAL_VERIFICATION"
    RE_VERIFICATION = "RE_VERIFICATION"
    POST_REPAIR = "POST_REPAIR"
    POST_RELOCATION = "POST_RELOCATION"
    REINSTALLATION = "REINSTALLATION"
    RETEST = "RETEST"
    OTHER = "OTHER"

    @classmethod
    def from_value(cls, val: Any) -> "JobType":
        if isinstance(val, cls):
            return val
        if hasattr(val, "value"):
            val = val.value
        clean = str(val or "RE_VERIFICATION").strip().upper().replace(" ", "_").replace("-", "_")
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        # Common aliases
        if clean in ("INITIAL", "FIRST_VERIFICATION"):
            return cls.INITIAL_VERIFICATION
        if clean in ("PERIODIC", "PERIODIC_RE_VERIFICATION", "SUBSEQUENT"):
            return cls.RE_VERIFICATION
        if clean in ("REPAIR", "AFTER_REPAIR"):
            return cls.POST_REPAIR
        if clean in ("RELOCATION", "MOVE"):
            return cls.POST_RELOCATION
        if clean in ("REINSTALL", "RE_INSTALLATION"):
            return cls.REINSTALLATION
        if clean in ("TYPE_EVALUATION", "PATTERN_APPROVAL"):
            return cls.MODEL_APPROVAL

        raise ValueError(
            f"Unknown or unsupported job type: '{val}'. Supported types: {[m.value for m in cls]}"
        )

    @property
    def is_in_service(self) -> bool:
        """Periodic re-verification and post-relocation operate under in-service MPE."""
        return self in (
            JobType.RE_VERIFICATION,
            JobType.POST_RELOCATION,
            JobType.REINSTALLATION,
            JobType.OTHER,
        )

    def to_p2_job_type(self) -> P2JobType:
        """Converts to Person 2's canonical JobType enum."""
        mapping = {
            JobType.MODEL_APPROVAL: P2JobType.MODEL_APPROVAL,
            JobType.INITIAL_VERIFICATION: P2JobType.INITIAL_VERIFICATION,
            JobType.RE_VERIFICATION: P2JobType.RE_VERIFICATION,
            JobType.POST_REPAIR: P2JobType.POST_REPAIR,
            JobType.POST_RELOCATION: P2JobType.POST_RELOCATION,
            JobType.REINSTALLATION: P2JobType.POST_RELOCATION,
            JobType.RETEST: P2JobType.RETEST,
            JobType.OTHER: P2JobType.RE_VERIFICATION,
        }
        return mapping.get(self, P2JobType.RE_VERIFICATION)


class JobStatus(str, Enum):
    """
    Formal lifecycle state machine for a test job.
    Enforces auditable progression through verification gates:
    DRAFT -> CREATED -> VALIDATED -> TEST_PLAN_GENERATED -> READY_FOR_TEST -> IN_TESTING
    -> TEST_COMPLETED -> UNDER_REVIEW -> APPROVED / REJECTED -> CLOSED
    """
    DRAFT = "DRAFT"                               # Initial job draft
    CREATED = "CREATED"                           # Formally registered job
    VALIDATED = "VALIDATED"                       # Metrology confirmed via Person 2
    TEST_PLAN_GENERATED = "TEST_PLAN_GENERATED"   # Person 2 statutory test plan attached
    READY_FOR_TEST = "READY_FOR_TEST"             # Inspector / Testing Centre allocated
    IN_TESTING = "IN_TESTING"                     # Active execution by Person 4
    TEST_COMPLETED = "TEST_COMPLETED"             # Observations completed by Person 4
    UNDER_REVIEW = "UNDER_REVIEW"                 # Submitted to reviewer in Person 5
    APPROVED = "APPROVED"                         # Approved by reviewer
    REJECTED = "REJECTED"                         # Verification failed or rejected
    CLOSED = "CLOSED"                             # Certificate stamped & job finalized
    CANCELLED = "CANCELLED"                       # Aborted prior to completion

    # P5 Canonical Lifecycle States
    READY = "READY"
    RETEST_REQUIRED = "RETEST_REQUIRED"
    REVIEW = "REVIEW"
    REPORT_GENERATED = "REPORT_GENERATED"

    # Backward compatibility synonyms
    PLAN_GENERATED = "PLAN_GENERATED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    TESTS_COMPLETED = "TESTS_COMPLETED"
    SUBMITTED_FOR_REVIEW = "SUBMITTED_FOR_REVIEW"
    CERTIFIED = "CERTIFIED"

    @classmethod
    def from_value(cls, val: Any) -> "JobStatus":
        if isinstance(val, cls):
            return val
        if hasattr(val, "value"):
            val = val.value
        clean = str(val or "DRAFT").strip().upper().replace(" ", "_").replace("-", "_")
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        return cls.DRAFT

    @property
    def is_terminal(self) -> bool:
        """Indicates whether this state cannot be transitioned further."""
        return self in (
            JobStatus.CLOSED,
            JobStatus.CERTIFIED,
            JobStatus.CANCELLED,
            JobStatus.REPORT_GENERATED,
        )

    @property
    def is_editable(self) -> bool:
        """Indicates whether job specifications can still be modified."""
        return self in (
            JobStatus.DRAFT,
            JobStatus.CREATED,
            JobStatus.VALIDATED,
        )


class JobPriority(str, Enum):
    """Job scheduling priority."""
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"

    @classmethod
    def from_value(cls, val: Any) -> "JobPriority":
        if isinstance(val, cls):
            return val
        if hasattr(val, "value"):
            val = val.value
        clean = str(val or "NORMAL").strip().upper()
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        return cls.NORMAL


@dataclass
class JobStateTransitionRecord:
    """Immutable audit trail entry recording a job status change."""
    transition_id: str
    from_status: str
    to_status: str
    timestamp: str
    user_id: str
    reason: str
    metadata: Dict[str, Any] = dc_field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "timestamp": self.timestamp,
            "user_id": self.user_id,
            "reason": self.reason,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobStateTransitionRecord":
        return cls(
            transition_id=str(data.get("transition_id") or uuid.uuid4().hex[:8]),
            from_status=str(data.get("from_status", "")),
            to_status=str(data.get("to_status", "")),
            timestamp=str(data.get("timestamp") or datetime.now(timezone.utc).isoformat()),
            user_id=str(data.get("user_id", "SYSTEM")),
            reason=str(data.get("reason", "")),
            metadata=dict(data.get("metadata", {})),
        )


class VerificationLocationType(str, Enum):
    """
    Statutory verification location types under Legal Metrology framework:
    - GATC_CENTRE: Government Approved Test Centre accredited under GATC Rules, 2013
    - STATE_LABORATORY: State Legal Metrology Department laboratory / testing facility
    - CENTRAL_LABORATORY: Central Directorate / CSIR-NPL / RRSL laboratory (for Model Approval)
    - ON_SITE_INSTALLATION: Field verification at customer/user premises (mandatory for heavy weighbridges > 150 kg, immovable scales)
    - MANUFACTURER_PREMISES: Manufacturer/assembler testing bench (for initial factory verification)
    - MOBILE_TEST_UNIT: Mobile calibration / test van
    """
    GATC_CENTRE = "GATC_CENTRE"
    STATE_LABORATORY = "STATE_LABORATORY"
    CENTRAL_LABORATORY = "CENTRAL_LABORATORY"
    ON_SITE_INSTALLATION = "ON_SITE_INSTALLATION"
    MANUFACTURER_PREMISES = "MANUFACTURER_PREMISES"
    MOBILE_TEST_UNIT = "MOBILE_TEST_UNIT"

    @classmethod
    def from_value(cls, val: Any) -> "VerificationLocationType":
        if isinstance(val, cls):
            return val
        if hasattr(val, "value"):
            val = val.value
        clean = str(val or "STATE_LABORATORY").strip().upper().replace(" ", "_").replace("-", "_")
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        # Common aliases
        if "GATC" in clean:
            return cls.GATC_CENTRE
        if "ON_SITE" in clean or "SITE" in clean or "FIELD" in clean or "CUSTOMER" in clean:
            return cls.ON_SITE_INSTALLATION
        if "CENTRAL" in clean or "NPL" in clean or "RRSL" in clean:
            return cls.CENTRAL_LABORATORY
        if "MANUFACTURER" in clean or "FACTORY" in clean:
            return cls.MANUFACTURER_PREMISES
        if "MOBILE" in clean or "VAN" in clean:
            return cls.MOBILE_TEST_UNIT
        return cls.STATE_LABORATORY


@dataclass
class StatutoryRoutingInfo:
    """Statutory routing decision evaluated under GATC Rules, 2013."""
    eligible_for_gatc: bool
    target_authority: str           # GATC, STATE_LEGAL_METROLOGY_OFFICER, CENTRAL_DIRECTORATE
    authority_name: str
    reason: str
    requires_regulatory_confirmation: bool = False
    citation: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eligible_for_gatc": self.eligible_for_gatc,
            "target_authority": self.target_authority,
            "authority_name": self.authority_name,
            "reason": self.reason,
            "requires_regulatory_confirmation": self.requires_regulatory_confirmation,
            "citation": self.citation,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["StatutoryRoutingInfo"]:
        if not data:
            return None
        return cls(
            eligible_for_gatc=bool(data.get("eligible_for_gatc", True)),
            target_authority=str(data.get("target_authority", "GATC")),
            authority_name=str(data.get("authority_name", "Government Approved Test Centre")),
            reason=str(data.get("reason", "")),
            requires_regulatory_confirmation=bool(data.get("requires_regulatory_confirmation", False)),
            citation=data.get("citation"),
        )


@dataclass
class TestJob:
    """
    Central Test Job entity.
    Coordinates an instrument's testing workflow, statutory authority assignment,
    Person 2 pre-calculated test plan, regulatory profile references, and audit transition history.
    """
    __test__ = False
    job_id: str
    instrument_id: str
    job_type: JobType = JobType.RE_VERIFICATION
    status: JobStatus = JobStatus.DRAFT
    priority: JobPriority = JobPriority.NORMAL

    # Reference & Model Approval
    job_number: str = ""
    model_approval_id: Optional[str] = None

    # Dates & Timestamps
    requested_date: Optional[str] = None  # YYYY-MM-DD
    created_date: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    scheduled_date: Optional[str] = None  # YYYY-MM-DD

    # Assignments & Locations
    assigned_laboratory: Optional[str] = None
    testing_centre_id: Optional[str] = None
    testing_centre_name: Optional[str] = None
    assigned_inspector_id: Optional[str] = None
    assigned_inspector_name: Optional[str] = None
    verification_location_type: Optional[str] = None
    gatc_reference: Optional[str] = None
    installation_location: Optional[Dict[str, Any]] = None
    reason_for_verification: Optional[str] = None
    routing_decision: Optional[str] = None
    regulatory_rule_reference: Optional[str] = None
    manual_review_flag: bool = False
    manual_review_reason: Optional[str] = None

    # Regulatory Integration (from Person 2)
    statutory_routing: Optional[StatutoryRoutingInfo] = None
    regulatory_profile_id: str = "IN_LM_2011_ACTIVE"
    regulatory_version: str = "1.0.0"
    regulatory_rule_references: List[str] = dc_field(default_factory=list)
    applicable_tests: List[str] = dc_field(default_factory=list)
    test_plan_reference: Optional[str] = None
    test_plan: Optional[Dict[str, Any]] = None  # Person 2 GeneratedTestPlan dict
    instrument_snapshot: Dict[str, Any] = dc_field(default_factory=dict)

    # Audit & User Metadata
    created_by: str = "SYSTEM"
    updated_by: str = "SYSTEM"
    state_history: List[JobStateTransitionRecord] = dc_field(default_factory=list)
    created_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    state_changed_at: Optional[str] = None
    completed_at: Optional[str] = None
    notes: str = ""
    test_execution_data: Optional[Dict[str, Any]] = None
    test_attempts: List[Dict[str, Any]] = dc_field(default_factory=list)
    equipment_ids: List[str] = dc_field(default_factory=list)
    test_standard_ids: List[str] = dc_field(default_factory=list)
    environment_records: List[Dict[str, Any]] = dc_field(default_factory=list)
    evidence_ids: List[str] = dc_field(default_factory=list)
    current_review_id: Optional[str] = None
    review_ids: List[str] = dc_field(default_factory=list)

    def __post_init__(self):
        if not self.job_number:
            year = datetime.now(timezone.utc).year
            self.job_number = f"JOB/{year}/{self.job_id.split('-')[-1].upper()}"
        if not self.test_plan_reference and self.test_plan:
            self.test_plan_reference = f"TP-{self.job_id}"
        if not self.state_changed_at:
            self.state_changed_at = self.created_at
        if self.testing_centre_name and not self.assigned_laboratory:
            self.assigned_laboratory = self.testing_centre_name
        if self.assigned_laboratory and not self.testing_centre_name:
            self.testing_centre_name = self.assigned_laboratory
        if self.statutory_routing:
            if not self.routing_decision:
                self.routing_decision = self.statutory_routing.target_authority
            if not self.manual_review_flag and self.statutory_routing.requires_regulatory_confirmation:
                self.manual_review_flag = True
        if not self.regulatory_rule_reference and self.regulatory_rule_references:
            self.regulatory_rule_reference = self.regulatory_rule_references[0]

    @property
    def id(self) -> str:
        """Alias for job_id conforming to generic entity identifier requirements."""
        return self.job_id

    @id.setter
    def id(self, val: str) -> None:
        self.job_id = val

    @property
    def current_state(self) -> str:
        """Convenience property for current lifecycle state name."""
        return self.status.value if hasattr(self.status, "value") else str(self.status)

    @property
    def laboratory(self) -> Optional[str]:
        """Convenience accessor for assigned testing laboratory."""
        return self.assigned_laboratory or self.testing_centre_name

    @property
    def test_centre(self) -> Optional[str]:
        """Convenience accessor for assigned testing centre."""
        return self.testing_centre_name or self.assigned_laboratory

    @property
    def gatc_code(self) -> Optional[str]:
        """Convenience accessor for GATC reference code."""
        return self.gatc_reference

    @property
    def regulatory_profile(self) -> str:
        """Convenience accessor for regulatory profile ID."""
        return self.regulatory_profile_id

    @property
    def latest_environment(self) -> Optional[Dict[str, Any]]:
        """Returns the most recent environment condition record, or None."""
        if self.environment_records:
            return self.environment_records[-1]
        return None

    def get_attempts_for_test(self, test_id: str) -> List[Dict[str, Any]]:
        """Returns all recorded test attempts for a specific test ID."""
        clean = str(test_id or "").strip().upper()
        return [
            a for a in self.test_attempts
            if str(a.get("test_id", "")).strip().upper() == clean
        ]

    def get_latest_attempt_for_test(self, test_id: str) -> Optional[Dict[str, Any]]:
        """Returns the latest attempt for a given test ID, or None."""
        attempts = self.get_attempts_for_test(test_id)
        if attempts:
            return max(attempts, key=lambda a: int(a.get("attempt_number", 0)))
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Converts TestJob entity to a serializable dictionary."""
        return {
            "id": self.job_id,
            "job_id": self.job_id,
            "job_number": self.job_number,
            "instrument_id": self.instrument_id,
            "model_approval_id": self.model_approval_id,
            "job_type": self.job_type.value,
            "status": self.status.value,
            "current_state": self.current_state,
            "priority": self.priority.value,
            "requested_date": self.requested_date,
            "created_date": self.created_date,
            "scheduled_date": self.scheduled_date,
            "assigned_laboratory": self.assigned_laboratory,
            "testing_centre_id": self.testing_centre_id,
            "testing_centre_name": self.testing_centre_name,
            "assigned_inspector_id": self.assigned_inspector_id,
            "assigned_inspector_name": self.assigned_inspector_name,
            "verification_location_type": self.verification_location_type,
            "laboratory": self.laboratory,
            "test_centre": self.test_centre,
            "gatc_reference": self.gatc_reference,
            "gatc_code": self.gatc_code,
            "installation_location": self.installation_location,
            "reason_for_verification": self.reason_for_verification,
            "routing_decision": self.routing_decision,
            "regulatory_rule_reference": self.regulatory_rule_reference,
            "regulatory_profile": self.regulatory_profile,
            "manual_review_flag": self.manual_review_flag,
            "manual_review_reason": self.manual_review_reason,
            "statutory_routing": self.statutory_routing.to_dict() if self.statutory_routing else None,
            "regulatory_profile_id": self.regulatory_profile_id,
            "regulatory_version": self.regulatory_version,
            "regulatory_rule_references": list(self.regulatory_rule_references),
            "applicable_tests": list(self.applicable_tests),
            "test_plan_reference": self.test_plan_reference,
            "test_plan": self.test_plan,
            "instrument_snapshot": self.instrument_snapshot,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
            "state_history": [t.to_dict() for t in self.state_history],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "state_changed_at": self.state_changed_at,
            "completed_at": self.completed_at,
            "notes": self.notes,
            "test_execution_data": self.test_execution_data,
            "test_attempts": list(self.test_attempts),
            "equipment_ids": list(self.equipment_ids),
            "test_standard_ids": list(self.test_standard_ids),
            "environment_records": list(self.environment_records),
            "latest_environment": self.latest_environment,
            "evidence_ids": list(self.evidence_ids),
            "current_review_id": self.current_review_id,
            "review_ids": list(self.review_ids),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestJob":
        """Reconstructs TestJob entity from dictionary."""
        j_id = str(data.get("job_id") or data.get("id") or f"JOB-{uuid.uuid4().hex[:8].upper()}")
        inst_id = str(data.get("instrument_id") or "")
        j_type = JobType.from_value(data.get("job_type", "RE_VERIFICATION"))
        j_status = JobStatus.from_value(data.get("status") or data.get("current_state") or "DRAFT")
        j_prio = JobPriority.from_value(data.get("priority", "NORMAL"))

        routing_obj = StatutoryRoutingInfo.from_dict(data.get("statutory_routing"))

        hist: List[JobStateTransitionRecord] = []
        if "state_history" in data and isinstance(data["state_history"], list):
            for h in data["state_history"]:
                hist.append(JobStateTransitionRecord.from_dict(h))

        return cls(
            job_id=j_id,
            instrument_id=inst_id,
            job_type=j_type,
            status=j_status,
            priority=j_prio,
            job_number=str(data.get("job_number") or ""),
            model_approval_id=data.get("model_approval_id"),
            requested_date=data.get("requested_date"),
            created_date=str(data.get("created_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            scheduled_date=data.get("scheduled_date"),
            assigned_laboratory=data.get("assigned_laboratory"),
            testing_centre_id=data.get("testing_centre_id"),
            testing_centre_name=data.get("testing_centre_name"),
            assigned_inspector_id=data.get("assigned_inspector_id"),
            assigned_inspector_name=data.get("assigned_inspector_name"),
            verification_location_type=data.get("verification_location_type"),
            gatc_reference=data.get("gatc_reference") or data.get("gatc_code"),
            installation_location=data.get("installation_location"),
            reason_for_verification=data.get("reason_for_verification") or data.get("verification_reason"),
            routing_decision=data.get("routing_decision") or (routing_obj.target_authority if routing_obj else None),
            regulatory_rule_reference=data.get("regulatory_rule_reference") or (data.get("regulatory_rule_references", [None])[0] if data.get("regulatory_rule_references") else None),
            manual_review_flag=bool(data.get("manual_review_flag", routing_obj.requires_regulatory_confirmation if routing_obj else False)),
            manual_review_reason=data.get("manual_review_reason"),
            statutory_routing=routing_obj,
            regulatory_profile_id=str(data.get("regulatory_profile_id") or data.get("regulatory_profile") or "IN_LM_2011_ACTIVE"),
            regulatory_version=str(data.get("regulatory_version", "1.0.0")),
            regulatory_rule_references=list(data.get("regulatory_rule_references", [])),
            applicable_tests=list(data.get("applicable_tests", [])),
            test_plan_reference=data.get("test_plan_reference"),
            test_plan=data.get("test_plan"),
            instrument_snapshot=dict(data.get("instrument_snapshot", {})),
            created_by=str(data.get("created_by", "SYSTEM")),
            updated_by=str(data.get("updated_by", "SYSTEM")),
            state_history=hist,
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            updated_at=str(data.get("updated_at") or datetime.now(timezone.utc).isoformat()),
            state_changed_at=data.get("state_changed_at") or data.get("created_at"),
            completed_at=data.get("completed_at"),
            notes=str(data.get("notes", "")),
            test_execution_data=data.get("test_execution_data"),
            test_attempts=list(data.get("test_attempts", [])),
            equipment_ids=list(data.get("equipment_ids", [])),
            test_standard_ids=list(data.get("test_standard_ids", [])),
            environment_records=list(data.get("environment_records", [])),
            evidence_ids=list(data.get("evidence_ids", [])),
            current_review_id=data.get("current_review_id"),
            review_ids=list(data.get("review_ids", [])),
        )
