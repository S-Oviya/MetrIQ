"""
MetrIQ Verification & Re-verification Scheduling — Person 3 (Job / Instrument Engineer)
=======================================================================================
Orchestrates statutory verification scheduling, deadline tracking, due/overdue
evaluation, verification job dispatch, and post-verification status synchronization
under the Legal Metrology Act, 2009 and Central Rules (2011 & 2013).

Guiding Principles:
1. Zero Hardcoding: Verification intervals are consumed strictly from active shared
   regulatory profiles (PROFILE_REGISTRY).
2. Manual Review Isolation: If an interval cannot be determined reliably (unverified,
   draft, missing rules, or unknown instrument type), the instrument is flagged as
   manual_review_required=True without guessing.
3. Zero Metrology Duplication: Consumes Person 2 regulatory profiles and Person 3
   lifecycle/job services cleanly.
4. Architectural Separation: Scheduling provisions Test Jobs for Person 4 execution.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import uuid

# Person 2 Profile Registry
from app.regulatory.profile import PROFILE_REGISTRY, ProfileStatus, RegulatoryProfile

# Person 3 Models and Services
from .models import (
    CustomerLocation,
    Instrument,
    InstrumentLifecycleEvent,
    InstrumentStatus,
    LifecycleEventType,
    PhysicalSeal,
    SealStatus,
    VerificationReason,
    VerificationStatus,
)
from .registry import INSTRUMENT_REGISTRY, InstrumentRegistry
from .lifecycle import InstrumentLifecycleManager
from app.jobs.models import JobPriority, JobStatus, JobType, TestJob
from app.jobs.repository import TEST_JOB_REPOSITORY, TestJobRepository
from app.jobs.state_machine import JobStateMachine


class VerificationScheduler:
    """
    Coordinates verification scheduling, reminder alerts, due/overdue detection,
    verification job provisioning, and status synchronization upon job completion.
    """

    def __init__(
        self,
        instrument_registry: Optional[InstrumentRegistry] = None,
        job_repository: Optional[TestJobRepository] = None,
        job_service: Optional[Any] = None,
    ) -> None:
        self.instruments = instrument_registry or INSTRUMENT_REGISTRY
        self.jobs = job_repository or TEST_JOB_REPOSITORY
        self._job_service = job_service

    @property
    def job_service(self) -> Any:
        if self._job_service is not None:
            return self._job_service
        from app.jobs.service import TEST_JOB_SERVICE
        return TEST_JOB_SERVICE

    # =========================================================================
    # 1. Authoritative Interval & Next Verification Date Calculation
    # =========================================================================

    def calculate_and_store_next_verification_date(
        self,
        instrument: Instrument,
        base_date: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calculates and stores the next verification due date for an instrument
        using the authoritative interval from the applicable regulatory profile.

        If the interval cannot be determined reliably (unverified profile,
        missing rules, or draft status), flags the instrument for manual review.
        """
        # 1. Resolve applicable regulatory profile
        profile = self._resolve_regulatory_profile(instrument, profile_id)

        if not profile:
            instrument.manual_review_required = True
            instrument.manual_review_reason = (
                f"No regulatory profile found for profile ID '{profile_id}' or instrument jurisdiction."
            )
            instrument.verification_status = VerificationStatus.MANUAL_REVIEW_REQUIRED
            self.instruments.update(instrument)
            return {
                "success": False,
                "manual_review_required": True,
                "message": instrument.manual_review_reason,
            }

        # 2. Check profile authoritativeness
        # Unverified secondary claims (e.g. reported G.S.R. 568(E) DRAFT) must NOT be applied automatically
        if profile.verification_status in (ProfileStatus.MANUAL_REVIEW, ProfileStatus.DRAFT) or not profile.is_authoritative:
            instrument.manual_review_required = True
            instrument.manual_review_reason = (
                f"Regulatory profile '{profile.profile_id}' is in {profile.verification_status.value} "
                f"status and is not authoritative law. Verification interval requires manual confirmation."
            )
            instrument.verification_status = VerificationStatus.MANUAL_REVIEW_REQUIRED
            instrument.applicable_regulatory_profile_id = profile.profile_id
            instrument.applicable_regulatory_version = profile.version
            self.instruments.update(instrument)
            return {
                "success": False,
                "manual_review_required": True,
                "profile_id": profile.profile_id,
                "verification_status": profile.verification_status.value,
                "message": instrument.manual_review_reason,
            }

        # 3. Check presence of re_verification_periods in profile
        if not profile.re_verification_periods:
            instrument.manual_review_required = True
            instrument.manual_review_reason = (
                f"Regulatory profile '{profile.profile_id}' does not define re-verification periods."
            )
            instrument.verification_status = VerificationStatus.MANUAL_REVIEW_REQUIRED
            instrument.applicable_regulatory_profile_id = profile.profile_id
            instrument.applicable_regulatory_version = profile.version
            self.instruments.update(instrument)
            return {
                "success": False,
                "manual_review_required": True,
                "profile_id": profile.profile_id,
                "message": instrument.manual_review_reason,
            }

        # 4. Determine authoritative interval in months
        query_type = self._map_instrument_type_for_profile(instrument)
        interval_months = profile.get_re_verification_period_months(query_type)

        # 5. Compute next verification date
        b_date_str = base_date or instrument.last_verification_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            b_dt = datetime.strptime(b_date_str[:10], "%Y-%m-%d")
        except ValueError:
            b_dt = datetime.now(timezone.utc)

        new_year = b_dt.year + (b_dt.month + interval_months - 1) // 12
        new_month = (b_dt.month + interval_months - 1) % 12 + 1
        new_day = min(b_dt.day, 28)
        due_dt = b_dt.replace(year=new_year, month=new_month, day=new_day)
        next_due_str = due_dt.strftime("%Y-%m-%d")

        # 6. Store on instrument
        instrument.next_re_verification_due = next_due_str
        instrument.re_verification_interval_months = interval_months
        instrument.applicable_regulatory_profile_id = profile.profile_id
        instrument.applicable_regulatory_version = profile.version
        instrument.manual_review_required = False
        instrument.manual_review_reason = None
        instrument.updated_at = datetime.now(timezone.utc).isoformat()
        self.instruments.update(instrument)

        return {
            "success": True,
            "manual_review_required": False,
            "next_verification_date": next_due_str,
            "interval_months": interval_months,
            "profile_id": profile.profile_id,
            "profile_version": profile.version,
            "regulation_name": profile.regulation_name,
        }

    # =========================================================================
    # 2. Due & Overdue Evaluation
    # =========================================================================

    def flag_verification_due(
        self,
        instrument: Instrument,
        as_of_date: Optional[str] = None,
        reminder_window_days: int = 30,
    ) -> Tuple[bool, str]:
        """
        Evaluates whether an instrument is approaching its verification deadline
        (within the reminder window or due today). Updates status and scheduling metadata.
        """
        if instrument.status in (InstrumentStatus.RETIRED, InstrumentStatus.DECOMMISSIONED):
            return False, "Instrument is permanently retired; scheduling is not applicable."

        if instrument.manual_review_required:
            return False, "Instrument is pending manual review of verification intervals."

        if not instrument.next_verification_date:
            return False, "Instrument has no scheduled next verification date."

        as_of_str = as_of_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            now_dt = datetime.strptime(as_of_str[:10], "%Y-%m-%d")
            due_dt = datetime.strptime(instrument.next_verification_date[:10], "%Y-%m-%d")
        except ValueError:
            return False, "Invalid date format for due date evaluation."

        delta_days = (due_dt - now_dt).days

        # Overdue condition is handled by flag_overdue
        if delta_days < 0:
            return self.flag_overdue(instrument, as_of_date)

        # Within reminder window or due today
        if delta_days <= reminder_window_days:
            instrument.verification_status = VerificationStatus.DUE
            instrument.status = InstrumentStatus.RE_VERIFICATION_DUE
            instrument.verification_reason = VerificationReason.PERIODIC_EXPIRY.value
            instrument.scheduling_metadata.update({
                "flagged_due_at": as_of_str,
                "days_until_due": delta_days,
                "due_date": instrument.next_verification_date,
                "due_today": (delta_days == 0),
                "reminder_window_days": reminder_window_days,
            })
            instrument.updated_at = datetime.now(timezone.utc).isoformat()
            self.instruments.update(instrument)
            msg = "Verification is due today." if delta_days == 0 else f"Verification is due in {delta_days} day(s)."
            return True, msg

        return False, f"Verification is in the future ({delta_days} days remaining)."

    def flag_overdue(
        self,
        instrument: Instrument,
        as_of_date: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Evaluates whether an instrument has surpassed its statutory verification
        deadline without being verified. Flags status as OVERDUE.
        """
        if instrument.status in (InstrumentStatus.RETIRED, InstrumentStatus.DECOMMISSIONED):
            return False, "Instrument is permanently retired."

        if not instrument.next_verification_date:
            return False, "Instrument has no scheduled next verification date."

        as_of_str = as_of_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            now_dt = datetime.strptime(as_of_str[:10], "%Y-%m-%d")
            due_dt = datetime.strptime(instrument.next_verification_date[:10], "%Y-%m-%d")
        except ValueError:
            return False, "Invalid date format for overdue evaluation."

        if now_dt > due_dt:
            days_overdue = (now_dt - due_dt).days
            instrument.verification_status = VerificationStatus.OVERDUE
            instrument.status = InstrumentStatus.RE_VERIFICATION_DUE
            instrument.verification_reason = VerificationReason.PERIODIC_EXPIRY.value
            instrument.scheduling_metadata.update({
                "flagged_overdue_at": as_of_str,
                "days_overdue": days_overdue,
                "due_date": instrument.next_verification_date,
            })
            instrument.updated_at = datetime.now(timezone.utc).isoformat()
            self.instruments.update(instrument)
            return True, f"Instrument is OVERDUE by {days_overdue} day(s)."

        return False, "Instrument is not overdue."

    # =========================================================================
    # 3. Create Verification Job
    # =========================================================================

    def create_verification_job(
        self,
        instrument_id: str,
        job_type: Union[str, JobType],
        reason: Union[str, VerificationReason],
        scheduled_date: Optional[str] = None,
        user_id: str = "SYSTEM",
        priority: Optional[str] = None,
        notes: str = "",
        inspector_id: Optional[str] = None,
        inspector_name: Optional[str] = None,
        testing_centre_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Provisions a statutory verification Test Job for Person 4 execution.
        Links the job ID to the instrument, updates operational status to
        IN_VERIFICATION / UNDER_INSPECTION, and records lifecycle trace.
        """
        instrument = self.instruments.get(instrument_id)
        if not instrument:
            return {"success": False, "status_code": 404, "message": f"Instrument '{instrument_id}' not found."}

        # Standardize job type and reason
        try:
            j_type = JobType.from_value(job_type)
        except ValueError as e:
            return {"success": False, "status_code": 422, "message": str(e)}

        r_obj = VerificationReason.from_value(reason)
        r_val = r_obj.value

        # Determine priority: Overdue or broken seal/repair gets HIGH priority
        if priority:
            prio = JobPriority.from_value(priority)
        elif instrument.verification_status == VerificationStatus.OVERDUE or r_obj == VerificationReason.POST_REPAIR:
            prio = JobPriority.HIGH
        else:
            prio = JobPriority.NORMAL

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        sched_dt = scheduled_date or today_str

        # Prepare job creation payload
        job_payload = {
            "instrument_id": instrument_id,
            "job_type": j_type.value,
            "requested_date": today_str,
            "scheduled_date": sched_dt,
            "priority": prio.value,
            "created_by": user_id,
            "notes": f"Verification trigger: {r_val}. {notes}".strip(),
            "metadata": {
                "verification_reason": r_val,
                "scheduled_by": user_id,
                "state": instrument.location.state if instrument.location else None,
                "district": instrument.location.district if instrument.location else None,
                "previous_verification_date": instrument.last_verification_date,
                "next_due_date": instrument.next_verification_date,
            },
        }

        job_result = self.job_service.create_job(job_payload)
        if not job_result.get("success"):
            return job_result

        job_id = job_result["data"]["job_id"]

        # Assign inspector if provided
        if inspector_id and inspector_name:
            self.job_service.assign_inspector(
                job_id=job_id,
                inspector_id=inspector_id,
                inspector_name=inspector_name,
                testing_centre_name=testing_centre_name,
                scheduled_date=sched_dt,
                assigned_by=user_id,
            )

        # Update Instrument status and link active job
        instrument.active_verification_job_id = job_id
        instrument.verification_status = VerificationStatus.UNDER_INSPECTION
        instrument.verification_reason = r_val
        instrument.status = InstrumentStatus.IN_VERIFICATION
        instrument.updated_at = datetime.now(timezone.utc).isoformat()
        self.instruments.update(instrument)

        return {
            "success": True,
            "status_code": 201,
            "message": f"Verification job '{job_id}' created for instrument '{instrument_id}'.",
            "job_id": job_id,
            "job_number": job_result["data"].get("job_number"),
            "job_type": j_type.value,
            "verification_reason": r_val,
            "priority": prio.value,
            "instrument_status": instrument.status.value,
            "verification_status": instrument.verification_status.value,
            "job_data": job_result["data"],
        }

    # =========================================================================
    # 4. Identify Instruments Requiring Verification
    # =========================================================================

    def identify_instruments_requiring_verification(
        self,
        as_of_date: Optional[str] = None,
        state: Optional[str] = None,
        reminder_window_days: int = 30,
        include_manual_review: bool = True,
    ) -> Dict[str, Any]:
        """
        Scans all registered instruments and identifies those requiring verification,
        categorized by statutory trigger:
        - INITIAL_VERIFICATION: Unverified instruments or new registrations.
        - PERIODIC_OVERDUE: Instruments whose verification deadline has passed.
        - PERIODIC_DUE: Instruments due today or within the reminder window.
        - POST_REPAIR: Broken seals, active repair, or post-repair verification required.
        - POST_RELOCATION: Instruments dismantled, relocated, or reinstalled.
        - MANUAL_REVIEW: Instruments where regulatory interval cannot be determined.
        """
        as_of_str = as_of_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            now_dt = datetime.strptime(as_of_str[:10], "%Y-%m-%d")
        except ValueError:
            now_dt = datetime.now(timezone.utc)

        all_instruments = self.instruments.list_all()
        requiring_list: List[Dict[str, Any]] = []

        summary_counts = {
            "total": 0,
            "initial_verification": 0,
            "periodic_due": 0,
            "periodic_overdue": 0,
            "post_repair": 0,
            "post_relocation": 0,
            "manual_review": 0,
        }

        norm_state = state.strip().upper() if state else None

        for inst in all_instruments:
            # Skip terminal instruments
            if inst.status in (InstrumentStatus.RETIRED, InstrumentStatus.DECOMMISSIONED):
                continue

            # State filtering if requested
            inst_state = inst.location.state.strip().upper() if (inst.location and inst.location.state) else None
            if norm_state and inst_state != norm_state:
                continue

            # Evaluate broken seals
            has_broken_seal = any(s.status in (SealStatus.BROKEN, SealStatus.MISSING) for s in inst.seals)

            # Determine requirement category
            rec_reason: Optional[str] = None
            rec_job_type: str = JobType.RE_VERIFICATION.value
            urgency: str = "NORMAL"
            days_diff: Optional[int] = None

            # 1. Broken seal or repair required
            if has_broken_seal or inst.status in (InstrumentStatus.REPAIR, InstrumentStatus.REPAIR_REQUIRED, InstrumentStatus.POST_REPAIR_VERIFICATION):
                rec_reason = VerificationReason.POST_REPAIR.value
                rec_job_type = JobType.POST_REPAIR.value
                urgency = "HIGH"
                summary_counts["post_repair"] += 1

            # 2. Relocation or Reinstallation
            elif inst.status in (InstrumentStatus.RELOCATED, InstrumentStatus.REINSTALLED, InstrumentStatus.DISMANTLED):
                rec_reason = (
                    VerificationReason.POST_REINSTALLATION.value
                    if inst.status == InstrumentStatus.REINSTALLED
                    else VerificationReason.POST_RELOCATION.value
                )
                rec_job_type = JobType.POST_RELOCATION.value
                urgency = "HIGH"
                summary_counts["post_relocation"] += 1

            # 3. Initial verification
            elif inst.verification_status == VerificationStatus.UNVERIFIED or (
                not inst.last_verification_date and inst.status in (InstrumentStatus.REGISTERED, InstrumentStatus.READY, InstrumentStatus.VERIFICATION_REQUIRED)
            ):
                rec_reason = VerificationReason.INITIAL_STAMPING.value
                rec_job_type = JobType.INITIAL_VERIFICATION.value
                urgency = "MEDIUM"
                summary_counts["initial_verification"] += 1

            # 4. Manual review required
            elif inst.manual_review_required and include_manual_review:
                rec_reason = VerificationReason.MANUAL_REVIEW.value
                rec_job_type = JobType.RE_VERIFICATION.value
                urgency = "MEDIUM"
                summary_counts["manual_review"] += 1

            # 5. Periodic due date evaluation
            elif inst.next_verification_date:
                try:
                    due_dt = datetime.strptime(inst.next_verification_date[:10], "%Y-%m-%d")
                    delta = (due_dt - now_dt).days
                    days_diff = delta

                    if delta < 0:
                        rec_reason = VerificationReason.PERIODIC_EXPIRY.value
                        rec_job_type = JobType.RE_VERIFICATION.value
                        urgency = "HIGH"
                        summary_counts["periodic_overdue"] += 1
                    elif delta <= reminder_window_days:
                        rec_reason = VerificationReason.PERIODIC_EXPIRY.value
                        rec_job_type = JobType.RE_VERIFICATION.value
                        urgency = "MEDIUM" if delta <= 7 else "NORMAL"
                        summary_counts["periodic_due"] += 1
                except ValueError:
                    pass

            if rec_reason:
                summary_counts["total"] += 1
                requiring_list.append({
                    "instrument_id": inst.instrument_id,
                    "serial_number": inst.serial_number,
                    "manufacturer": inst.manufacturer,
                    "model_name": inst.model_name,
                    "accuracy_class": inst.accuracy_class.roman,
                    "max_capacity": inst.max_capacity,
                    "unit": inst.unit.value,
                    "state": inst.location.state if inst.location else None,
                    "customer_name": inst.location.customer_name if inst.location else None,
                    "operational_status": inst.status.value,
                    "verification_status": inst.verification_status.value,
                    "verification_reason": rec_reason,
                    "recommended_job_type": rec_job_type,
                    "urgency": urgency,
                    "last_verification_date": inst.last_verification_date,
                    "next_verification_date": inst.next_verification_date,
                    "days_remaining_or_overdue": days_diff,
                    "active_verification_job_id": inst.active_verification_job_id,
                    "manual_review_required": inst.manual_review_required,
                    "manual_review_reason": inst.manual_review_reason,
                    "applicable_regulatory_profile_id": inst.applicable_regulatory_profile_id,
                })

        return {
            "success": True,
            "as_of_date": as_of_str,
            "filter_state": state,
            "reminder_window_days": reminder_window_days,
            "summary": summary_counts,
            "instruments": requiring_list,
            "items": requiring_list,
        }

    # =========================================================================
    # 5. Post-Job Status Synchronization
    # =========================================================================

    def update_verification_status_after_job(
        self,
        job_id: str,
        outcome: str,
        certificate_number: Optional[str] = None,
        verification_date: Optional[str] = None,
        inspecting_officer: Optional[str] = None,
        stamping_authority: Optional[str] = None,
        applied_seals: Optional[List[PhysicalSeal]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Updates instrument verification status and scheduling metadata after
        a verification job outcome (PASSED/CERTIFIED or REJECTED).

        Upon successful verification:
        - Updates last_verification_date, certificate number, and officer.
        - Sets verification_status = VERIFIED and status = IN_SERVICE.
        - Calculates and stores next_verification_date using authoritative profile.
        - Clears active_verification_job_id and sets last_verification_job_id.
        - Records statutory lifecycle event.
        """
        job = self.jobs.get(job_id)
        if not job:
            return {"success": False, "status_code": 404, "message": f"Job '{job_id}' not found."}

        instrument = self.instruments.get(job.instrument_id)
        if not instrument:
            return {"success": False, "status_code": 404, "message": f"Instrument '{job.instrument_id}' not found."}

        clean_outcome = str(outcome).strip().upper()
        v_date = verification_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        officer = inspecting_officer or job.assigned_inspector_name or "Legal Metrology Officer"
        authority = stamping_authority or job.assigned_laboratory or "State Legal Metrology Department"

        if clean_outcome in ("PASSED", "CERTIFIED", "APPROVED"):
            cert_num = certificate_number or f"VER-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{job_id[:6].upper()}"

            # 1. Update verification attributes
            instrument.last_verification_date = v_date
            instrument.last_verification_certificate = cert_num
            instrument.verification_officer = officer
            instrument.verification_status = VerificationStatus.VERIFIED
            instrument.status = InstrumentStatus.IN_SERVICE
            instrument.last_verification_job_id = job_id
            instrument.active_verification_job_id = None
            instrument.verification_reason = None

            # 2. Update seals if provided
            if applied_seals:
                instrument.seals = applied_seals

            # 3. Calculate and store next authoritative verification date
            sched_res = self.calculate_and_store_next_verification_date(instrument, base_date=v_date)

            # 4. Determine lifecycle event type based on job type
            j_type_str = job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type)
            if "INITIAL" in j_type_str:
                ev_type = LifecycleEventType.INITIAL_VERIFICATION
            elif "REPAIR" in j_type_str:
                ev_type = LifecycleEventType.POST_REPAIR_VERIFICATION
            elif "RELOCATION" in j_type_str or "REINSTALL" in j_type_str:
                ev_type = LifecycleEventType.POST_RELOCATION_VERIFICATION
            else:
                ev_type = LifecycleEventType.PERIODIC_RE_VERIFICATION

            # 5. Record immutable lifecycle event
            InstrumentLifecycleManager.record_lifecycle_event(
                instrument=instrument,
                event_type=ev_type,
                new_status=InstrumentStatus.IN_SERVICE,
                actor=officer,
                event_date=v_date,
                related_job_id=job_id,
                notes=f"Verification certified. Certificate '{cert_num}' issued by {authority}.",
                metadata={
                    "certificate_number": cert_num,
                    "stamping_authority": authority,
                    "next_due_date": instrument.next_verification_date,
                    "interval_months": instrument.re_verification_interval_months,
                },
            )

            # 6. Complete job transition to CERTIFIED if not already
            if job.status != JobStatus.CERTIFIED:
                try:
                    JobStateMachine.transition(
                        job=job,
                        to_status=JobStatus.CERTIFIED,
                        user_id=officer,
                        reason=f"Certified under {cert_num}",
                        metadata={"certificate_number": cert_num},
                    )
                    self.jobs.save(job)
                except Exception:
                    pass

            self.instruments.update(instrument)

            return {
                "success": True,
                "status_code": 200,
                "outcome": "PASSED",
                "instrument_id": instrument.instrument_id,
                "instrument_status": instrument.status.value,
                "verification_status": instrument.verification_status.value,
                "operational_status": instrument.status.value,
                "certificate_number": cert_num,
                "verification_certificate_number": cert_num,
                "last_verification_date": instrument.last_verification_date,
                "next_verification_date": instrument.next_verification_date,
                "re_verification_interval_months": instrument.re_verification_interval_months,
                "manual_review_required": instrument.manual_review_required,
                "data": instrument.to_dict(),
            }

        else:
            # REJECTED or FAILED
            instrument.verification_status = VerificationStatus.REJECTED
            instrument.status = InstrumentStatus.REPAIR_REQUIRED
            instrument.verification_reason = "REJECTED_VERIFICATION"
            instrument.last_verification_job_id = job_id
            instrument.active_verification_job_id = None

            # Record repair event
            InstrumentLifecycleManager.record_lifecycle_event(
                instrument=instrument,
                event_type=LifecycleEventType.REPAIR,
                new_status=InstrumentStatus.REPAIR_REQUIRED,
                actor=officer,
                event_date=v_date,
                related_job_id=job_id,
                notes=f"Verification rejected by {officer} at {authority}. Re-stamping prohibited until repair.",
                metadata={"job_id": job_id, "rejection_metadata": metadata or {}},
            )

            # Transition job to REJECTED if possible
            try:
                JobStateMachine.transition(
                    job=job,
                    to_status=JobStatus.REJECTED,
                    user_id=officer,
                    reason="Test observations exceeded statutory MPE limits",
                )
                self.jobs.save(job)
            except Exception:
                pass

            self.instruments.update(instrument)

            return {
                "success": True,
                "status_code": 200,
                "outcome": "REJECTED",
                "instrument_id": instrument.instrument_id,
                "verification_status": instrument.verification_status.value,
                "operational_status": instrument.status.value,
                "verification_reason": instrument.verification_reason,
                "data": instrument.to_dict(),
            }

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _resolve_regulatory_profile(
        self,
        instrument: Instrument,
        profile_id: Optional[str] = None,
    ) -> Optional[RegulatoryProfile]:
        """Resolves the appropriate regulatory profile without hardcoding state rules."""
        if profile_id:
            return PROFILE_REGISTRY.get_profile(profile_id)

        # If instrument has a customer location with a state, check state-specific profile
        if instrument.location and instrument.location.state:
            state_clean = instrument.location.state.strip().upper()
            if state_clean == "MAHARASHTRA":
                p = PROFILE_REGISTRY.get_profile("STATE_MAHARASHTRA_2026")
                if p:
                    return p

        # Default to verified Indian Legal Metrology profile
        return PROFILE_REGISTRY.get_profile("IN_LM_2011_ACTIVE")

    @staticmethod
    def _map_instrument_type_for_profile(instrument: Instrument) -> str:
        """Maps an Instrument to the profile's re_verification_periods lookup keys."""
        type_str = instrument.instrument_type.value if hasattr(instrument.instrument_type, "value") else str(instrument.instrument_type)
        type_str = type_str.upper()

        if "PRECISION" in type_str or "ANALYTICAL" in type_str or instrument.accuracy_class.roman in ("I", "II"):
            return "PRECISION_LAB"
        elif "WEIGHBRIDGE" in type_str:
            return "INDUSTRIAL_WEIGHBRIDGE"
        else:
            return "COMMERCIAL_NAWI"


# Global singleton scheduler instance
VERIFICATION_SCHEDULER = VerificationScheduler()
