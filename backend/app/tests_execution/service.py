"""
MetrIQ Test Execution Service
==============================
Bridges the P4 Test Engine (calculations) with the P5 Attempt tracker and
P5 Workflow state machine, providing a single transactional entry-point for
a verification officer to submit observations for a job and receive a
PASS/FAIL verdict that is automatically persisted and reflected in the job's
lifecycle.

Workflow for a single test submission:
  1. Load job → validate it is IN_PROGRESS (or IN_TESTING)
  2. Load instrument → extract metrological params (accuracy_class, e, d, unit…)
  3. Derive verification_type from job.job_type
  4. Build a TestRun from the submitted observations
  5. Call TestEngine.execute() → TestExecutionResult (PASS/FAIL/INCONCLUSIVE)
  6. Open a new TestAttempt via ATTEMPT_SERVICE.start_attempt()
  7. Close it immediately via ATTEMPT_SERVICE.complete_attempt() with the verdict
  8. On all-tests-PASS: advance job → TEST_COMPLETED (if using P3 state machine)
     or → REVIEW (if using P5 state machine)
  9. Return a rich summary dict ready for the API layer
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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
# Helpers
# ---------------------------------------------------------------------------

_INITIAL_VERIFICATION_JOB_TYPES = {
    JobType.INITIAL_VERIFICATION,
    JobType.MODEL_APPROVAL,
}

_IN_PROGRESS_STATUSES = {
    JobStatus.IN_PROGRESS,
    JobStatus.IN_TESTING,
    JobStatus.READY_FOR_TEST,
    JobStatus.READY,
}


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


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class TestExecutionService:
    """
    Coordinates end-to-end test execution:
      - Validates preconditions (job state, instrument availability)
      - Dispatches to the P4 TestEngine
      - Persists the result via P5 AttemptService
      - Optionally advances job state via P5 WorkflowService
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
        Submit raw observations for one test within a job.

        Parameters
        ----------
        job_id       : ID of the IN_PROGRESS job
        test_type    : One of the 10 statutory TestType values
        observations : List of RawObservation dicts
        operator     : Verification officer identifier
        notes        : Optional free-text comment
        metadata     : Optional extra metadata forwarded to the test run

        Returns a rich summary dict containing:
          - attempt details (id, number, result)
          - calculation result (verdict, calculated_values, regulatory_limits)
          - job status after the operation
        """
        with self._lock:
            # 1. Validate inputs
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

            # 2. Resolve and validate test_type
            try:
                tt = TestType.from_value(test_type)
            except ValueError as exc:
                raise ExecutionValidationError(
                    f"Unknown test_type '{test_type}'. "
                    f"Supported: {[t.value for t in TestType]}"
                ) from exc

            # 3. Load and validate job
            job = self._jobs.get(clean_job_id)
            if not job:
                raise ExecutionJobNotFoundError(
                    f"Job '{clean_job_id}' not found."
                )

            job_status = job.status if hasattr(job.status, "value") else JobStatus.from_value(job.status)
            if job_status not in _IN_PROGRESS_STATUSES:
                raise ExecutionJobStateError(
                    f"Job '{clean_job_id}' is in '{job_status.value}' state. "
                    "Test execution requires the job to be IN_PROGRESS, IN_TESTING, "
                    "READY_FOR_TEST, or READY."
                )

            # 4. Load instrument
            instrument_id = getattr(job, "instrument_id", None) or _job_dict(job).get("instrument_id")
            instrument_obj = None
            if instrument_id:
                instrument_obj = self._instruments.get_instrument(str(instrument_id))
            if instrument_obj is None:
                raise ExecutionInstrumentError(
                    f"Instrument '{instrument_id}' linked to job '{clean_job_id}' "
                    "could not be loaded. Ensure the instrument exists in the registry."
                )
            instrument = _instrument_dict(instrument_obj)

            # 5. Derive verification type from job type
            job_type_raw = getattr(job, "job_type", None) or _job_dict(job).get("job_type", "RE_VERIFICATION")
            verification_type = _derive_verification_type(job_type_raw)

            # 6. Build TestRun
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

            # 7. Execute via P4 TestEngine
            try:
                calc_result = TestEngine.execute(test_run, instrument, verification_type)
            except Exception as exc:
                raise ExecutionValidationError(
                    f"Calculation engine error for {tt.value}: {exc}"
                ) from exc

            verdict: Verdict = calc_result.verdict

            # 8. Ensure job is in IN_PROGRESS for the attempt service
            # The attempt service strictly requires IN_PROGRESS; if the job was
            # READY_FOR_TEST / IN_TESTING we auto-advance it first.
            if job_status != JobStatus.IN_PROGRESS:
                try:
                    self._workflow.transition_job(
                        job_id=clean_job_id,
                        target_state=JobStatus.IN_PROGRESS,
                        actor=clean_operator,
                        reason="Auto-advanced to IN_PROGRESS on first test observation submission.",
                    )
                    # Reload job to pick up the new status
                    job = self._jobs.get(clean_job_id)
                except Exception:
                    # If the transition fails (e.g. state machine doesn't allow it from this
                    # source state), carry on — the attempt service will surface the error.
                    pass

            # 9. Open attempt
            attempt = self._attempts.start_attempt(
                job_id=clean_job_id,
                test_id=tt.value,
                operator=clean_operator,
                entered_values={"observations_count": len(observations)},
                test_run_id=test_run.test_run_id,
                notes=notes,
            )

            # 10. Complete attempt with verdict and full result_data
            attempt = self._attempts.complete_attempt(
                attempt_id=attempt.id,
                result=verdict,
                comments=notes,
                result_data=calc_result.to_dict(),
                completed_by=clean_operator,
            )

            # 11. Reload job to get current state
            job = self._jobs.get(clean_job_id)
            final_job_status = (
                job.status.value if hasattr(job.status, "value") else str(job.status)
            ) if job else "UNKNOWN"

            return {
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
            }

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_results_for_job(self, job_id: str) -> Dict[str, Any]:
        """
        Returns all completed test attempts for a job, grouped by test_type,
        together with the current job status.

        This provides the reviewer with a complete picture of what was tested
        and what passed/failed before the REVIEW stage.
        """
        clean_job_id = str(job_id or "").strip()
        job = self._jobs.get(clean_job_id)
        if not job:
            raise ExecutionJobNotFoundError(f"Job '{clean_job_id}' not found.")

        attempts = self._attempts.get_all_attempts_for_job(clean_job_id)

        by_test: Dict[str, List[Dict[str, Any]]] = {}
        for att in attempts:
            key = str(att.test_id)
            by_test.setdefault(key, [])
            by_test[key].append(att.to_dict())

        # Per-test summary: latest result, attempt count, all verdicts
        test_summaries: List[Dict[str, Any]] = []
        overall_pass = True
        for test_id, test_attempts in by_test.items():
            sorted_attempts = sorted(test_attempts, key=lambda a: a.get("attempt_number", 0))
            latest = sorted_attempts[-1]
            latest_result = latest.get("result")
            if latest_result != Verdict.PASS.value:
                overall_pass = False
            test_summaries.append({
                "test_id": test_id,
                "attempt_count": len(sorted_attempts),
                "latest_result": latest_result,
                "all_verdicts": [a.get("result") for a in sorted_attempts],
                "latest_attempt": latest,
            })

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
