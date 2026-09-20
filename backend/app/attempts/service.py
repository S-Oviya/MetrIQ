"""
MetrIQ P5 Test Attempt & Retest Service
=======================================
Person 5: Workflow + Evidence Engineer

Orchestrates sequential test attempt tracking, completion recording,
and retest workflow transitions using the existing P5 state machine.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional, Union
import uuid

from app.calculations.models import TestType, Verdict
from app.jobs.models import JobStatus, TestJob
from app.jobs.repository import TEST_JOB_REPOSITORY, TestJobRepository
from app.workflow.service import WORKFLOW_SERVICE, JobNotFoundError, WorkflowService
from .models import AttemptStatus, RetestRequest, TestAttempt
from .repository import (
    ATTEMPT_REPOSITORY,
    AttemptRepository,
    DuplicateAttemptNumberError,
)


class AttemptNotFoundError(KeyError):
    """Raised when a test attempt cannot be found."""
    pass


class TestNotFoundError(KeyError):
    """Raised when a test ID is not recognized or not applicable for a job."""
    __test__ = False


class AttemptValidationError(ValueError):
    """Raised when attempt input or result data fails domain validation."""

    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.field = field


class AttemptJobStateError(ValueError):
    """Raised when an attempt operation is attempted in an invalid job lifecycle state."""

    def __init__(self, message: str, error_code: str = "INVALID_JOB_STATE"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class AttemptAlreadyCompletedError(ValueError):
    """Raised when attempting to complete an attempt that has already been completed."""

    def __init__(self, message: str, error_code: str = "ATTEMPT_ALREADY_COMPLETED"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class AttemptService:
    """
    Core domain service managing the lifecycle, sequential numbering,
    completion, and retest requests for test attempts on statutory Test Jobs.
    """

    def __init__(
        self,
        attempt_repository: Optional[AttemptRepository] = None,
        job_repository: Optional[TestJobRepository] = None,
        workflow_service: Optional[WorkflowService] = None,
    ) -> None:
        self.repo = attempt_repository or ATTEMPT_REPOSITORY
        self.jobs = job_repository or TEST_JOB_REPOSITORY
        self.workflow = workflow_service or WORKFLOW_SERVICE
        self._lock = threading.RLock()

    # =========================================================================
    # Helpers
    # =========================================================================

    def _validate_test_exists(self, job: TestJob, test_id: str) -> str:
        """Validates that a test ID is non-empty and applicable to the given job."""
        clean = str(test_id or "").strip()
        if not clean:
            raise AttemptValidationError("Field 'test_id' is required and cannot be empty.", field="test_id")

        # If job has explicit applicable tests or test_plan, verify test_id against them
        if job.applicable_tests:
            clean_upper = clean.upper()
            applicable_uppers = [t.upper() for t in job.applicable_tests]
            if clean_upper not in applicable_uppers:
                # Also check test_plan if present
                in_plan = False
                if job.test_plan and isinstance(job.test_plan, dict):
                    tests = job.test_plan.get("tests", [])
                    for t in tests:
                        if (
                            str(t.get("test_id", "")).upper() == clean_upper
                            or str(t.get("test_type", "")).upper() == clean_upper
                            or str(t.get("name", "")).upper() == clean_upper
                        ):
                            in_plan = True
                            break
                if not in_plan:
                    # Check if it's a recognized statutory TestType
                    try:
                        TestType.from_value(clean)
                    except ValueError:
                        raise TestNotFoundError(
                            f"Test '{clean}' is not an applicable test for job '{job.job_id}'. Applicable tests: {job.applicable_tests}"
                        )
        return clean

    # =========================================================================
    # 1. Starting an Attempt
    # =========================================================================

    def start_attempt(
        self,
        job_id: str,
        test_id: str,
        operator: str,
        entered_values: Optional[Dict[str, Any]] = None,
        test_run_id: Optional[str] = None,
        notes: str = "",
    ) -> TestAttempt:
        """
        Starts a new sequential test attempt for a test on an IN_PROGRESS job.
        Computes next sequential attempt number, records start time and operator.
        Does NOT assign a PASS/FAIL result at creation.
        """
        with self._lock:
            # 1. Verify job exists
            job = self.jobs.get(job_id)
            if not job:
                raise JobNotFoundError(f"Test job '{job_id}' not found.")

            # 2. Verify test exists / is applicable
            clean_test_id = self._validate_test_exists(job, test_id)

            # 3. Verify job is in an execution-ready workflow state.
            # IN_PROGRESS is the canonical execution state, but a job may arrive here
            # directly from a P3 status (ASSIGNED, READY_FOR_TEST, IN_TESTING, etc.)
            # when TestExecutionService has already auto-advanced it.  We accept all
            # of those rather than requiring a precise IN_PROGRESS check, because the
            # auto-advance in TestExecutionService may have already transitioned it or
            # may be calling us as part of that transition.
            _ATTEMPT_ALLOWED_STATUSES = {
                JobStatus.IN_PROGRESS,
                # P3 execution-ready aliases (accepted when arrived via TestExecutionService)
                JobStatus.READY_FOR_TEST,
                JobStatus.ASSIGNED,
                JobStatus.IN_TESTING,
            }
            if job.status not in _ATTEMPT_ALLOWED_STATUSES:
                raise AttemptJobStateError(
                    f"Cannot start test attempt: job '{job_id}' is in '{job.status.value}' state. "
                    f"Job must be in one of: "
                    f"{sorted(s.value for s in _ATTEMPT_ALLOWED_STATUSES)}.",
                    error_code="JOB_NOT_IN_PROGRESS",
                )

            # 4. Verify operator
            clean_operator = str(operator or "").strip()
            if not clean_operator:
                raise AttemptValidationError(
                    "Field 'operator' is required to start a test attempt.",
                    field="operator",
                )

            # 5. Determine next sequential attempt number
            attempt_number = self.repo.get_next_attempt_number(job.job_id, clean_test_id)

            # 6. Instantiate new attempt
            now_iso = datetime.now(timezone.utc).isoformat()
            attempt_id = f"ATT-{uuid.uuid4().hex[:8].upper()}"

            attempt = TestAttempt(
                id=attempt_id,
                test_id=clean_test_id,
                job_id=job.job_id,
                attempt_number=attempt_number,
                status=AttemptStatus.IN_PROGRESS,
                result=None,
                entered_values=dict(entered_values or {}),
                test_run_id=test_run_id,
                comments=str(notes or "").strip(),
                operator=clean_operator,
                started_at=now_iso,
                completed_at=None,
                created_at=now_iso,
                updated_at=now_iso,
            )

            # 7. Persist in repository
            self.repo.save_attempt(attempt)

            # 8. Synchronize with Job entity
            job.test_attempts.append(attempt.to_dict())
            job.updated_at = now_iso
            self.jobs.save(job)

            # Emit statutory audit log
            try:
                from app.audit.service import AUDIT_SERVICE
                from app.audit.models import AuditAction, EntityType
                AUDIT_SERVICE.record_audit(
                    actor=clean_operator,
                    action=AuditAction.TEST_ATTEMPT_STARTED,
                    entity_type=EntityType.TEST_ATTEMPT,
                    entity_id=attempt.id,
                    new_value={"status": attempt.status.value, "attempt_number": attempt.attempt_number},
                    metadata={"job_id": job.job_id, "test_id": clean_test_id, "operator": clean_operator},
                    job_id=job.job_id,
                )
            except Exception:
                pass

            return attempt

    # =========================================================================
    # 2. Completing an Attempt
    # =========================================================================

    def complete_attempt(
        self,
        attempt_id: str,
        result: Union[str, Verdict],
        comments: str = "",
        result_data: Optional[Dict[str, Any]] = None,
        entered_values: Optional[Dict[str, Any]] = None,
        test_run_id: Optional[str] = None,
        completed_by: Optional[str] = None,
    ) -> TestAttempt:
        """
        Completes an in-progress test attempt by recording its evaluated verdict
        (PASS, FAIL, INCONCLUSIVE), completion timestamp, and calculation references.
        Rejects completing an already completed attempt.
        """
        with self._lock:
            # 1. Verify attempt exists
            attempt = self.repo.get_attempt(attempt_id)
            if not attempt:
                raise AttemptNotFoundError(f"Test attempt '{attempt_id}' not found.")

            # 2. Reject if already completed
            if attempt.is_completed or attempt.result is not None:
                curr_res = attempt.result.value if hasattr(attempt.result, "value") else str(attempt.result)
                raise AttemptAlreadyCompletedError(
                    f"Test attempt '{attempt_id}' is already completed with result '{curr_res}'. "
                    "Completed attempts cannot be completed again.",
                    error_code="ATTEMPT_ALREADY_COMPLETED",
                )

            # 3. Validate result
            clean_res_str = str(result.value if hasattr(result, "value") else result).strip().upper()
            if clean_res_str not in ("PASS", "FAIL", "INCONCLUSIVE"):
                raise AttemptValidationError(
                    f"Invalid attempt result '{result}'. Supported results: PASS, FAIL, INCONCLUSIVE.",
                    field="result",
                )
            verdict = Verdict(clean_res_str)

            # 4. Update attempt
            now_iso = datetime.now(timezone.utc).isoformat()
            attempt.status = AttemptStatus.COMPLETED
            attempt.result = verdict
            attempt.completed_at = now_iso
            attempt.updated_at = now_iso
            if comments:
                attempt.comments = str(comments).strip()
            if result_data:
                attempt.result_data = dict(result_data)
            if entered_values:
                attempt.entered_values.update(entered_values)
            if test_run_id:
                attempt.test_run_id = test_run_id
            if completed_by:
                attempt.completed_by = str(completed_by).strip()

            # 5. Save in repository
            self.repo.save_attempt(attempt)

            # 6. Synchronize with Job entity
            job = self.jobs.get(attempt.job_id)
            if job:
                for idx, a_dict in enumerate(job.test_attempts):
                    if a_dict.get("id") == attempt.id:
                        job.test_attempts[idx] = attempt.to_dict()
                        break
                job.updated_at = now_iso
                self.jobs.save(job)

            # Emit statutory audit log
            try:
                from app.audit.service import AUDIT_SERVICE
                from app.audit.models import AuditAction, EntityType
                AUDIT_SERVICE.record_audit(
                    actor=str(completed_by or attempt.operator or "SYSTEM"),
                    action=AuditAction.TEST_ATTEMPT_COMPLETED,
                    entity_type=EntityType.TEST_ATTEMPT,
                    entity_id=attempt.id,
                    old_value={"status": AttemptStatus.IN_PROGRESS.value, "result": None},
                    new_value={"status": attempt.status.value, "result": attempt.result.value if attempt.result else None},
                    metadata={"job_id": attempt.job_id, "test_id": attempt.test_id, "attempt_number": attempt.attempt_number},
                    job_id=attempt.job_id,
                )
            except Exception:
                pass

            return attempt

    # =========================================================================
    # 3. Retest Handling
    # =========================================================================

    def request_retest(
        self,
        job_id: str,
        test_id: str,
        attempt_id: str,
        reason: str,
        requested_by: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RetestRequest:
        """
        Handles retest request for a failed test attempt:
        1. Verifies the attempt exists and was completed with FAIL verdict.
        2. Validates the retest reason and requesting operator.
        3. Moves the Job to RETEST_REQUIRED state using the existing WorkflowService.
        4. Preserves the failed attempt record without overwriting.
        5. Records and returns a RetestRequest audit entity.
        """
        with self._lock:
            # 1. Verify job exists
            job = self.jobs.get(job_id)
            if not job:
                raise JobNotFoundError(f"Test job '{job_id}' not found.")

            # 2. Verify attempt exists
            attempt = self.repo.get_attempt(attempt_id)
            if not attempt:
                raise AttemptNotFoundError(f"Test attempt '{attempt_id}' not found.")

            # 3. Verify attempt belongs to job and test
            if attempt.job_id != job.job_id:
                raise AttemptValidationError(
                    f"Attempt '{attempt_id}' belongs to job '{attempt.job_id}', not '{job_id}'.",
                    field="job_id",
                )
            if attempt.test_id.upper() != test_id.strip().upper():
                raise AttemptValidationError(
                    f"Attempt '{attempt_id}' belongs to test '{attempt.test_id}', not '{test_id}'.",
                    field="test_id",
                )

            # 4. Check that attempt is completed and was a FAIL
            if not attempt.is_completed:
                raise AttemptValidationError(
                    f"Cannot request retest: attempt '{attempt_id}' is still in progress. "
                    "Retest can only be requested for a completed FAIL attempt.",
                    field="attempt_id",
                )
            if attempt.result != Verdict.FAIL:
                res_str = attempt.result.value if hasattr(attempt.result, "value") else str(attempt.result)
                raise AttemptValidationError(
                    f"Cannot request retest for attempt '{attempt_id}' with result '{res_str}'. "
                    "Retest can only be requested for a completed FAIL attempt.",
                    field="result",
                )

            # 5. Validate reason and operator
            clean_reason = str(reason or "").strip()
            if not clean_reason:
                raise AttemptValidationError("Field 'reason' is required for retest request.", field="reason")

            clean_operator = str(requested_by or "").strip()
            if not clean_operator:
                raise AttemptValidationError("Field 'requested_by' is required for retest request.", field="requested_by")

            # 6. Verify job is currently in IN_PROGRESS
            if job.status != JobStatus.IN_PROGRESS:
                raise AttemptJobStateError(
                    f"Cannot transition to RETEST_REQUIRED: job '{job_id}' is currently in '{job.status.value}' state. "
                    "Job must be IN_PROGRESS to request a retest.",
                    error_code="INVALID_JOB_STATE",
                )

            # 7. Transition job to RETEST_REQUIRED via existing WorkflowService
            meta = dict(metadata or {})
            meta.update({
                "retest_test_id": test_id,
                "failed_attempt_id": attempt.id,
                "failed_attempt_number": attempt.attempt_number,
            })
            self.workflow.transition_job(
                job_id=job.job_id,
                target_state=JobStatus.RETEST_REQUIRED,
                actor=clean_operator,
                reason=clean_reason,
                metadata=meta,
            )

            # 8. Create and store RetestRequest
            now_iso = datetime.now(timezone.utc).isoformat()
            retest_req = RetestRequest(
                retest_id=f"RET-{uuid.uuid4().hex[:8].upper()}",
                job_id=job.job_id,
                test_id=test_id,
                attempt_id=attempt.id,
                attempt_number=attempt.attempt_number,
                reason=clean_reason,
                requested_by=clean_operator,
                requested_at=now_iso,
                metadata=meta,
            )
            self.repo.save_retest_request(retest_req)

            # 9. Update attempt reason
            attempt.reason = clean_reason
            attempt.updated_at = now_iso
            self.repo.save_attempt(attempt)

            # Emit statutory audit log
            try:
                from app.audit.service import AUDIT_SERVICE
                from app.audit.models import AuditAction, EntityType
                AUDIT_SERVICE.record_audit(
                    actor=clean_operator,
                    action=AuditAction.RETEST_REQUESTED,
                    entity_type=EntityType.RETEST_REQUEST,
                    entity_id=retest_req.retest_id,
                    metadata={
                        "job_id": job.job_id,
                        "test_id": test_id,
                        "attempt_id": attempt.id,
                        "attempt_number": attempt.attempt_number,
                        "reason": clean_reason,
                    },
                    job_id=job.job_id,
                )
            except Exception:
                pass

            return retest_req

    # =========================================================================
    # 4. Queries & Lookups
    # =========================================================================

    def get_attempts_for_test(self, job_id: str, test_id: str) -> List[TestAttempt]:
        """Returns all attempts for a test in chronological/sequential order."""
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                raise JobNotFoundError(f"Test job '{job_id}' not found.")
            return self.repo.get_attempts_for_test(job_id, test_id)

    def get_attempt(self, attempt_id: str) -> Optional[TestAttempt]:
        """Returns a single test attempt by ID."""
        with self._lock:
            return self.repo.get_attempt(attempt_id)

    def get_all_attempts_for_job(self, job_id: str) -> List[TestAttempt]:
        """Returns all attempts across all tests for a given job."""
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                raise JobNotFoundError(f"Test job '{job_id}' not found.")
            return self.repo.get_attempts_by_job(job_id)

    def get_retest_requests_for_job(self, job_id: str) -> List[RetestRequest]:
        """Returns all retest requests recorded for a job."""
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                raise JobNotFoundError(f"Test job '{job_id}' not found.")
            return self.repo.get_retest_requests_by_job(job_id)


# Global singleton service
ATTEMPT_SERVICE = AttemptService()
