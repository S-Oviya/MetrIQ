"""
MetrIQ P5 Test-Job Workflow State Machine
==========================================
Person 5: Workflow + Evidence Engineer

Enforces strict legal metrology state transitions for NAWI test jobs.

Permitted Lifecycle Transitions:
--------------------------------
DRAFT → READY
READY → IN_PROGRESS
IN_PROGRESS → REVIEW
IN_PROGRESS → RETEST_REQUIRED
RETEST_REQUIRED → IN_PROGRESS
REVIEW → APPROVED
REVIEW → REJECTED
REVIEW → IN_PROGRESS
REJECTED → IN_PROGRESS
APPROVED → REPORT_GENERATED

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


class WorkflowStateMachine:
    """
    State machine governing statutory test job lifecycle progression.
    Enforces valid transitions and business rules.
    """

    VALID_TRANSITIONS: Dict[JobStatus, Set[JobStatus]] = {
        JobStatus.DRAFT: {JobStatus.READY},
        JobStatus.READY: {JobStatus.IN_PROGRESS},
        JobStatus.IN_PROGRESS: {JobStatus.REVIEW, JobStatus.RETEST_REQUIRED},
        JobStatus.RETEST_REQUIRED: {JobStatus.IN_PROGRESS},
        JobStatus.REVIEW: {JobStatus.APPROVED, JobStatus.REJECTED, JobStatus.IN_PROGRESS},
        JobStatus.REJECTED: {JobStatus.IN_PROGRESS},
        JobStatus.APPROVED: {JobStatus.REPORT_GENERATED},
        JobStatus.REPORT_GENERATED: set(),
    }

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

        # Terminal state check: REPORT_GENERATED cannot transition to anything
        if curr == JobStatus.REPORT_GENERATED:
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
                f"Job in {curr_name} cannot transition directly to {target_name}",
            )

        # Business Rule 2: A job cannot enter REVIEW unless the required test execution data is present.
        if target == JobStatus.REVIEW:
            has_data = False
            if test_execution_data:
                has_data = True
            elif metadata and (metadata.get("test_execution_data") or metadata.get("test_data")):
                has_data = True
            elif job:
                if job.test_execution_data:
                    has_data = True
                elif job.test_attempts and len(job.test_attempts) > 0:
                    has_data = True
                else:
                    try:
                        from app.attempts.repository import ATTEMPT_REPOSITORY
                        atts = ATTEMPT_REPOSITORY.get_attempts_by_job(job.job_id)
                        if atts and any(a.status.value == "COMPLETED" or a.result is not None for a in atts):
                            has_data = True
                    except Exception:
                        pass

            if not has_data:
                return (
                    False,
                    "MISSING_TEST_EXECUTION_DATA",
                    f"Job in {curr_name} cannot enter REVIEW without required test execution data",
                )

        return True, None, None
