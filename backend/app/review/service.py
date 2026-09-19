"""
MetrIQ P5 Review & Approval Service
===================================
Person 5: Workflow + Evidence Engineer

Orchestrates review submission eligibility, supervisory authorization,
four-eyes principle enforcement, review decisions (APPROVE, REJECT, RETURN_FOR_CORRECTION),
and seamless state transitions via WORKFLOW_SERVICE.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from app.attempts.repository import ATTEMPT_REPOSITORY, AttemptRepository
from app.jobs.models import JobStatus, TestJob
from app.jobs.repository import TEST_JOB_REPOSITORY, TestJobRepository
from app.workflow.service import WORKFLOW_SERVICE, JobNotFoundError, WorkflowService
from app.workflow.state_machine import WorkflowStateTransitionError
from .models import Review, ReviewDecision, ReviewRole, ReviewStatus
from .repository import REVIEW_REPOSITORY, ReviewRepository


class ReviewNotFoundError(KeyError):
    """Raised when a requested review record cannot be found."""
    pass


class ReviewEligibilityError(ValueError):
    """Raised when a job does not meet the requirements to enter REVIEW."""

    def __init__(self, message: str, error_code: str = "JOB_NOT_READY_FOR_REVIEW"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class UnauthorizedReviewerError(ValueError):
    """Raised when an actor lacks authorization or violates four-eyes principle."""

    def __init__(self, message: str, error_code: str = "UNAUTHORIZED_REVIEWER"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class InvalidReviewDecisionError(ValueError):
    """Raised when a decision is invalid or missing required comments."""

    def __init__(self, message: str, error_code: str = "INVALID_REVIEW_DECISION", field: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.field = field


class ReviewWorkflowStateError(ValueError):
    """Raised when a review operation is attempted in an incompatible job state."""

    def __init__(self, message: str, error_code: str = "INVALID_JOB_STATE"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class ReviewService:
    """
    Central domain service governing Legal Metrology review and supervisory approval.
    Ensures complete chronological history and delegates transitions to WORKFLOW_SERVICE.
    """

    def __init__(
        self,
        review_repository: Optional[ReviewRepository] = None,
        job_repository: Optional[TestJobRepository] = None,
        attempt_repository: Optional[AttemptRepository] = None,
        workflow_service: Optional[WorkflowService] = None,
    ) -> None:
        self.reviews = review_repository or REVIEW_REPOSITORY
        self.jobs = job_repository or TEST_JOB_REPOSITORY
        self.attempts = attempt_repository or ATTEMPT_REPOSITORY
        self.workflow = workflow_service or WORKFLOW_SERVICE
        self._lock = threading.RLock()

    # =========================================================================
    # Eligibility & Verification Checks
    # =========================================================================

    def check_review_eligibility(self, job_id: str) -> Tuple[bool, Optional[str], Optional[TestJob]]:
        """
        Verifies whether a test job satisfies all prerequisites for review:
        1. Job must exist.
        2. Job must be in IN_PROGRESS state.
        3. Job must not be already APPROVED, REPORT_GENERATED, or terminal.
        4. Job must have completed test execution data or recorded attempts.
        """
        job = self.jobs.get(job_id)
        if not job:
            return False, f"Job '{job_id}' not found.", None

        # State check
        if job.status == JobStatus.APPROVED:
            return False, f"Job '{job_id}' is already APPROVED.", job
        if job.status == JobStatus.REPORT_GENERATED:
            return False, f"Job '{job_id}' has already completed certification (REPORT_GENERATED).", job
        if job.status != JobStatus.IN_PROGRESS:
            return False, f"Job '{job_id}' is in state '{job.status.value}'. Must be IN_PROGRESS to submit for review.", job

        # Execution data check
        has_execution_data = False
        if job.test_execution_data and len(job.test_execution_data) > 0:
            has_execution_data = True
        elif job.test_attempts and len(job.test_attempts) > 0:
            has_execution_data = True
        else:
            job_attempts = self.attempts.get_attempts_by_job(job_id)
            if job_attempts and any(a.status.value == "COMPLETED" or a.result is not None for a in job_attempts):
                has_execution_data = True

        if not has_execution_data:
            return (
                False,
                f"Job '{job_id}' cannot enter REVIEW without required test execution data or completed attempts.",
                job,
            )

        return True, None, job

    # =========================================================================
    # Submit for Review
    # =========================================================================

    def submit_for_review(
        self,
        job_id: str,
        reviewer: str = "UNASSIGNED",
        comments: str = "",
        submitted_by: str = "SYSTEM",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Review, TestJob]:
        """
        Submits a job for review:
        1. Validates review eligibility.
        2. Creates a PENDING Review record.
        3. Transitions job: IN_PROGRESS -> REVIEW using WORKFLOW_SERVICE.
        4. Updates job review references.
        """
        with self._lock:
            eligible, reason, job = self.check_review_eligibility(job_id)
            if not job:
                raise JobNotFoundError(f"Job '{job_id}' not found.", job_id=job_id)
            if not eligible:
                raise ReviewEligibilityError(reason or "Job is not eligible for review.")

            now_iso = datetime.now(timezone.utc).isoformat()
            review_id = f"REV-{uuid.uuid4().hex[:8].upper()}"

            meta = dict(metadata or {})
            meta["submitted_by"] = submitted_by

            review = Review(
                id=review_id,
                job_id=job.job_id,
                reviewer=str(reviewer or "UNASSIGNED").strip(),
                status=ReviewStatus.PENDING,
                decision=None,
                comments=str(comments or "").strip(),
                created_at=now_iso,
                updated_at=now_iso,
                metadata=meta,
            )

            # Transition job via existing WORKFLOW_SERVICE
            updated_job = self.workflow.transition_job(
                job_id=job.job_id,
                target_state=JobStatus.REVIEW,
                actor=submitted_by,
                reason=str(comments or "Submitted for supervisory review"),
                metadata={"review_id": review_id, "reviewer": review.reviewer},
                test_execution_data=job.test_execution_data,
            )

            # Link review on job
            updated_job.current_review_id = review.id
            if hasattr(updated_job, "review_ids") and review.id not in updated_job.review_ids:
                updated_job.review_ids.append(review.id)
            self.jobs.save(updated_job)

            self.reviews.save(review)

            # Emit statutory audit log
            try:
                from app.audit.service import AUDIT_SERVICE
                from app.audit.models import AuditAction, EntityType
                AUDIT_SERVICE.record_audit(
                    actor=str(submitted_by or "SYSTEM"),
                    action=AuditAction.REVIEW_SUBMITTED,
                    entity_type=EntityType.REVIEW,
                    entity_id=review.id,
                    new_value={"status": review.status.value, "reviewer": review.reviewer},
                    metadata={"job_id": job.job_id, "comments": review.comments},
                    job_id=job.job_id,
                )
            except Exception:
                pass

            return review, updated_job

    # =========================================================================
    # Review Decision Action (APPROVE / REJECT / RETURN_FOR_CORRECTION)
    # =========================================================================

    def execute_review(
        self,
        job_id: str,
        decision: Union[str, ReviewDecision],
        comments: str = "",
        reviewer: str = "REVIEWER",
        role: Optional[Union[str, ReviewRole]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Review, TestJob]:
        """
        Applies a review decision by an authorized reviewer:
        1. Validates job is currently in REVIEW state.
        2. Validates reviewer authorization and enforces the Four-Eyes Principle.
        3. Validates decision type and required comments.
        4. Updates the Review record to COMPLETED.
        5. Executes the state transition via WORKFLOW_SERVICE:
           - APPROVE -> REVIEW -> APPROVED
           - REJECT -> REVIEW -> REJECTED
           - RETURN_FOR_CORRECTION -> REVIEW -> IN_PROGRESS
        6. Preserves full review history.
        """
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                raise JobNotFoundError(f"Job '{job_id}' not found.", job_id=job_id)

            # 1. State check
            if job.status != JobStatus.REVIEW:
                if job.status == JobStatus.APPROVED:
                    raise ReviewWorkflowStateError(
                        f"Cannot review job '{job_id}': job is already APPROVED.",
                        error_code="JOB_ALREADY_APPROVED",
                    )
                raise ReviewWorkflowStateError(
                    f"Cannot review job '{job_id}': current state is '{job.status.value}', expected REVIEW.",
                    error_code="INVALID_JOB_STATE",
                )

            # 2. Reviewer authorization & Four-Eyes Principle
            clean_reviewer = str(reviewer or "").strip()
            if not clean_reviewer or clean_reviewer.upper() in ("UNASSIGNED", "ANONYMOUS"):
                raise UnauthorizedReviewerError(
                    "A valid, identifiable reviewer must be provided to render a review decision.",
                    error_code="UNAUTHORIZED_REVIEWER",
                )

            # Check role if supplied
            if role:
                clean_role = ReviewRole.from_value(role)
                if clean_role == ReviewRole.OPERATOR:
                    raise UnauthorizedReviewerError(
                        "Normal operators are not authorized to render statutory review decisions.",
                        error_code="UNAUTHORIZED_REVIEWER",
                    )

            # Four-Eyes Principle: Assigned inspector / testing operator cannot approve their own job
            prohibited_self_reviewers = set()
            if job.assigned_inspector_id:
                prohibited_self_reviewers.add(job.assigned_inspector_id.strip().upper())
            if hasattr(job, "assigned_operator") and getattr(job, "assigned_operator"):
                prohibited_self_reviewers.add(getattr(job, "assigned_operator").strip().upper())
            if job.created_by and job.created_by.upper() != "SYSTEM":
                prohibited_self_reviewers.add(job.created_by.strip().upper())

            # Check operators from recorded attempts
            for att in self.attempts.get_attempts_by_job(job.job_id):
                if att.operator:
                    prohibited_self_reviewers.add(att.operator.strip().upper())

            if clean_reviewer.upper() in prohibited_self_reviewers:
                raise UnauthorizedReviewerError(
                    f"Reviewer '{clean_reviewer}' conducted or was assigned to this test job. "
                    "Self-review and self-approval are strictly prohibited under Legal Metrology four-eyes rules.",
                    error_code="UNAUTHORIZED_REVIEWER",
                )

            # 3. Validate decision enum
            try:
                dec = ReviewDecision.from_value(decision)
            except ValueError as e:
                raise InvalidReviewDecisionError(str(e), error_code="INVALID_REVIEW_DECISION", field="decision")

            clean_comments = str(comments or "").strip()
            if dec in (ReviewDecision.REJECT, ReviewDecision.RETURN_FOR_CORRECTION) and not clean_comments:
                raise InvalidReviewDecisionError(
                    f"Comments explaining the rationale are required when decision is {dec.value}.",
                    error_code="INVALID_REVIEW_DECISION",
                    field="comments",
                )

            # 4. Locate or instantiate the review record
            review = self.reviews.get_current_for_job(job.job_id)
            now_iso = datetime.now(timezone.utc).isoformat()

            if not review or review.status == ReviewStatus.COMPLETED:
                review_id = f"REV-{uuid.uuid4().hex[:8].upper()}"
                review = Review(
                    id=review_id,
                    job_id=job.job_id,
                    reviewer=clean_reviewer,
                    status=ReviewStatus.COMPLETED,
                    decision=dec,
                    comments=clean_comments,
                    reviewed_at=now_iso,
                    created_at=now_iso,
                    updated_at=now_iso,
                    metadata=dict(metadata or {}),
                )
            else:
                review.reviewer = clean_reviewer
                review.status = ReviewStatus.COMPLETED
                review.decision = dec
                review.comments = clean_comments
                review.reviewed_at = now_iso
                review.updated_at = now_iso
                if metadata:
                    review.metadata.update(metadata)

            if role:
                review.metadata["role"] = str(role)

            # 5. Determine target state and transition via WORKFLOW_SERVICE
            if dec == ReviewDecision.APPROVE:
                target_state = JobStatus.APPROVED
                transition_reason = f"Supervisory approval granted by {clean_reviewer}. {clean_comments}".strip()
            elif dec == ReviewDecision.REJECT:
                target_state = JobStatus.REJECTED
                transition_reason = f"Job rejected by {clean_reviewer}. Reason: {clean_comments}".strip()
            else:  # RETURN_FOR_CORRECTION
                target_state = JobStatus.IN_PROGRESS
                transition_reason = f"Job returned for correction by {clean_reviewer}. Reason: {clean_comments}".strip()

            updated_job = self.workflow.transition_job(
                job_id=job.job_id,
                target_state=target_state,
                actor=clean_reviewer,
                reason=transition_reason,
                metadata={"review_id": review.id, "decision": dec.value},
            )

            # Update review pointer
            updated_job.current_review_id = review.id
            if hasattr(updated_job, "review_ids") and review.id not in updated_job.review_ids:
                updated_job.review_ids.append(review.id)
            self.jobs.save(updated_job)

            self.reviews.save(review)

            # Emit statutory audit log
            try:
                from app.audit.service import AUDIT_SERVICE
                from app.audit.models import AuditAction, EntityType
                if dec == ReviewDecision.APPROVE:
                    audit_action = AuditAction.REVIEW_APPROVED
                elif dec == ReviewDecision.REJECT:
                    audit_action = AuditAction.REVIEW_REJECTED
                else:
                    audit_action = AuditAction.REVIEW_RETURNED_FOR_CORRECTION

                AUDIT_SERVICE.record_audit(
                    actor=clean_reviewer,
                    action=audit_action,
                    entity_type=EntityType.REVIEW,
                    entity_id=review.id,
                    old_value={"status": ReviewStatus.PENDING.value, "decision": None},
                    new_value={"status": review.status.value, "decision": dec.value},
                    metadata={"job_id": job.job_id, "comments": clean_comments, "role": str(role or "")},
                    job_id=job.job_id,
                )
            except Exception:
                pass

            return review, updated_job

    # =========================================================================
    # Query Operations
    # =========================================================================

    def get_current_review(self, job_id: str) -> Optional[Review]:
        """Retrieves active or most recent review for a job."""
        return self.reviews.get_current_for_job(job_id)

    def get_review_history(self, job_id: str) -> List[Review]:
        """Retrieves all reviews for a job in chronological order."""
        job = self.jobs.get(job_id)
        if not job:
            raise JobNotFoundError(f"Job '{job_id}' not found.", job_id=job_id)
        return self.reviews.get_by_job(job_id)

    def get_review(self, review_id: str) -> Optional[Review]:
        """Retrieves a specific review by ID."""
        return self.reviews.get(review_id)


# Global singleton service
REVIEW_SERVICE = ReviewService()
