"""
MetrIQ Instrument Lifecycle Manager — Person 3 (Job / Instrument Engineer)
==========================================================================
Manages the statutory operational lifecycle of weighing instruments under the
Legal Metrology Act, 2009 and Legal Metrology (General) Rules, 2011.

Capabilities:
1. Structured lifecycle events for all 12 Legal Metrology workflow phases:
   - Instrument registration
   - Model approval association
   - Initial verification
   - In-service use
   - Periodic re-verification
   - Repair
   - Post-repair re-verification
   - Dismantling
   - Relocation
   - Reinstallation
   - Post-relocation/reinstallation verification
   - Retirement
2. Strict statutory state machine preventing illegal state transitions.
3. Immutable historical lifecycle event auditing.
4. Statutory re-verification due dates based on regulatory profile rules.
5. Tracking legal metrology seals (lead seals, tamper-evident seals, electronic audit counters).
"""

from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import uuid

# Import Person 2 profile interfaces without modifying Person 2 code
from app.regulatory.profile import PROFILE_REGISTRY
from .models import (
    Instrument,
    InstrumentLifecycleEvent,
    InstrumentStatus,
    LifecycleEventType,
    PhysicalSeal,
    SealStatus,
    SealType,
)


class InstrumentLifecycleTransitionError(ValueError):
    """Raised when an illegal or non-sensible instrument lifecycle transition is attempted."""
    pass


class InstrumentLifecycleStateMachine:
    """
    Statutory state machine governing physical instrument lifecycle states.
    Enforces sensible legal progression and protects against impossible transitions.
    """

    ALLOWED_TRANSITIONS: Dict[InstrumentStatus, Set[InstrumentStatus]] = {
        InstrumentStatus.REGISTERED: {
            InstrumentStatus.READY,
            InstrumentStatus.PENDING_APPROVAL,
            InstrumentStatus.VERIFICATION_REQUIRED,
            InstrumentStatus.IN_VERIFICATION,
            InstrumentStatus.RETIRED,
            InstrumentStatus.DECOMMISSIONED,
        },
        InstrumentStatus.PENDING_APPROVAL: {
            InstrumentStatus.READY,
            InstrumentStatus.VERIFICATION_REQUIRED,
            InstrumentStatus.IN_VERIFICATION,
            InstrumentStatus.RETIRED,
            InstrumentStatus.DECOMMISSIONED,
        },
        InstrumentStatus.READY: {
            InstrumentStatus.VERIFICATION_REQUIRED,
            InstrumentStatus.IN_VERIFICATION,
            InstrumentStatus.RETIRED,
            InstrumentStatus.DECOMMISSIONED,
        },
        InstrumentStatus.VERIFICATION_REQUIRED: {
            InstrumentStatus.IN_VERIFICATION,
            InstrumentStatus.RETIRED,
            InstrumentStatus.DECOMMISSIONED,
        },
        InstrumentStatus.IN_VERIFICATION: {
            InstrumentStatus.VERIFIED,
            InstrumentStatus.IN_SERVICE,
            InstrumentStatus.ACTIVE,
            InstrumentStatus.REPAIR,
            InstrumentStatus.REPAIR_REQUIRED,
            InstrumentStatus.SUSPENDED,
            InstrumentStatus.RETIRED,
            InstrumentStatus.DECOMMISSIONED,
        },
        InstrumentStatus.VERIFIED: {
            InstrumentStatus.IN_SERVICE,
            InstrumentStatus.ACTIVE,
            InstrumentStatus.DISMANTLED,
            InstrumentStatus.REPAIR,
            InstrumentStatus.REPAIR_REQUIRED,
            InstrumentStatus.RETIRED,
            InstrumentStatus.DECOMMISSIONED,
        },
        InstrumentStatus.IN_SERVICE: {
            InstrumentStatus.RE_VERIFICATION_DUE,
            InstrumentStatus.IN_VERIFICATION,
            InstrumentStatus.REPAIR,
            InstrumentStatus.REPAIR_REQUIRED,
            InstrumentStatus.DISMANTLED,
            InstrumentStatus.RELOCATED,
            InstrumentStatus.SUSPENDED,
            InstrumentStatus.RETIRED,
            InstrumentStatus.DECOMMISSIONED,
        },
        InstrumentStatus.ACTIVE: {
            InstrumentStatus.RE_VERIFICATION_DUE,
            InstrumentStatus.IN_VERIFICATION,
            InstrumentStatus.REPAIR,
            InstrumentStatus.REPAIR_REQUIRED,
            InstrumentStatus.DISMANTLED,
            InstrumentStatus.RELOCATED,
            InstrumentStatus.SUSPENDED,
            InstrumentStatus.RETIRED,
            InstrumentStatus.DECOMMISSIONED,
        },
        InstrumentStatus.RE_VERIFICATION_DUE: {
            InstrumentStatus.IN_VERIFICATION,
            InstrumentStatus.REPAIR,
            InstrumentStatus.REPAIR_REQUIRED,
            InstrumentStatus.DISMANTLED,
            InstrumentStatus.SUSPENDED,
            InstrumentStatus.RETIRED,
            InstrumentStatus.DECOMMISSIONED,
        },
        InstrumentStatus.REPAIR: {
            InstrumentStatus.POST_REPAIR_VERIFICATION,
            InstrumentStatus.VERIFICATION_REQUIRED,
            InstrumentStatus.IN_VERIFICATION,
            InstrumentStatus.DISMANTLED,
            InstrumentStatus.RETIRED,
            InstrumentStatus.DECOMMISSIONED,
        },
        InstrumentStatus.REPAIR_REQUIRED: {
            InstrumentStatus.POST_REPAIR_VERIFICATION,
            InstrumentStatus.VERIFICATION_REQUIRED,
            InstrumentStatus.IN_VERIFICATION,
            InstrumentStatus.DISMANTLED,
            InstrumentStatus.RETIRED,
            InstrumentStatus.DECOMMISSIONED,
        },
        InstrumentStatus.POST_REPAIR_VERIFICATION: {
            InstrumentStatus.IN_VERIFICATION,
            InstrumentStatus.VERIFIED,
            InstrumentStatus.IN_SERVICE,
            InstrumentStatus.ACTIVE,
            InstrumentStatus.REPAIR,
            InstrumentStatus.REPAIR_REQUIRED,
            InstrumentStatus.RETIRED,
            InstrumentStatus.DECOMMISSIONED,
        },
        InstrumentStatus.DISMANTLED: {
            InstrumentStatus.RELOCATED,
            InstrumentStatus.REINSTALLED,
            InstrumentStatus.REPAIR,
            InstrumentStatus.REPAIR_REQUIRED,
            InstrumentStatus.RETIRED,
            InstrumentStatus.DECOMMISSIONED,
        },
        InstrumentStatus.RELOCATED: {
            InstrumentStatus.REINSTALLED,
            InstrumentStatus.VERIFICATION_REQUIRED,
            InstrumentStatus.IN_VERIFICATION,
            InstrumentStatus.RETIRED,
            InstrumentStatus.DECOMMISSIONED,
        },
        InstrumentStatus.REINSTALLED: {
            InstrumentStatus.VERIFICATION_REQUIRED,
            InstrumentStatus.IN_VERIFICATION,
            InstrumentStatus.RETIRED,
            InstrumentStatus.DECOMMISSIONED,
        },
        InstrumentStatus.SUSPENDED: {
            InstrumentStatus.IN_VERIFICATION,
            InstrumentStatus.REPAIR,
            InstrumentStatus.REPAIR_REQUIRED,
            InstrumentStatus.RETIRED,
            InstrumentStatus.DECOMMISSIONED,
            InstrumentStatus.IN_SERVICE,
            InstrumentStatus.ACTIVE,
        },
        InstrumentStatus.RETIRED: set(),        # Terminal state
        InstrumentStatus.DECOMMISSIONED: set(), # Terminal state
    }

    @classmethod
    def can_transition(
        cls,
        from_status: Union[str, InstrumentStatus],
        to_status: Union[str, InstrumentStatus],
    ) -> Tuple[bool, str]:
        """Evaluates whether transitioning from from_status to to_status is legally permissible."""
        curr = InstrumentStatus.from_value(from_status)
        target = InstrumentStatus.from_value(to_status)

        if curr == target:
            return True, f"Instrument is already in {curr.value} status."

        allowed_targets = cls.ALLOWED_TRANSITIONS.get(curr, set())
        if target in allowed_targets:
            return True, f"Transition from {curr.value} to {target.value} is valid."

        allowed_names = [s.value for s in allowed_targets]
        return (
            False,
            f"Invalid instrument state transition from {curr.value} to {target.value}. "
            f"Permitted next states from {curr.value}: {allowed_names or 'None (Terminal state)'}.",
        )

    @classmethod
    def validate_transition(
        cls,
        from_status: Union[str, InstrumentStatus],
        to_status: Union[str, InstrumentStatus],
    ) -> None:
        """Validates transition and raises InstrumentLifecycleTransitionError if invalid."""
        valid, reason = cls.can_transition(from_status, to_status)
        if not valid:
            raise InstrumentLifecycleTransitionError(reason)


@dataclass
class VerificationRecord:
    """Historical record of an official verification and stamping event."""
    record_id: str
    job_id: str
    verification_date: str          # YYYY-MM-DD
    certificate_number: str
    job_type: str                   # INITIAL_VERIFICATION, RE_VERIFICATION, etc.
    stamping_authority: str         # GATC or State Legal Metrology Department
    inspecting_officer: str
    outcome: str                    # PASSED / REJECTED
    next_due_date: str              # YYYY-MM-DD
    fee_charged_inr: Optional[float] = None
    applied_seals: List[str] = dc_field(default_factory=list)
    remarks: str = ""
    recorded_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "job_id": self.job_id,
            "verification_date": self.verification_date,
            "certificate_number": self.certificate_number,
            "job_type": self.job_type,
            "stamping_authority": self.stamping_authority,
            "inspecting_officer": self.inspecting_officer,
            "outcome": self.outcome,
            "next_due_date": self.next_due_date,
            "fee_charged_inr": self.fee_charged_inr,
            "applied_seals": self.applied_seals,
            "remarks": self.remarks,
            "recorded_at": self.recorded_at,
        }


class InstrumentLifecycleManager:
    """
    Coordinates instrument lifecycle transitions, statutory seal integrity,
    historical event tracking, and periodic re-verification deadlines.
    """

    @classmethod
    def record_lifecycle_event(
        cls,
        instrument: Instrument,
        event_type: Union[str, LifecycleEventType],
        new_status: Union[str, InstrumentStatus],
        actor: str = "SYSTEM",
        event_date: Optional[str] = None,
        related_job_id: Optional[str] = None,
        notes: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InstrumentLifecycleEvent:
        """
        Executes and immutably records a statutory lifecycle event on an instrument.
        Validates the state transition and updates the instrument's operational status.
        Does NOT delete historical events.
        """
        ev_type = LifecycleEventType.from_value(event_type)
        target_status = InstrumentStatus.from_value(new_status)
        old_status = instrument.status

        # 1. Validate sensible state transition
        InstrumentLifecycleStateMachine.validate_transition(old_status, target_status)

        # 2. Update operational status
        instrument.status = target_status
        e_date = event_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        instrument.updated_at = datetime.now(timezone.utc).isoformat()

        # 3. Synchronize lifecycle dates based on event type
        if ev_type == LifecycleEventType.REGISTRATION:
            instrument.registered_date = e_date
        elif ev_type == LifecycleEventType.DISMANTLING:
            instrument.dismantled_date = e_date
        elif ev_type in (LifecycleEventType.REINSTALLATION, LifecycleEventType.RELOCATION):
            instrument.reinstalled_date = e_date
        elif ev_type == LifecycleEventType.REPAIR:
            instrument.repair_date = e_date
        elif ev_type == LifecycleEventType.RETIREMENT:
            instrument.retired_date = e_date

        # 4. Create immutable lifecycle event
        event = InstrumentLifecycleEvent(
            event_id=f"EVT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}",
            instrument_id=instrument.instrument_id,
            event_type=ev_type,
            event_date=e_date,
            previous_status=old_status,
            new_status=target_status,
            related_job_id=related_job_id,
            notes=notes or f"Transitioned to {target_status.value} via {ev_type.value}",
            actor=actor,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=dict(metadata or {}),
        )

        instrument.lifecycle_events.append(event)
        return event

    @classmethod
    def get_lifecycle_history(cls, instrument: Instrument) -> List[InstrumentLifecycleEvent]:
        """Returns the full chronological, immutable lifecycle event history for an instrument."""
        return list(instrument.lifecycle_events)

    @classmethod
    def calculate_next_re_verification_due(
        cls,
        instrument: Instrument,
        verification_date: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> str:
        """
        Calculates the statutory re-verification due date (YYYY-MM-DD)
        by consulting the active regulatory profile via Person 2's API.
        """
        v_date_str = verification_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            base_dt = datetime.strptime(v_date_str, "%Y-%m-%d")
        except ValueError:
            base_dt = datetime.now(timezone.utc)

        # 1. Resolve interval in months
        if instrument.re_verification_interval_months:
            months = instrument.re_verification_interval_months
        else:
            months = 12  # Statutory default
            try:
                active_profile = PROFILE_REGISTRY.get_profile(profile_id or "IN_LM_2011_ACTIVE")
                if active_profile:
                    type_str = instrument.instrument_type.value if hasattr(instrument.instrument_type, "value") else str(instrument.instrument_type)
                    if "PRECISION" in type_str or "ANALYTICAL" in type_str:
                        query_type = "PRECISION_LAB"
                    elif "WEIGHBRIDGE" in type_str:
                        query_type = "INDUSTRIAL_WEIGHBRIDGE"
                    else:
                        query_type = "COMMERCIAL_NAWI"
                    months = active_profile.get_re_verification_period_months(query_type)
            except Exception:
                months = instrument.re_verification_interval_months or 12

        # 2. Advance date by statutory months
        new_year = base_dt.year + (base_dt.month + months - 1) // 12
        new_month = (base_dt.month + months - 1) % 12 + 1
        new_day = min(base_dt.day, 28)
        due_dt = base_dt.replace(year=new_year, month=new_month, day=new_day)
        return due_dt.strftime("%Y-%m-%d")

    @classmethod
    def evaluate_operational_status(
        cls,
        instrument: Instrument,
        as_of_date: Optional[str] = None,
    ) -> InstrumentStatus:
        """
        Evaluates the current legal operational status of an instrument based on
        seal integrity and statutory re-verification due date.
        """
        if instrument.status in (
            InstrumentStatus.DECOMMISSIONED,
            InstrumentStatus.RETIRED,
            InstrumentStatus.SUSPENDED,
            InstrumentStatus.IN_VERIFICATION,
            InstrumentStatus.DISMANTLED,
        ):
            return instrument.status

        # 1. Seal check: Broken statutory seal immediately requires repair and re-stamping
        for seal in instrument.seals:
            if seal.status in (SealStatus.BROKEN, SealStatus.MISSING):
                return InstrumentStatus.REPAIR_REQUIRED

        # 2. Deadline check: Past or approaching re-verification date
        if instrument.next_re_verification_due:
            now_date = as_of_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if now_date > instrument.next_re_verification_due:
                return InstrumentStatus.RE_VERIFICATION_DUE

            # 30-day notice window before expiration
            try:
                due_dt = datetime.strptime(instrument.next_re_verification_due, "%Y-%m-%d")
                now_dt = datetime.strptime(now_date, "%Y-%m-%d")
                days_left = (due_dt - now_dt).days
                if days_left <= 30:
                    return InstrumentStatus.RE_VERIFICATION_DUE
            except ValueError:
                pass

        return instrument.status or InstrumentStatus.ACTIVE

    @classmethod
    def record_successful_verification(
        cls,
        instrument: Instrument,
        job_id: str,
        certificate_number: str,
        job_type: str,
        stamping_authority: str,
        inspecting_officer: str,
        verification_date: Optional[str] = None,
        applied_seals: Optional[List[PhysicalSeal]] = None,
        profile_id: Optional[str] = None,
        fee_inr: Optional[float] = None,
    ) -> VerificationRecord:
        """
        Updates instrument lifecycle upon successful legal verification and stamping.
        """
        v_date = verification_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        next_due = cls.calculate_next_re_verification_due(instrument, v_date, profile_id)

        instrument.last_verification_date = v_date
        instrument.last_verification_certificate = certificate_number
        instrument.next_re_verification_due = next_due
        instrument.status = InstrumentStatus.ACTIVE
        instrument.updated_at = datetime.now(timezone.utc).isoformat()

        seal_nums: List[str] = []
        if applied_seals:
            instrument.seals = applied_seals
            seal_nums = [s.seal_number for s in applied_seals]

        rec = VerificationRecord(
            record_id=f"VR-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            job_id=job_id,
            verification_date=v_date,
            certificate_number=certificate_number,
            job_type=job_type,
            stamping_authority=stamping_authority,
            inspecting_officer=inspecting_officer,
            outcome="PASSED",
            next_due_date=next_due,
            fee_charged_inr=fee_inr,
            applied_seals=seal_nums,
            remarks=f"Statutory stamping completed under Legal Metrology Rules, 2011.",
        )

        # Record corresponding lifecycle event
        ev_type = (
            LifecycleEventType.INITIAL_VERIFICATION
            if "INITIAL" in job_type
            else (
                LifecycleEventType.POST_REPAIR_VERIFICATION
                if "REPAIR" in job_type
                else (
                    LifecycleEventType.POST_RELOCATION_VERIFICATION
                    if ("RELOCATION" in job_type or "REINSTALL" in job_type)
                    else LifecycleEventType.PERIODIC_RE_VERIFICATION
                )
            )
        )
        cls.record_lifecycle_event(
            instrument=instrument,
            event_type=ev_type,
            new_status=InstrumentStatus.IN_SERVICE,
            actor=inspecting_officer,
            event_date=v_date,
            related_job_id=job_id,
            notes=f"Stamping completed. Certificate {certificate_number} issued by {stamping_authority}.",
            metadata={"certificate_number": certificate_number, "applied_seals": seal_nums, "fee_inr": fee_inr},
        )

        return rec

    @classmethod
    def report_broken_seal(
        cls,
        instrument: Instrument,
        seal_id: str,
        reason: str,
        reported_by: str,
    ) -> Tuple[bool, str]:
        """
        Reports a broken or tampered seal on an active instrument.
        Immediately changes instrument status to REPAIR_REQUIRED under Section 24 of the LM Act.
        """
        target_seal = None
        for s in instrument.seals:
            if s.seal_id == seal_id or s.seal_number == seal_id:
                target_seal = s
                break

        if not target_seal:
            return False, f"Seal with ID or number '{seal_id}' not found on instrument {instrument.instrument_id}."

        target_seal.status = SealStatus.BROKEN
        target_seal.broken_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        target_seal.broken_reason = reason

        # Transition operational status and record event
        cls.record_lifecycle_event(
            instrument=instrument,
            event_type=LifecycleEventType.REPAIR,
            new_status=InstrumentStatus.REPAIR_REQUIRED,
            actor=reported_by,
            notes=f"Seal '{target_seal.seal_number}' broken: {reason}",
            metadata={"broken_seal_id": target_seal.seal_id, "broken_seal_number": target_seal.seal_number},
        )

        return (
            True,
            f"Seal '{target_seal.seal_number}' recorded as BROKEN. Instrument {instrument.instrument_id} "
            f"operational status transitioned to REPAIR_REQUIRED under Section 24 of the Legal Metrology Act, 2009. "
            f"Re-stamping required before commercial trade use.",
        )

    @classmethod
    def apply_seal(
        cls,
        instrument: Instrument,
        seal: PhysicalSeal,
    ) -> None:
        """Applies a new statutory verification seal to the instrument."""
        existing_idx = -1
        for idx, s in enumerate(instrument.seals):
            if s.location == seal.location:
                existing_idx = idx
                break

        if existing_idx >= 0:
            instrument.seals[existing_idx] = seal
        else:
            instrument.seals.append(seal)

        instrument.updated_at = datetime.now(timezone.utc).isoformat()
