"""
MetrIQ Job Lifecycle State Machine — Person 3 (Job / Instrument Engineer)
========================================================================
Enforces strict statutory lifecycle state transitions and audit logging for
weighing instrument test jobs under Legal Metrology Rules.

Governs the controlled sequence:
DRAFT -> CREATED -> VALIDATED -> TEST_PLAN_GENERATED -> READY_FOR_TEST -> IN_TESTING
-> TEST_COMPLETED -> UNDER_REVIEW -> APPROVED / REJECTED -> CLOSED
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .models import JobStateTransitionRecord, JobStatus, TestJob


class JobStateTransitionError(ValueError):
    """Raised when an invalid state transition is attempted on a TestJob."""
    pass


class JobStateMachine:
    """
    Statutory workflow state machine governing test job progression.
    Guarantees that a test job moves sequentially through verification gates.
    """

    ALLOWED_TRANSITIONS: Dict[JobStatus, Set[JobStatus]] = {
        JobStatus.DRAFT: {
            JobStatus.CREATED,
            JobStatus.VALIDATED,
            JobStatus.TEST_PLAN_GENERATED,
            JobStatus.PLAN_GENERATED,
            JobStatus.CANCELLED,
        },
        JobStatus.CREATED: {
            JobStatus.VALIDATED,
            JobStatus.TEST_PLAN_GENERATED,
            JobStatus.PLAN_GENERATED,
            JobStatus.CANCELLED,
        },
        JobStatus.VALIDATED: {
            JobStatus.TEST_PLAN_GENERATED,
            JobStatus.PLAN_GENERATED,
            JobStatus.READY_FOR_TEST,
            JobStatus.ASSIGNED,
            JobStatus.CANCELLED,
        },
        JobStatus.TEST_PLAN_GENERATED: {
            JobStatus.READY_FOR_TEST,
            JobStatus.ASSIGNED,
            JobStatus.IN_TESTING,
            JobStatus.IN_PROGRESS,
            JobStatus.CANCELLED,
        },
        JobStatus.PLAN_GENERATED: {
            JobStatus.READY_FOR_TEST,
            JobStatus.ASSIGNED,
            JobStatus.IN_TESTING,
            JobStatus.IN_PROGRESS,
            JobStatus.CANCELLED,
        },
        JobStatus.READY_FOR_TEST: {
            JobStatus.IN_TESTING,
            JobStatus.IN_PROGRESS,
            JobStatus.CANCELLED,
        },
        JobStatus.ASSIGNED: {
            JobStatus.IN_TESTING,
            JobStatus.IN_PROGRESS,
            JobStatus.READY_FOR_TEST,
            JobStatus.CANCELLED,
        },
        JobStatus.IN_TESTING: {
            JobStatus.TEST_COMPLETED,
            JobStatus.TESTS_COMPLETED,
            JobStatus.CANCELLED,
        },
        JobStatus.IN_PROGRESS: {
            JobStatus.TEST_COMPLETED,
            JobStatus.TESTS_COMPLETED,
            JobStatus.CANCELLED,
        },
        JobStatus.TEST_COMPLETED: {
            JobStatus.UNDER_REVIEW,
            JobStatus.SUBMITTED_FOR_REVIEW,
            JobStatus.IN_TESTING,
            JobStatus.IN_PROGRESS,
            JobStatus.CANCELLED,
        },
        JobStatus.TESTS_COMPLETED: {
            JobStatus.UNDER_REVIEW,
            JobStatus.SUBMITTED_FOR_REVIEW,
            JobStatus.IN_TESTING,
            JobStatus.IN_PROGRESS,
            JobStatus.CANCELLED,
        },
        JobStatus.UNDER_REVIEW: {
            JobStatus.APPROVED,
            JobStatus.REJECTED,
            JobStatus.IN_TESTING,
            JobStatus.IN_PROGRESS,
            JobStatus.CANCELLED,
        },
        JobStatus.SUBMITTED_FOR_REVIEW: {
            JobStatus.APPROVED,
            JobStatus.REJECTED,
            JobStatus.IN_TESTING,
            JobStatus.IN_PROGRESS,
            JobStatus.CANCELLED,
        },
        JobStatus.APPROVED: {
            JobStatus.CLOSED,
            JobStatus.CERTIFIED,
            JobStatus.CANCELLED,
        },
        JobStatus.REJECTED: {
            JobStatus.CLOSED,
            JobStatus.CANCELLED,
            JobStatus.DRAFT,
            JobStatus.CREATED,
        },
        JobStatus.CLOSED: set(),      # Terminal state
        JobStatus.CERTIFIED: set(),   # Terminal state
        JobStatus.CANCELLED: set(),   # Terminal state
    }

    @classmethod
    def can_transition(
        cls,
        from_status: Union[str, JobStatus],
        to_status: Union[str, JobStatus],
    ) -> Tuple[bool, str]:
        """Evaluates whether transitioning from from_status to to_status is permissible."""
        curr = JobStatus.from_value(from_status)
        target = JobStatus.from_value(to_status)

        if curr == target:
            return True, f"Job is already in {curr.value} status."

        allowed_targets = cls.ALLOWED_TRANSITIONS.get(curr, set())
        if target in allowed_targets:
            return True, f"Transition from {curr.value} to {target.value} is valid."

        allowed_names = [s.value for s in allowed_targets]
        return (
            False,
            f"Invalid transition from {curr.value} to {target.value}. "
            f"Permitted next states from {curr.value}: {allowed_names or 'None (Terminal state)'}.",
        )

    @classmethod
    def transition(
        cls,
        job: TestJob,
        to_status: Union[str, JobStatus],
        user_id: str = "SYSTEM",
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TestJob:
        """
        Executes and records a state transition on a TestJob.
        Appends an immutable JobStateTransitionRecord to the job's state history.
        """
        target = JobStatus.from_value(to_status)
        valid, msg = cls.can_transition(job.status, target)
        if not valid:
            raise JobStateTransitionError(msg)

        old_status = job.status
        job.status = target
        job.updated_at = datetime.now(timezone.utc).isoformat()
        job.updated_by = user_id

        if target in (JobStatus.CLOSED, JobStatus.CERTIFIED):
            job.completed_at = datetime.now(timezone.utc).isoformat()

        record = JobStateTransitionRecord(
            transition_id=f"TR-{datetime.now(timezone.utc).strftime('%H%M%S')}",
            from_status=old_status.value,
            to_status=target.value,
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_id=user_id,
            reason=reason or f"Status transitioned from {old_status.value} to {target.value}",
            metadata=dict(metadata or {}),
        )
        job.state_history.append(record)
        return job
