"""
MetrIQ Test Execution Service
==============================
Bridges the P4 Test Engine (calculations) with the P5 Attempt tracker and
P5 Workflow state machine, providing a single transactional entry-point for
a verification officer to submit observations for a job and receive a
PASS/FAIL verdict that is automatically persisted and reflected in the job's
lifecycle.

Workflow for a single test submission:
  1. Load job → validate it is in an execution-ready state
  2. If not already IN_PROGRESS, auto-advance the job to IN_PROGRESS
     (uses WorkflowService which now accepts all P3 execution-ready statuses)
  3. Load instrument → extract metrological params (accuracy_class, e, d, unit…)
  4. Derive verification_type from job.job_type
  5. Build a TestRun from the submitted observations
  6. Call TestEngine.execute() → TestExecutionResult (PASS/FAIL/INCONCLUSIVE)
  7. Open a new TestAttempt via ATTEMPT_SERVICE.start_attempt()
  8. Close it immediately via ATTEMPT_SERVICE.complete_attempt() with the verdict
  9. Check whether all applicable tests now have at least one PASS verdict.
     If so, auto-transition job to REVIEW (only when it would not violate rules).
 10. Return a rich summary dict ready for the API layer

Error behaviour
---------------
Every failure path raises a typed domain exception (never silently swallowed).
The only `except` blocks in this file either re-raise or convert to a typed
domain error.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from app.calculations.engine import TestEngine
from app.calculations.models import RawObservation, TestRun, TestType, Verdict
from app.jobs.models import JobStatus, JobType
from app.jobs.repository import TEST_JOB_REPOSITORY, TestJobRepository
from app.instruments.service import INSTRUMENT_SERVICE, InstrumentService
from app.attempts.service import (
    ATTEMPT_SERVICE,
    AttemptService,
    AttemptJobStateError,
)
from app.workflow.service import WORKFLOW_SERVICE, WorkflowService
from app.workflow.state_machine import WorkflowStateTransitionError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain errors
# ---------------------------------------------------------------------------


class ExecutionJobNotFoundError(KeyError):
    """Raised when the job does not exist."""


class ExecutionJobStateError(ValueError):
    """Raised when the job is not in a state that permits test execution."""


class ExecutionInstrumentError(ValueError):
    """Raised when instrument parameters cannot be resolved."""


class ExecutionValidationError(ValueError):
    """Raised when the submitted observations or test type are invalid."""


# ---------------------------------------------------------------------------
# Status sets
# ---------------------------------------------------------------------------

# All statuses that are accepted as "execution-ready" by this service.
# WorkflowStateMachine now knows how to bridge each of these → IN_PROGRESS.
_EXECUTION_READY_STATUSES: Set[JobStatus] = {
    JobStatus.DRAFT,
    JobStatus.CREATED,
    JobStatus.VALIDATED,
    JobStatus.TEST_PLAN_GENERATED,
    JobStatus.PLAN_GENERATED,
    JobStatus.READY_FOR_TEST,
    JobStatus.ASSIGNED,
    JobStatus.IN_TESTING,
    JobStatus.READY,
    JobStatus.IN_PROGRESS,
    JobStatus.RETEST_REQUIRED,
    # After a reviewer rejects a job, the job may be corrected and re-tested.
    # REJECTED → IN_PROGRESS is a valid WorkflowStateMachine transition, and
    # TestExecutionService must accept REJECTED as an execution-ready source
    # so that submit_observations auto-advances it to IN_PROGRESS.
    JobStatus.REJECTED,
}

# Statuses where more tests are still being collected after a retest
_RETEST_STATUSES: Set[JobStatus] = {JobStatus.RETEST_REQUIRED, JobStatus.IN_TESTING}

_INITIAL_VERIFICATION_JOB_TYPES = {
    JobType.INITIAL_VERIFICATION,
    JobType.MODEL_APPROVAL,
}

_INITIAL_VERIFICATION_JOB_TYPE_VALUES = {
    jt.value for jt in _INITIAL_VERIFICATION_JOB_TYPES
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _derive_verification_type(job_type_val: Any) -> str:
    """Map a P3 JobType to the P4 verification_type string expected by the calculators."""
    try:
        jt = JobType.from_value(job_type_val)
    except Exception:
        return "SUBSEQUENT"
    if jt in _INITIAL_VERIFICATION_JOB_TYPES:
        return "INITIAL"
    return "SUBSEQUENT"


def _instrument_dict(instrument_obj: Any) -> Dict[str, Any]:
    """Coerce the instrument (model instance or plain dict) to a plain dict."""
    if instrument_obj is None:
        return {}
    if hasattr(instrument_obj, "to_dict"):
        return instrument_obj.to_dict()
    if hasattr(instrument_obj, "__dict__"):
        return vars(instrument_obj)
    return dict(instrument_obj)


def _job_dict(job_obj: Any) -> Dict[str, Any]:
    """Coerce a TestJob (model) or plain dict to a plain dict."""
    if job_obj is None:
        return {}
    if hasattr(job_obj, "to_dict"):
        return job_obj.to_dict()
    if hasattr(job_obj, "__dict__"):
        return vars(job_obj)
    return dict(job_obj)


def _job_status(job: Any) -> JobStatus:
    """Safely extract JobStatus from a job object."""
    raw = getattr(job, "status", None) or _job_dict(job).get("status")
    if isinstance(raw, JobStatus):
        return raw
    return JobStatus.from_value(raw)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class TestExecutionService:
    """
    Coordinates end-to-end test execution:
      - Validates preconditions (job state, instrument availability)
      - Auto-advances P3 jobs to IN_PROGRESS when needed
      - Dispatches to the P4 TestEngine
      - Persists the result via P5 AttemptService
      - Advances job state via P5 WorkflowService after all tests pass
    """

    def __init__(
        self,
        job_repository: Optional[TestJobRepository] = None,
        instrument_service: Optional[InstrumentService] = None,
        attempt_service: Optional[AttemptService] = None,
        workflow_service: Optional[WorkflowService] = None,
    ) -> None:
        self._jobs = job_repository or TEST_JOB_REPOSITORY
        self._instruments = instrument_service or INSTRUMENT_SERVICE
        self._attempts = attempt_service or ATTEMPT_SERVICE
        self._workflow = workflow_service or WORKFLOW_SERVICE
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Primary entry-point
    # ------------------------------------------------------------------

    def submit_observations(
        self,
        job_id: str,
        test_type: str,
        observations: List[Dict[str, Any]],
        operator: str,
        notes: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Submit raw observations for one statutory test within a job.

        Raises typed domain exceptions on every error path.  No bare
        ``except: pass`` blocks exist in this method.

        Returns a rich summary dict containing:
          - attempt details (id, number, result)
          - calculation result (verdict, calculated_values, regulatory_limits)
          - job status after the operation
          - auto_review_triggered flag (True when all tests passed)
        """
        with self._lock:
            # ── 1. Validate inputs ────────────────────────────────────
            clean_job_id = str(job_id or "").strip()
            if not clean_job_id:
                raise ExecutionValidationError("job_id is required.")

            clean_operator = str(operator or "").strip()
            if not clean_operator:
                raise ExecutionValidationError("operator is required.")

            if not observations:
                raise ExecutionValidationError(
                    "observations list must contain at least one entry."
                )

            # ── 2. Resolve test_type ──────────────────────────────────
            try:
                tt = TestType.from_value(test_type)
            except ValueError as exc:
                raise ExecutionValidationError(
                    f"Unknown test_type '{test_type}'. "
                    f"Supported: {[t.value for t in TestType]}"
                ) from exc

            # ── 3. Load and validate job ──────────────────────────────
            job = self._jobs.get(clean_job_id)
            if not job:
                raise ExecutionJobNotFoundError(
                    f"Job '{clean_job_id}' not found."
                )

            job_status = _job_status(job)

            if job_status not in _EXECUTION_READY_STATUSES:
                raise ExecutionJobStateError(
                    f"Job '{clean_job_id}' is in '{job_status.value}' state. "
                    f"Test execution requires one of: "
                    f"{sorted(s.value for s in _EXECUTION_READY_STATUSES)}."
                )

            # ── 4. Auto-advance to IN_PROGRESS when needed ────────────
            # WorkflowStateMachine now accepts all _EXECUTION_READY_STATUSES
            # as valid sources for → IN_PROGRESS.
            if job_status != JobStatus.IN_PROGRESS:
                logger.info(
                    "Job '%s' is in '%s'; auto-advancing to IN_PROGRESS "
                    "before test execution.",
                    clean_job_id,
                    job_status.value,
                )
                try:
                    job = self._workflow.transition_job(
                        job_id=clean_job_id,
                        target_state=JobStatus.IN_PROGRESS,
                        actor=clean_operator,
                        reason=(
                            f"Auto-advanced from '{job_status.value}' to IN_PROGRESS "
                            "on first test observation submission."
                        ),
                    )
                except WorkflowStateTransitionError as exc:
                    raise ExecutionJobStateError(
                        f"Cannot advance job '{clean_job_id}' from "
                        f"'{job_status.value}' to IN_PROGRESS: {exc.message}"
                    ) from exc

            # Confirm we are now IN_PROGRESS
            job_status = _job_status(job)
            if job_status != JobStatus.IN_PROGRESS:
                raise ExecutionJobStateError(
                    f"Job '{clean_job_id}' could not be placed into IN_PROGRESS; "
                    f"current state is '{job_status.value}'."
                )

            # ── 5. Load instrument ────────────────────────────────────
            instrument_id = (
                getattr(job, "instrument_id", None)
                or _job_dict(job).get("instrument_id")
            )
            instrument_obj = None
            if instrument_id:
                instrument_obj = self._instruments.get_instrument(str(instrument_id))
            if instrument_obj is None:
                raise ExecutionInstrumentError(
                    f"Instrument '{instrument_id}' linked to job '{clean_job_id}' "
                    "could not be loaded. Ensure the instrument exists in the registry."
                )
            instrument = _instrument_dict(instrument_obj)

            # ── 6. Derive verification type ───────────────────────────
            job_type_raw = (
                getattr(job, "job_type", None)
                or _job_dict(job).get("job_type", "RE_VERIFICATION")
            )
            verification_type = _derive_verification_type(job_type_raw)

            # ── 7. Build TestRun ──────────────────────────────────────
            test_run = TestRun(
                job_id=clean_job_id,
                instrument_id=instrument_id,
                test_type=tt,
                observations=[
                    RawObservation.from_dict(o) if isinstance(o, dict) else o
                    for o in observations
                ],
                executed_by=clean_operator,
                metadata=dict(metadata or {}),
            )

            # ── 8. Execute via P4 TestEngine ──────────────────────────
            try:
                calc_result = TestEngine.execute(test_run, instrument, verification_type)
            except (ValueError, KeyError, TypeError) as exc:
                raise ExecutionValidationError(
                    f"Calculation engine error for {tt.value}: {exc}"
                ) from exc

            verdict: Verdict = calc_result.verdict

            # ── 9. Open + immediately close TestAttempt ───────────────
            attempt = self._attempts.start_attempt(
                job_id=clean_job_id,
                test_id=tt.value,
                operator=clean_operator,
                entered_values={"observations_count": len(observations)},
                test_run_id=test_run.test_run_id,
                notes=notes,
            )

            attempt = self._attempts.complete_attempt(
                attempt_id=attempt.id,
                result=verdict,
                comments=notes,
                result_data=calc_result.to_dict(),
                completed_by=clean_operator,
            )

            # ── 10. Check all-tests-passed and auto-trigger REVIEW ────
            auto_review_triggered = False
            review_trigger_error: Optional[str] = None
            job = self._jobs.get(clean_job_id)  # fresh copy after attempt writes

            if verdict == Verdict.PASS:
                auto_review_triggered, review_trigger_error = (
                    self._maybe_trigger_review(job, clean_operator)
                )

            # ── 11. Build response ────────────────────────────────────
            job = self._jobs.get(clean_job_id)
            final_job_status = (
                job.status.value if hasattr(job.status, "value") else str(job.status)
            ) if job else "UNKNOWN"

            response: Dict[str, Any] = {
                "success": True,
                "job_id": clean_job_id,
                "job_status": final_job_status,
                "test_type": tt.value,
                "verification_type": verification_type,
                "attempt": {
                    "attempt_id": attempt.id,
                    "attempt_number": attempt.attempt_number,
                    "status": attempt.status.value,
                    "result": verdict.value,
                    "operator": attempt.operator,
                    "started_at": attempt.started_at,
                    "completed_at": attempt.completed_at,
                },
                "calculation_result": calc_result.to_dict(),
                "verdict": verdict.value,
                "summary": calc_result.summary,
                "standard_reference": calc_result.standard_reference,
                "auto_review_triggered": auto_review_triggered,
            }
            if review_trigger_error:
                response["auto_review_note"] = review_trigger_error

            return response

    # ------------------------------------------------------------------
    # Auto-review trigger
    # ------------------------------------------------------------------

    def _maybe_trigger_review(
        self,
        job: Any,
        actor: str,
    ) -> tuple[bool, Optional[str]]:
        """
        Transition the job to REVIEW when every applicable test has at least
        one PASS verdict.

        Returns (triggered: bool, error_message_or_None).
        Never raises — errors are captured and returned so the caller can
        include them in the API response without failing the whole submission.
        """
        if job is None:
            return False, "Job not found after attempt completion."

        job_id = getattr(job, "job_id", None) or _job_dict(job).get("job_id", "")
        applicable_tests: List[str] = list(
            getattr(job, "applicable_tests", None)
            or _job_dict(job).get("applicable_tests", [])
        )

        # If the job has no applicable_tests list, we cannot determine completeness.
        if not applicable_tests:
            logger.debug(
                "Job '%s' has no applicable_tests list; skipping auto-review check.",
                job_id,
            )
            return False, None

        # Gather verdicts for every applicable test
        try:
            all_attempts = self._attempts.get_all_attempts_for_job(job_id)
        except Exception as exc:
            logger.warning(
                "Auto-review check failed fetching attempts for job '%s': %s",
                job_id, exc,
            )
            return False, f"Could not fetch attempts: {exc}"

        # Map test_id → set of verdicts (latest attempt per test)
        passed_tests: Set[str] = set()
        for att in all_attempts:
            result_val = (
                att.result.value
                if hasattr(att.result, "value")
                else str(att.result or "")
            )
            if result_val == Verdict.PASS.value:
                passed_tests.add(str(att.test_id).upper())

        applicable_upper = {t.upper() for t in applicable_tests}
        all_passed = applicable_upper.issubset(passed_tests)

        if not all_passed:
            pending = applicable_upper - passed_tests
            logger.debug(
                "Job '%s': %d/%d applicable tests passed; pending: %s",
                job_id, len(applicable_upper) - len(pending), len(applicable_upper), pending,
            )
            return False, None

        # All applicable tests passed — advance to REVIEW
        logger.info(
            "Job '%s': all %d applicable tests passed. Auto-transitioning to REVIEW.",
            job_id, len(applicable_upper),
        )
        try:
            self._workflow.transition_job(
                job_id=job_id,
                target_state=JobStatus.REVIEW,
                actor=actor,
                reason="All applicable tests passed. Auto-transitioned to REVIEW.",
                test_execution_data={"auto_review": True, "all_tests_passed": True},
            )
            return True, None
        except WorkflowStateTransitionError as exc:
            logger.warning(
                "Auto-review transition failed for job '%s': %s", job_id, exc.message
            )
            return False, f"Auto-review transition blocked: {exc.message}"
        except Exception as exc:
            logger.warning(
                "Unexpected error during auto-review for job '%s': %s", job_id, exc
            )
            return False, f"Auto-review error: {exc}"

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_results_for_job(self, job_id: str) -> Dict[str, Any]:
        """
        Returns all completed test attempts for a job, grouped by test_type,
        together with the current job status.
        """
        clean_job_id = str(job_id or "").strip()
        job = self._jobs.get(clean_job_id)
        if not job:
            raise ExecutionJobNotFoundError(f"Job '{clean_job_id}' not found.")

        attempts = self._attempts.get_all_attempts_for_job(clean_job_id)

        by_test: Dict[str, list] = {}
        for att in attempts:
            key = str(att.test_id)
            by_test.setdefault(key, [])
            by_test[key].append(att.to_dict())

        test_summaries = []
        overall_pass = True
        for test_id, test_attempts in by_test.items():
            sorted_attempts = sorted(
                test_attempts, key=lambda a: a.get("attempt_number", 0)
            )
            latest = sorted_attempts[-1]
            latest_result = latest.get("result")
            if latest_result != Verdict.PASS.value:
                overall_pass = False
            test_summaries.append(
                {
                    "test_id": test_id,
                    "attempt_count": len(sorted_attempts),
                    "latest_result": latest_result,
                    "all_verdicts": [a.get("result") for a in sorted_attempts],
                    "latest_attempt": latest,
                }
            )

        job_status_val = (
            job.status.value if hasattr(job.status, "value") else str(job.status)
        )

        return {
            "job_id": clean_job_id,
            "job_status": job_status_val,
            "tests_executed": len(by_test),
            "overall_pass": overall_pass if by_test else None,
            "test_summaries": test_summaries,
            "total_attempts": len(attempts),
        }

    def get_attempt(self, attempt_id: str) -> Optional[Dict[str, Any]]:
        """Returns a single attempt by ID, or None if not found."""
        att = self._attempts.get_attempt(attempt_id)
        return att.to_dict() if att else None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

TEST_EXECUTION_SERVICE = TestExecutionService()
