"""
MetrIQ P5 Test-Job Workflow Service
===================================
Person 5: Workflow + Evidence Engineer

Orchestrates atomic test-job state machine transitions, validation,
metadata logging, and audit history preservation.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional, Union
import uuid

from app.jobs.models import JobStateTransitionRecord, JobStatus, TestJob
from app.jobs.repository import TEST_JOB_REPOSITORY, TestJobRepository
from .state_machine import WorkflowStateMachine, WorkflowStateTransitionError


class JobNotFoundError(KeyError):
    """Raised when a requested test job does not exist in the repository."""

    def __init__(self, message: str, job_id: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.job_id = job_id


class WorkflowService:
    """
    Central domain service governing test-job lifecycle progression.
    Thread-safe and atomic.
    """

    def __init__(self, job_repository: Optional[TestJobRepository] = None) -> None:
        self.jobs = job_repository or TEST_JOB_REPOSITORY
        self._lock = threading.RLock()

    def transition_job(
        self,
        job_id: str,
        target_state: Union[str, JobStatus],
        actor: str = "SYSTEM",
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        test_execution_data: Optional[Dict[str, Any]] = None,
    ) -> TestJob:
        """
        Executes an atomic lifecycle transition on a test job:
        1. Loads the job.
        2. Determines current state.
        3. Validates the requested transition.
        4. Rejects invalid transitions with clear diagnostic errors.
        5. Updates the state atomically.
        6. Records transition metadata.
        7. Returns the updated job.
        """
        with self._lock:
            clean_job_id = str(job_id or "").strip()
            if not clean_job_id:
                raise JobNotFoundError("Job ID cannot be empty.")

            # 1. Load the job
            job = self.jobs.get(clean_job_id)
            if not job:
                raise JobNotFoundError(f"Job '{clean_job_id}' was not found.", job_id=clean_job_id)

            # 2. Determine current state
            current_state = job.status
            target_status = JobStatus.from_value(target_state)

            # 3. Validate the requested transition
            valid, err_code, err_msg = WorkflowStateMachine.can_transition(
                from_state=current_state,
                to_state=target_status,
                job=job,
                test_execution_data=test_execution_data,
                metadata=metadata,
            )

            # 4. Reject invalid transitions
            if not valid:
                raise WorkflowStateTransitionError(
                    message=err_msg or f"Job in {current_state.value} cannot transition directly to {target_status.value}",
                    error_code=err_code or "INVALID_STATE_TRANSITION",
                    current_state=current_state.value,
                    target_state=target_status.value,
                )

            # 5. Update the state atomically
            now_iso = datetime.now(timezone.utc).isoformat()
            prev_status_str = current_state.value
            new_status_str = target_status.value

            job.status = target_status
            job.updated_at = now_iso
            job.updated_by = str(actor or "SYSTEM")
            job.state_changed_at = now_iso

            # Attach test execution data if provided
            if test_execution_data:
                if job.test_execution_data:
                    job.test_execution_data.update(test_execution_data)
                else:
                    job.test_execution_data = dict(test_execution_data)

            if target_status == JobStatus.REPORT_GENERATED:
                job.completed_at = now_iso

            # 6. Record transition metadata (never silently overwrite previous state)
            transition_id = f"TR-{uuid.uuid4().hex[:8].upper()}"
            record = JobStateTransitionRecord(
                transition_id=transition_id,
                from_status=prev_status_str,
                to_status=new_status_str,
                timestamp=now_iso,
                user_id=str(actor or "SYSTEM"),
                reason=str(reason or f"State transitioned from {prev_status_str} to {new_status_str}"),
                metadata=dict(metadata or {}),
            )
            job.state_history.append(record)

            # Persist updated job
            saved_job = self.jobs.save(job)

            # Emit statutory audit log
            try:
                from app.audit.service import AUDIT_SERVICE
                from app.audit.models import AuditAction, EntityType
                AUDIT_SERVICE.record_audit(
                    actor=str(actor or "SYSTEM"),
                    action=AuditAction.JOB_STATE_CHANGED,
                    entity_type=EntityType.JOB,
                    entity_id=job.job_id,
                    old_value={"status": prev_status_str},
                    new_value={"status": new_status_str},
                    metadata={
                        "reason": record.reason,
                        "transition_id": record.transition_id,
                        **(metadata or {}),
                    },
                    job_id=job.job_id,
                )
            except Exception:
                pass

            return saved_job

    # Alias matching transitionJob specification
    def transitionJob(
        self,
        jobId: str,
        targetState: Union[str, JobStatus],
        actor: str = "SYSTEM",
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        test_execution_data: Optional[Dict[str, Any]] = None,
    ) -> TestJob:
        return self.transition_job(
            job_id=jobId,
            target_state=targetState,
            actor=actor,
            reason=reason,
            metadata=metadata,
            test_execution_data=test_execution_data,
        )


# Global singleton instance
WORKFLOW_SERVICE = WorkflowService()


def transition_job(
    job_id: str,
    target_state: Union[str, JobStatus],
    actor: str = "SYSTEM",
    reason: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    test_execution_data: Optional[Dict[str, Any]] = None,
) -> TestJob:
    """Convenience domain function for job state transition."""
    return WORKFLOW_SERVICE.transition_job(
        job_id=job_id,
        target_state=target_state,
        actor=actor,
        reason=reason,
        metadata=metadata,
        test_execution_data=test_execution_data,
    )


def transitionJob(
    jobId: str,
    targetState: Union[str, JobStatus],
    actor: str = "SYSTEM",
    reason: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    test_execution_data: Optional[Dict[str, Any]] = None,
) -> TestJob:
    """CamelCase convenience domain function for job state transition."""
    return WORKFLOW_SERVICE.transition_job(
        job_id=jobId,
        target_state=targetState,
        actor=actor,
        reason=reason,
        metadata=metadata,
        test_execution_data=test_execution_data,
    )
