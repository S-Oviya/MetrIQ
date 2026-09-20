"""
MetrIQ P5 Test-Job Workflow State Machine
==========================================
Person 5: Workflow + Evidence Engineer

Enforces strict legal metrology state transitions for NAWI test jobs.

Canonical Execution Vocabulary (P5)
------------------------------------
IN_PROGRESS  — active test execution
REVIEW       — submitted for supervisory review
APPROVED     — reviewer signed-off
REPORT_GENERATED — certificate/report generated

P3 Status Bridge
-----------------
P3 creates jobs that progress through its own pipeline before reaching
execution.  The following P3 statuses are valid *source* states for the
→ IN_PROGRESS transition so that TestExecutionService, AttemptService, and
ReviewService never need to know about P3 internals:

  DRAFT, CREATED, VALIDATED, TEST_PLAN_GENERATED, PLAN_GENERATED,
  READY_FOR_TEST, ASSIGNED, IN_TESTING

Once IN_PROGRESS is reached (either from P5 READY or any of the above P3
states), the pure P5 vocabulary takes over for the remainder of the job's
life.

P3 Terminal State Bridge
-------------------------
After APPROVED, P3 expects CLOSED or CERTIFIED.  Those are treated as
aliases for REPORT_GENERATED in the execution vocabulary:
  APPROVED → CLOSED
  APPROVED → CERTIFIED
  APPROVED → REPORT_GENERATED

P3 REVIEW Alias Bridge
-----------------------
P3 uses UNDER_REVIEW / SUBMITTED_FOR_REVIEW as aliases for REVIEW.  These
are valid source states for the REVIEW-stage transitions.

Permitted Lifecycle Transitions
--------------------------------
Any P3 pre-execution status → IN_PROGRESS

READY              → IN_PROGRESS
IN_PROGRESS        → REVIEW
IN_PROGRESS        → RETEST_REQUIRED
RETEST_REQUIRED    → IN_PROGRESS

# P3 REVIEW aliases
UNDER_REVIEW           → APPROVED, REJECTED, IN_PROGRESS
SUBMITTED_FOR_REVIEW   → APPROVED, REJECTED, IN_PROGRESS
# P5 canonical
REVIEW                 → APPROVED, REJECTED, IN_PROGRESS

REJECTED           → IN_PROGRESS

# Report / terminal aliases
APPROVED           → REPORT_GENERATED, CLOSED, CERTIFIED

No other transitions are permitted.
"""

from typing import Any, Dict, Optional, Set, Tuple, Union
from app.jobs.models import JobStatus, TestJob


class WorkflowStateTransitionError(ValueError):
    """Raised when an invalid state transition is attempted on a TestJob."""

    def __init__(
        self,
        message: str,
        error_code: str = "INVALID_STATE_TRANSITION",
        current_state: Optional[str] = None,
        target_state: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.current_state = current_state
        self.target_state = target_state


# ---------------------------------------------------------------------------
# Statuses that represent "execution-ready" (any of these → IN_PROGRESS)
# ---------------------------------------------------------------------------
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
}

# Statuses that represent "in review" (P3 aliases + P5 canonical)
_REVIEW_STATUSES: Set[JobStatus] = {
    JobStatus.REVIEW,
    JobStatus.UNDER_REVIEW,
    JobStatus.SUBMITTED_FOR_REVIEW,
}

# Statuses that represent "report/certificate generated" (terminal aliases)
_REPORT_GENERATED_STATUSES: Set[JobStatus] = {
    JobStatus.REPORT_GENERATED,
    JobStatus.CLOSED,
    JobStatus.CERTIFIED,
}


class WorkflowStateMachine:
    """
    State machine governing statutory test job lifecycle progression.
    Enforces valid transitions and business rules.

    The VALID_TRANSITIONS table is the single authority for what moves are
    legal.  P3 status aliases are resolved here so every service above this
    layer can treat the workflow as a clean P5 machine.
    """

    VALID_TRANSITIONS: Dict[JobStatus, Set[JobStatus]] = {
        # ── P3 pre-execution statuses → IN_PROGRESS ──────────────────────
        JobStatus.DRAFT:               {JobStatus.IN_PROGRESS, JobStatus.READY},
        JobStatus.CREATED:             {JobStatus.IN_PROGRESS, JobStatus.READY},
        JobStatus.VALIDATED:           {JobStatus.IN_PROGRESS, JobStatus.READY},
        JobStatus.TEST_PLAN_GENERATED: {JobStatus.IN_PROGRESS, JobStatus.READY},
        JobStatus.PLAN_GENERATED:      {JobStatus.IN_PROGRESS, JobStatus.READY},
        JobStatus.READY_FOR_TEST:      {JobStatus.IN_PROGRESS, JobStatus.READY},
        JobStatus.ASSIGNED:            {JobStatus.IN_PROGRESS, JobStatus.READY, JobStatus.READY_FOR_TEST},
        JobStatus.IN_TESTING:          {JobStatus.IN_PROGRESS},

        # ── P5 canonical execution states ────────────────────────────────
        JobStatus.READY:               {JobStatus.IN_PROGRESS},
        JobStatus.IN_PROGRESS:         {
            JobStatus.REVIEW,
            JobStatus.UNDER_REVIEW,           # P3 alias accepted as target
            JobStatus.SUBMITTED_FOR_REVIEW,   # P3 alias accepted as target
            JobStatus.RETEST_REQUIRED,
        },
        JobStatus.RETEST_REQUIRED:     {JobStatus.IN_PROGRESS},

        # ── Review stage (P5 canonical + P3 aliases) ─────────────────────
        JobStatus.REVIEW:              {
            JobStatus.APPROVED,
            JobStatus.REJECTED,
            JobStatus.IN_PROGRESS,   # return-for-correction
        },
        JobStatus.UNDER_REVIEW:        {
            JobStatus.APPROVED,
            JobStatus.REJECTED,
            JobStatus.IN_PROGRESS,
        },
        JobStatus.SUBMITTED_FOR_REVIEW: {
            JobStatus.APPROVED,
            JobStatus.REJECTED,
            JobStatus.IN_PROGRESS,
        },

        # ── Post-review ──────────────────────────────────────────────────
        JobStatus.REJECTED:            {JobStatus.IN_PROGRESS},
        JobStatus.APPROVED:            {
            JobStatus.REPORT_GENERATED,
            JobStatus.CLOSED,      # P3 terminal alias
            JobStatus.CERTIFIED,   # P3 terminal alias
        },

        # ── Terminal states ───────────────────────────────────────────────
        JobStatus.REPORT_GENERATED:    set(),
        JobStatus.CLOSED:              set(),
        JobStatus.CERTIFIED:           set(),
        JobStatus.CANCELLED:           set(),
        JobStatus.TESTS_COMPLETED:     {
            # P3 creates TEST_COMPLETED / TESTS_COMPLETED as a step between
            # execution and review; allow it to enter the review pipeline.
            JobStatus.REVIEW,
            JobStatus.UNDER_REVIEW,
            JobStatus.SUBMITTED_FOR_REVIEW,
            JobStatus.IN_PROGRESS,   # re-open for more tests
        },
        JobStatus.TEST_COMPLETED:      {
            JobStatus.REVIEW,
            JobStatus.UNDER_REVIEW,
            JobStatus.SUBMITTED_FOR_REVIEW,
            JobStatus.IN_PROGRESS,
        },
    }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def _is_terminal(cls, status: JobStatus) -> bool:
        return status in (
            JobStatus.REPORT_GENERATED,
            JobStatus.CLOSED,
            JobStatus.CERTIFIED,
            JobStatus.CANCELLED,
        )

    @classmethod
    def _is_review_stage(cls, status: JobStatus) -> bool:
        return status in _REVIEW_STATUSES

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def can_transition(
        cls,
        from_state: Union[str, JobStatus],
        to_state: Union[str, JobStatus],
        job: Optional[TestJob] = None,
        test_execution_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Evaluates whether transitioning from from_state to to_state is permissible.

        Returns:
            Tuple[bool, Optional[str], Optional[str]]:
                (is_valid, error_code, error_message)
        """
        curr = JobStatus.from_value(from_state)
        target = JobStatus.from_value(to_state)

        curr_name = curr.value
        target_name = target.value

        # Self-transitions are not permitted
        if curr == target:
            return (
                False,
                "INVALID_STATE_TRANSITION",
                f"Job is already in {curr_name} state. No transition occurred.",
            )

        # Terminal state check
        if cls._is_terminal(curr):
            return (
                False,
                "INVALID_STATE_TRANSITION",
                f"Job in terminal state {curr_name} cannot transition to {target_name}.",
            )

        # Check transition validity in state graph
        allowed_targets = cls.VALID_TRANSITIONS.get(curr, set())
        if target not in allowed_targets:
            return (
                False,
                "INVALID_STATE_TRANSITION",
                (
                    f"Job in {curr_name} cannot transition directly to {target_name}. "
                    f"Allowed next states: {sorted(s.value for s in allowed_targets) or 'none (terminal)'}."
                ),
            )

        # Business Rule: entering any review stage requires test execution data
        if cls._is_review_stage(target) or target in (
            JobStatus.REVIEW, JobStatus.UNDER_REVIEW, JobStatus.SUBMITTED_FOR_REVIEW
        ):
            has_data = _has_test_execution_data(job, test_execution_data, metadata)
            if not has_data:
                return (
                    False,
                    "MISSING_TEST_EXECUTION_DATA",
                    (
                        f"Job in {curr_name} cannot enter review without required test execution "
                        "data or completed attempts."
                    ),
                )

        return True, None, None


def _has_test_execution_data(
    job: Optional[TestJob],
    test_execution_data: Optional[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]],
) -> bool:
    """Return True if there is evidence of completed test execution."""
    if test_execution_data:
        return True
    if metadata and (metadata.get("test_execution_data") or metadata.get("test_data")):
        return True
    if job is None:
        return False
    if job.test_execution_data:
        return True
    if job.test_attempts and len(job.test_attempts) > 0:
        return True
    # Lazy check in the attempt repository
    try:
        from app.attempts.repository import ATTEMPT_REPOSITORY
        atts = ATTEMPT_REPOSITORY.get_attempts_by_job(job.job_id)
        if atts and any(
            a.status.value == "COMPLETED" or a.result is not None
            for a in atts
        ):
            return True
    except Exception:
        pass
    return False
