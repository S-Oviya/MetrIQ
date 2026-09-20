"""
MetrIQ Test Job Service — Person 3 (Job / Instrument Engineer)
==============================================================
Central service orchestrating test job creation, statutory GATC routing,
Person 2 regulatory test plan generation, regulatory profile association,
and instrument lifecycle updates.

Guarantees clear architectural separation:
- Person 3 owns the TEST JOB lifecycle and test plan assignment.
- Person 4 owns actual TEST EXECUTION and metrological test calculations.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

# Person 2 models & interfaces
from app.regulatory.models import AccuracyClass, MassUnit
from app.instruments.models import Instrument, InstrumentStatus
from app.instruments.registry import INSTRUMENT_REGISTRY, InstrumentRegistry
from app.instruments.lifecycle import InstrumentLifecycleManager
from app.instruments.model_approval import MODEL_APPROVAL_REGISTRY
from app.regulatory.profile import PROFILE_REGISTRY, ProfileStatus

from .models import (
    JobPriority,
    JobStatus,
    JobType,
    StatutoryRoutingInfo,
    TestJob,
    VerificationLocationType,
)
from .repository import TEST_JOB_REPOSITORY, TestJobRepository
from .state_machine import JobStateMachine, JobStateTransitionError
from .regulatory_adapter import RegulatoryAdapter
from .location_service import JOB_LOCATION_SERVICE, JobLocationService


class TestJobService:
    """
    Orchestrates test job workflows, connecting:
    Instrument -> Test Job -> Regulatory Profile -> Automatic Test Plan -> Person 4 Execution.
    """
    __test__ = False

    def __init__(
        self,
        job_repository: Optional[TestJobRepository] = None,
        instrument_registry: Optional[InstrumentRegistry] = None,
        location_service: Optional[JobLocationService] = None,
    ) -> None:
        self.jobs = job_repository or TEST_JOB_REPOSITORY
        self.instruments = instrument_registry or INSTRUMENT_REGISTRY
        self.location_service = location_service or JOB_LOCATION_SERVICE

    def create_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Creates a new statutory verification test job:
        1. Resolves instrument from registry (validates existence).
        2. Validates job type.
        3. Prevents duplicate job IDs and conflicting active jobs.
        4. Associates regulatory profile, version, and statutory rules via Person 2.
        5. Generates and attaches automatic test plan for Person 4 execution.
        6. Updates instrument operational status to IN_VERIFICATION.
        7. Saves job with state history and returns structured response.
        """
        # 1. Validate Instrument existence
        inst_id = str(payload.get("instrument_id") or "").strip()
        if not inst_id:
            return {
                "success": False,
                "status_code": 400,
                "message": "Field 'instrument_id' is required.",
            }

        instrument = self.instruments.get(inst_id)
        if not instrument:
            return {
                "success": False,
                "status_code": 404,
                "message": f"Instrument '{inst_id}' not found in registry.",
            }

        # 2. Validate Job Type
        raw_job_type = payload.get("job_type", "RE_VERIFICATION")
        try:
            job_type = JobType.from_value(raw_job_type)
        except ValueError as e:
            return {
                "success": False,
                "status_code": 422,
                "message": f"Invalid job_type: {str(e)}",
            }

        # 3. Duplicate Prevention
        custom_job_id = payload.get("job_id")
        if custom_job_id:
            clean_job_id = str(custom_job_id).strip()
            if self.jobs.exists(clean_job_id):
                return {
                    "success": False,
                    "status_code": 409,
                    "message": f"Test job with ID '{clean_job_id}' already exists in repository.",
                }
            job_id = clean_job_id
        else:
            job_id = f"JOB-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        # Check for duplicate active jobs on same instrument
        existing_jobs = self.jobs.get_by_instrument(instrument.instrument_id)
        active_jobs = [j for j in existing_jobs if not j.status.is_terminal]
        if active_jobs and not payload.get("allow_concurrent_jobs", False):
            active_ids = [j.job_id for j in active_jobs]
            return {
                "success": False,
                "status_code": 409,
                "message": (
                    f"Instrument '{instrument.instrument_id}' already has active test job(s): {', '.join(active_ids)}. "
                    "Complete or cancel existing jobs before initiating a new verification job."
                ),
                "active_job_ids": active_ids,
            }

        # 4. Resolve Model Approval ID
        model_approval_id = payload.get("model_approval_id")
        if not model_approval_id and instrument.model_approval_number:
            model_approval_id = instrument.model_approval_number

        # 5. Regulatory Profile & Version Association via RegulatoryAdapter
        requested_profile_id = payload.get("regulatory_profile_id") or payload.get("profile_id")
        profile_meta = RegulatoryAdapter.get_profile_and_version(requested_profile_id)
        reg_profile_id = profile_meta["profile_id"]
        reg_version = profile_meta["version"]

        # 6. Determine Applicable Tests & Rules via Person 2
        applicable_test_ids, _ = RegulatoryAdapter.determine_applicable_tests(
            instrument.to_dict(),
            is_type_evaluation=(job_type == JobType.MODEL_APPROVAL),
        )
        rule_references = [
            "Legal Metrology Act, 2009 (Sec. 24)",
            "Legal Metrology (General) Rules, 2011 (Seventh Schedule)",
            "OIML R 76-1:2006 (Non-automatic weighing instruments)",
        ]
        if job_type == JobType.MODEL_APPROVAL:
            rule_references.append("Legal Metrology (Approval of Models) Rules, 2011")

        # 7. Evaluate Statutory GATC Routing & Verification Location Integration
        strict_gatc = payload.get("strict_gatc_validation", True)
        try:
            loc_routing = self.location_service.resolve_job_location_and_routing(
                instrument=instrument,
                job_type=job_type,
                reason=payload.get("reason") or payload.get("verification_reason"),
                preferred_location_type=payload.get("verification_location_type"),
                testing_centre_id=payload.get("testing_centre_id"),
                testing_centre_name=payload.get("testing_centre_name") or payload.get("assigned_laboratory") or payload.get("laboratory"),
                gatc_reference=payload.get("gatc_reference") or payload.get("gatc_code"),
                profile_id=reg_profile_id,
                strict_gatc_validation=strict_gatc,
            )
        except ValueError as e:
            return {
                "success": False,
                "status_code": 422,
                "message": str(e),
            }

        routing_info = StatutoryRoutingInfo(
            eligible_for_gatc=loc_routing.routing_result.eligible_for_gatc,
            target_authority=loc_routing.routing_result.target_authority,
            authority_name=loc_routing.routing_result.authority_name,
            reason=loc_routing.routing_result.reason,
            requires_regulatory_confirmation=loc_routing.manual_review_flag,
            citation=loc_routing.routing_result.statutory_citation,
        )

        # 8. Invoke Person 2's Regulatory Test Plan Generator
        test_plan_data = RegulatoryAdapter.generate_automatic_test_plan(
            instrument_spec=instrument.to_regulatory_payload(),
            job_id=job_id,
            job_type_str=job_type.value,
            profile_id=reg_profile_id,
        )

        # Initial Status
        req_status_raw = payload.get("status")
        if req_status_raw:
            initial_status = JobStatus.from_value(req_status_raw)
        elif test_plan_data:
            initial_status = JobStatus.TEST_PLAN_GENERATED
        else:
            initial_status = JobStatus.CREATED

        # 9. Create TestJob entity
        created_by = str(payload.get("created_by", "SYSTEM"))
        job = TestJob(
            job_id=job_id,
            job_number=str(payload.get("job_number") or ""),
            instrument_id=instrument.instrument_id,
            model_approval_id=model_approval_id,
            job_type=job_type,
            status=initial_status,
            priority=JobPriority.from_value(payload.get("priority")),
            requested_date=payload.get("requested_date"),
            created_date=str(payload.get("created_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            scheduled_date=payload.get("scheduled_date"),
            assigned_laboratory=loc_routing.laboratory,
            testing_centre_id=loc_routing.testing_centre_id,
            testing_centre_name=loc_routing.test_centre,
            assigned_inspector_id=payload.get("assigned_inspector_id"),
            assigned_inspector_name=payload.get("assigned_inspector_name"),
            verification_location_type=loc_routing.verification_location_type,
            gatc_reference=loc_routing.gatc_reference,
            installation_location=loc_routing.installation_location,
            reason_for_verification=loc_routing.reason_for_verification,
            routing_decision=loc_routing.routing_decision,
            regulatory_rule_reference=loc_routing.regulatory_rule_reference,
            manual_review_flag=loc_routing.manual_review_flag,
            manual_review_reason=loc_routing.manual_review_reason,
            statutory_routing=routing_info,
            regulatory_profile_id=reg_profile_id,
            regulatory_version=reg_version,
            regulatory_rule_references=rule_references,
            applicable_tests=applicable_test_ids,
            test_plan_reference=f"TP-{job_id}" if test_plan_data else None,
            test_plan=test_plan_data,
            instrument_snapshot=instrument.to_dict(),
            created_by=created_by,
            updated_by=created_by,
            notes=str(payload.get("notes", "")),
        )

        # 10. Record initial creation transition
        JobStateMachine.transition(
            job=job,
            to_status=job.status,
            user_id=created_by,
            reason=f"Test job created for {job_type.value}. Regulatory profile {reg_profile_id} (v{reg_version}) attached.",
        )

        # 11. Transition instrument status to IN_VERIFICATION
        instrument.status = InstrumentStatus.IN_VERIFICATION
        self.instruments.update(instrument)

        # 12. Save job
        saved_job = self.jobs.save(job)

        # Emit statutory audit event for job creation
        try:
            from app.audit.service import AUDIT_SERVICE
            from app.audit.models import AuditAction, EntityType
            AUDIT_SERVICE.record_audit(
                actor=created_by,
                action=AuditAction.JOB_CREATED,
                entity_type=EntityType.JOB,
                entity_id=saved_job.job_id,
                new_value={
                    "status": saved_job.status.value,
                    "job_type": saved_job.job_type.value,
                    "instrument_id": saved_job.instrument_id,
                    "regulatory_profile_id": saved_job.regulatory_profile_id,
                    "has_test_plan": saved_job.test_plan is not None,
                },
                metadata={
                    "job_id": saved_job.job_id,
                    "instrument_id": inst_id,
                    "job_type": saved_job.job_type.value,
                },
                job_id=saved_job.job_id,
            )
        except Exception:
            pass

        return {
            "success": True,
            "status_code": 201,
            "message": f"Test job '{saved_job.job_id}' successfully created for instrument '{inst_id}'.",
            "job_id": saved_job.job_id,
            "job_number": saved_job.job_number,
            "status": saved_job.status.value,
            "job_type": saved_job.job_type.value,
            "regulatory_profile_id": saved_job.regulatory_profile_id,
            "regulatory_version": saved_job.regulatory_version,
            "statutory_routing": saved_job.statutory_routing.to_dict() if saved_job.statutory_routing else None,
            "has_test_plan": saved_job.test_plan is not None,
            "test_plan_reference": saved_job.test_plan_reference,
            "data": saved_job.to_dict(),
        }

    def execute_test(self, *args, **kwargs) -> Any:
        """
        Guards team architecture boundary.
        Person 3 owns Test Job management and test plan generation.
        Actual test execution and calculation engine are owned exclusively by Person 4.
        """
        raise NotImplementedError(
            "Person 3 does not perform test execution. "
            "Test execution and calculation engine are owned exclusively by Person 4."
        )

    def transition_job_status(
        self,
        job_id: str,
        to_status: str,
        user_id: str = "SYSTEM",
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes a controlled state machine transition on a job.
        Updates instrument operational status upon certification or rejection.
        """
        job = self.jobs.get(job_id)
        if not job:
            return {"success": False, "status_code": 404, "message": f"Job '{job_id}' not found."}

        try:
            target_status = JobStatus.from_value(to_status)
            JobStateMachine.transition(
                job=job,
                to_status=target_status,
                user_id=user_id,
                reason=reason,
                metadata=metadata,
            )
        except JobStateTransitionError as e:
            return {"success": False, "status_code": 400, "message": str(e)}

        # Update Instrument operational status on completion
        instrument = self.instruments.get(job.instrument_id)
        if instrument:
            if target_status in (JobStatus.CLOSED, JobStatus.CERTIFIED, JobStatus.APPROVED):
                instrument.status = InstrumentStatus.ACTIVE
                instrument.last_verification_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                if metadata and metadata.get("certificate_number"):
                    instrument.last_verification_certificate = str(metadata["certificate_number"])
                instrument.next_re_verification_due = (
                    InstrumentLifecycleManager.calculate_next_re_verification_due(
                        instrument, instrument.last_verification_date
                    )
                )
                self.instruments.update(instrument)
            elif target_status == JobStatus.REJECTED:
                instrument.status = InstrumentStatus.REPAIR_REQUIRED
                self.instruments.update(instrument)
            elif target_status == JobStatus.CANCELLED:
                instrument.status = InstrumentStatus.ACTIVE
                self.instruments.update(instrument)

        self.jobs.save(job)
        return {
            "success": True,
            "status_code": 200,
            "message": f"Job '{job_id}' status transitioned to {target_status.value}.",
            "status": target_status.value,
            "data": job.to_dict(),
        }

    def assign_inspector(
        self,
        job_id: str,
        inspector_id: str,
        inspector_name: str,
        testing_centre_id: Optional[str] = None,
        testing_centre_name: Optional[str] = None,
        scheduled_date: Optional[str] = None,
        assigned_by: str = "SYSTEM",
        verification_location_type: Optional[str] = None,
        gatc_reference: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Assigns an inspector and/or testing centre to a job.
        Validates verification location assignment against Person 2 statutory routing.
        Transitions the job to READY_FOR_TEST (or ASSIGNED).
        """
        job = self.jobs.get(job_id)
        if not job:
            return {"success": False, "status_code": 404, "message": f"Job '{job_id}' not found."}

        # Validate location assignment if location type is changed
        if verification_location_type:
            inst = self.instruments.get(job.instrument_id)
            if inst:
                valid, msg = self.location_service.validate_location_assignment(
                    instrument=inst,
                    location_type=verification_location_type,
                    job_type=job.job_type,
                )
                if not valid:
                    return {"success": False, "status_code": 422, "message": msg}
            job.verification_location_type = str(verification_location_type)

        job.assigned_inspector_id = inspector_id
        job.assigned_inspector_name = inspector_name
        if testing_centre_id:
            job.testing_centre_id = testing_centre_id
        if testing_centre_name:
            job.testing_centre_name = testing_centre_name
            job.assigned_laboratory = testing_centre_name
        if scheduled_date:
            job.scheduled_date = scheduled_date
        if gatc_reference:
            job.gatc_reference = str(gatc_reference)

        # Transition status to ASSIGNED (synonym for READY_FOR_TEST)
        if job.status in (JobStatus.TEST_PLAN_GENERATED, JobStatus.PLAN_GENERATED, JobStatus.VALIDATED):
            try:
                JobStateMachine.transition(
                    job=job,
                    to_status=JobStatus.ASSIGNED,
                    user_id=assigned_by,
                    reason=f"Inspector {inspector_name} ({inspector_id}) assigned. Testing scheduled for {scheduled_date or 'TBD'}.",
                )
            except JobStateTransitionError:
                pass

        self.jobs.save(job)

        # Emit audit event for inspector assignment
        try:
            from app.audit.service import AUDIT_SERVICE
            from app.audit.models import AuditAction, EntityType
            AUDIT_SERVICE.record_audit(
                actor=assigned_by,
                action=AuditAction.INSPECTOR_ASSIGNED,
                entity_type=EntityType.JOB,
                entity_id=job_id,
                new_value={"status": job.status.value, "inspector": inspector_name, "inspector_id": inspector_id},
                metadata={"job_id": job_id, "event": "inspector_assigned", "inspector_id": inspector_id, "inspector_name": inspector_name},
                job_id=job_id,
            )
        except Exception:
            pass

        return {
            "success": True,
            "status_code": 200,
            "message": f"Inspector '{inspector_name}' assigned to job '{job_id}'.",
            "data": job.to_dict(),
        }

    def evaluate_job_routing(
        self,
        instrument_id: str,
        job_type: Union[str, JobType] = JobType.RE_VERIFICATION,
        profile_id: Optional[str] = None,
        preferred_location_type: Optional[str] = None,
        testing_centre_id: Optional[str] = None,
        testing_centre_name: Optional[str] = None,
        gatc_reference: Optional[str] = None,
        strict_gatc_validation: bool = False,
    ) -> Dict[str, Any]:
        """
        Evaluates statutory routing and location recommendations for an instrument
        using Person 2's GATC evaluation engine without creating a job.
        """
        inst = self.instruments.get(instrument_id)
        if not inst:
            return {"success": False, "status_code": 404, "message": f"Instrument '{instrument_id}' not found."}

        try:
            res = self.location_service.resolve_job_location_and_routing(
                instrument=inst,
                job_type=job_type,
                preferred_location_type=preferred_location_type,
                testing_centre_id=testing_centre_id,
                testing_centre_name=testing_centre_name,
                gatc_reference=gatc_reference,
                profile_id=profile_id,
                strict_gatc_validation=strict_gatc_validation,
            )
            return {
                "success": True,
                "status_code": 200,
                "data": res.to_dict(),
            }
        except ValueError as e:
            return {"success": False, "status_code": 422, "message": str(e)}

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single job by its ID."""
        job = self.jobs.get(job_id)
        return job.to_dict() if job else None

    def get_job_test_plan(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the pre-calculated statutory test plan for Person 4 execution.
        Contains load points, eccentricity positions, repeatability cycles, and MPE limits.
        """
        job = self.jobs.get(job_id)
        if not job or not job.test_plan:
            return None
        return job.test_plan

    def list_jobs(
        self,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        instrument_id: Optional[str] = None,
        inspector_id: Optional[str] = None,
        testing_centre_id: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Queries and filters test jobs."""
        jobs = self.jobs.list_all(
            status=status,
            job_type=job_type,
            instrument_id=instrument_id,
            inspector_id=inspector_id,
            testing_centre_id=testing_centre_id,
            search=search,
        )
        return [j.to_dict() for j in jobs]

    def update_job(
        self,
        job_id: str,
        update_data: Dict[str, Any],
        updated_by: str = "SYSTEM",
    ) -> Dict[str, Any]:
        """
        Updates an existing test job (PUT/PATCH).
        Supports modifying schedule, notes, priority, inspector, testing centre, and location.
        Validates location assignments and prevents altering terminal jobs.
        """
        job = self.jobs.get(job_id)
        if not job:
            return {"success": False, "status_code": 404, "message": f"Job '{job_id}' not found."}

        if job.status.is_terminal:
            return {
                "success": False,
                "status_code": 400,
                "message": f"Cannot modify job '{job_id}' in terminal status '{job.status.value}'.",
            }

        # Validate location changes if present
        new_loc_type = update_data.get("verification_location_type")
        if new_loc_type:
            inst = self.instruments.get(job.instrument_id)
            if inst:
                valid, msg = self.location_service.validate_location_assignment(
                    instrument=inst,
                    location_type=new_loc_type,
                    job_type=job.job_type,
                )
                if not valid:
                    return {"success": False, "status_code": 422, "message": msg}
            job.verification_location_type = str(new_loc_type)

        # Update priority if present
        if "priority" in update_data and update_data["priority"] is not None:
            job.priority = JobPriority.from_value(update_data["priority"])

        # Update dates if present
        if "scheduled_date" in update_data:
            job.scheduled_date = update_data["scheduled_date"]
        if "requested_date" in update_data:
            job.requested_date = update_data["requested_date"]

        # Update inspector / testing centre
        if "assigned_inspector_id" in update_data:
            job.assigned_inspector_id = update_data["assigned_inspector_id"]
        if "assigned_inspector_name" in update_data:
            job.assigned_inspector_name = update_data["assigned_inspector_name"]
        if "testing_centre_id" in update_data:
            job.testing_centre_id = update_data["testing_centre_id"]
        if "testing_centre_name" in update_data:
            job.testing_centre_name = update_data["testing_centre_name"]
            job.assigned_laboratory = update_data["testing_centre_name"]
        if "assigned_laboratory" in update_data and "testing_centre_name" not in update_data:
            job.assigned_laboratory = update_data["assigned_laboratory"]
            job.testing_centre_name = update_data["assigned_laboratory"]
        if "gatc_reference" in update_data:
            job.gatc_reference = update_data["gatc_reference"]

        # Update notes & metadata
        if "notes" in update_data:
            job.notes = str(update_data["notes"])
        if "metadata" in update_data and isinstance(update_data["metadata"], dict):
            job.metadata.update(update_data["metadata"])

        job.updated_by = updated_by
        job.updated_at = datetime.now(timezone.utc).isoformat()

        saved_job = self.jobs.save(job)
        return {
            "success": True,
            "status_code": 200,
            "message": f"Job '{job_id}' successfully updated.",
            "data": saved_job.to_dict(),
        }

    def validate_job(
        self,
        job_id: str,
        user_id: str = "SYSTEM",
    ) -> Dict[str, Any]:
        """
        Performs comprehensive statutory validation of a test job.
        Checks:
        1. Instrument presence and metrological validity.
        2. Regulatory profile validity and active status.
        3. Statutory GATC / location routing compliance.
        4. Model approval envelope compliance (if applicable).
        5. Applicable test list completeness.
        Transitions job from DRAFT/CREATED to VALIDATED if checks pass.
        """
        job = self.jobs.get(job_id)
        if not job:
            return {"success": False, "status_code": 404, "message": f"Job '{job_id}' not found."}

        inst = self.instruments.get(job.instrument_id)
        if not inst:
            return {"success": False, "status_code": 404, "message": f"Instrument '{job.instrument_id}' for job '{job_id}' not found."}

        checks: List[Dict[str, Any]] = []

        # Check 1: Instrument metrology validation
        metrology_check = RegulatoryAdapter.validate_metrology_feasibility(inst.to_regulatory_payload())
        checks.append({
            "check": "metrological_feasibility",
            "passed": metrology_check.get("valid", False),
            "errors": metrology_check.get("errors", []),
            "warnings": metrology_check.get("warnings", []),
        })

        # Check 2: Regulatory Profile validity
        prof_valid = False
        prof_status = "UNKNOWN"
        if job.regulatory_profile_id:
            prof = PROFILE_REGISTRY.get_profile(job.regulatory_profile_id)
            if prof:
                prof_status = prof.verification_status.value if hasattr(prof.verification_status, "value") else str(prof.verification_status)
                prof_valid = prof.is_authoritative or prof.verification_status == ProfileStatus.ACTIVE
        checks.append({
            "check": "regulatory_profile_status",
            "passed": prof_valid,
            "profile_id": job.regulatory_profile_id,
            "profile_status": prof_status,
            "requires_manual_review": not prof_valid or job.manual_review_flag,
        })

        # Check 3: Statutory Location / GATC compliance
        loc_valid = True
        loc_reason = "Compliant"
        if job.verification_location_type:
            loc_valid, loc_reason = self.location_service.validate_location_assignment(
                instrument=inst,
                location_type=job.verification_location_type,
                job_type=job.job_type,
            )
        checks.append({
            "check": "statutory_location_compliance",
            "passed": loc_valid,
            "location_type": job.verification_location_type,
            "reason": loc_reason,
        })

        # Check 4: Model Approval envelope check
        ma_passed = True
        ma_details: Dict[str, Any] = {"declared": False}
        if inst.model_approval_number:
            is_valid_ma, cert, ma_reasons = MODEL_APPROVAL_REGISTRY.verify_instrument(inst)
            ma_passed = is_valid_ma
            ma_details = {
                "declared": True,
                "approval_number": inst.model_approval_number,
                "certificate_found": cert is not None,
                "reasons": ma_reasons,
            }
        checks.append({
            "check": "model_approval_compliance",
            "passed": ma_passed,
            "details": ma_details,
        })

        # Check 5: Applicable tests
        tests_passed = len(job.applicable_tests) > 0
        checks.append({
            "check": "applicable_tests_determined",
            "passed": tests_passed,
            "test_count": len(job.applicable_tests),
            "test_ids": job.applicable_tests,
        })

        overall_valid = all(c["passed"] for c in checks)

        # Transition status to VALIDATED if in DRAFT or CREATED
        if overall_valid and job.status in (JobStatus.DRAFT, JobStatus.CREATED):
            try:
                JobStateMachine.transition(
                    job=job,
                    to_status=JobStatus.VALIDATED,
                    user_id=user_id,
                    reason="Pre-test statutory validation checks passed successfully.",
                )
                self.jobs.save(job)
            except JobStateTransitionError:
                pass

        # Emit audit event for validation
        try:
            from app.audit.service import AUDIT_SERVICE
            from app.audit.models import AuditAction, EntityType
            AUDIT_SERVICE.record_audit(
                actor=user_id,
                action=AuditAction.JOB_VALIDATED,
                entity_type=EntityType.JOB,
                entity_id=job.job_id,
                new_value={"status": job.status.value, "valid": overall_valid},
                metadata={"job_id": job.job_id, "validation_checks": len(checks), "all_passed": overall_valid},
                job_id=job.job_id,
            )
        except Exception:
            pass

        return {
            "success": True,
            "status_code": 200,
            "data": {
                "job_id": job.job_id,
                "job_number": job.job_number,
                "valid": overall_valid,
                "status": job.status.value,
                "checks": checks,
            },
        }

    def generate_job_test_plan(
        self,
        job_id: str,
        user_id: str = "SYSTEM",
        force_regenerate: bool = False,
    ) -> Dict[str, Any]:
        """
        Generates or re-generates statutory test plan for a test job via Person 2.
        Binds the test plan and reference, and transitions status to TEST_PLAN_GENERATED.
        """
        job = self.jobs.get(job_id)
        if not job:
            return {"success": False, "status_code": 404, "message": f"Job '{job_id}' not found."}

        if job.status.is_terminal:
            return {
                "success": False,
                "status_code": 400,
                "message": f"Cannot generate test plan for job '{job_id}' in terminal status '{job.status.value}'.",
            }

        if job.test_plan and not force_regenerate:
            return {
                "success": True,
                "status_code": 200,
                "message": f"Test plan already exists for job '{job_id}'. Use force_regenerate=true to overwrite.",
                "job_id": job.job_id,
                "test_plan_reference": job.test_plan_reference,
                "status": job.status.value,
                "data": job.test_plan,
            }

        inst = self.instruments.get(job.instrument_id)
        if not inst:
            return {"success": False, "status_code": 404, "message": f"Instrument '{job.instrument_id}' not found."}

        test_plan_data = RegulatoryAdapter.generate_automatic_test_plan(
            instrument_spec=inst.to_regulatory_payload(),
            job_id=job.job_id,
            job_type_str=job.job_type.value,
            profile_id=job.regulatory_profile_id,
        )

        if not test_plan_data:
            return {
                "success": False,
                "status_code": 422,
                "message": f"Failed to generate statutory test plan for instrument '{inst.instrument_id}'. Check instrument metrological specification.",
            }

        job.test_plan = test_plan_data
        job.test_plan_reference = f"TP-{job.job_id}"

        # Transition status to TEST_PLAN_GENERATED
        if job.status in (JobStatus.DRAFT, JobStatus.CREATED, JobStatus.VALIDATED):
            try:
                JobStateMachine.transition(
                    job=job,
                    to_status=JobStatus.TEST_PLAN_GENERATED,
                    user_id=user_id,
                    reason=f"Statutory test plan generated via Person 2 engine (Ref: {job.test_plan_reference}).",
                )
            except JobStateTransitionError:
                pass

        self.jobs.save(job)

        # Emit audit event for test plan generation
        try:
            from app.audit.service import AUDIT_SERVICE
            from app.audit.models import AuditAction, EntityType
            AUDIT_SERVICE.record_audit(
                actor=user_id,
                action=AuditAction.TEST_PLAN_GENERATED,
                entity_type=EntityType.JOB,
                entity_id=job.job_id,
                new_value={"status": job.status.value, "test_plan_reference": job.test_plan_reference},
                metadata={"job_id": job.job_id, "event": "test_plan_generated", "test_plan_reference": job.test_plan_reference},
                job_id=job.job_id,
            )
        except Exception:
            pass

        return {
            "success": True,
            "status_code": 200,
            "message": f"Statutory test plan generated and bound to job '{job.job_id}'.",
            "job_id": job.job_id,
            "test_plan_reference": job.test_plan_reference,
            "status": job.status.value,
            "data": job.test_plan,
        }


# Global singleton instance for application runtime
TEST_JOB_SERVICE = TestJobService()
