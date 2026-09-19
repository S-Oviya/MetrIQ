"""
MetrIQ P5 Review & Approval Workflow Unit Tests
===============================================
Person 5: Workflow + Evidence Engineer

Comprehensive test suite covering:
1. Review submission eligibility (IN_PROGRESS, test execution data presence, rejection of unready jobs).
2. Review decisions: APPROVE (-> APPROVED), REJECT (-> REJECTED), RETURN_FOR_CORRECTION (-> IN_PROGRESS).
3. Four-Eyes Principle and Role-based authorization: self-approval rejection, operator role rejection.
4. Multi-cycle review history preservation.
5. REST API endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.router import api_router
from app.attempts.models import AttemptStatus, TestAttempt, Verdict
from app.attempts.repository import ATTEMPT_REPOSITORY
from app.jobs.models import JobPriority, JobStatus, JobType, TestJob
from app.jobs.repository import TEST_JOB_REPOSITORY
from app.review.models import Review, ReviewDecision, ReviewRole, ReviewStatus
from app.review.repository import REVIEW_REPOSITORY
from app.review.service import (
    REVIEW_SERVICE,
    InvalidReviewDecisionError,
    ReviewEligibilityError,
    ReviewWorkflowStateError,
    UnauthorizedReviewerError,
)
from app.workflow.service import WORKFLOW_SERVICE, JobNotFoundError


@pytest.fixture(autouse=True)
def clean_repositories():
    """Ensures test isolation by resetting all P5 repositories before/after each test."""
    REVIEW_REPOSITORY.clear()
    TEST_JOB_REPOSITORY.clear()
    ATTEMPT_REPOSITORY.clear()
    yield
    REVIEW_REPOSITORY.clear()
    TEST_JOB_REPOSITORY.clear()
    ATTEMPT_REPOSITORY.clear()


@pytest.fixture
def client():
    """FastAPI test client with the integrated API router."""
    from fastapi import FastAPI
    app = FastAPI(title="Test MetrIQ P5 Review")
    app.include_router(api_router)
    return TestClient(app)


def _create_sample_job(
    job_id: str = "JOB-REV-001",
    status: JobStatus = JobStatus.IN_PROGRESS,
    applicable_tests: list = None,
    with_execution_data: bool = True,
    assigned_inspector: str = "INSP-LEGAL-01",
) -> TestJob:
    """Helper to persist a test job with specified status, tests, and execution data."""
    tests = applicable_tests if applicable_tests is not None else ["A.4.4", "A.4.7"]
    exec_data = {"completed": True, "verdict": "PASS"} if with_execution_data else None
    job = TestJob(
        job_id=job_id,
        instrument_id="INS-REV-001",
        job_type=JobType.INITIAL_VERIFICATION,
        status=status,
        priority=JobPriority.NORMAL,
        assigned_inspector_id=assigned_inspector,
        applicable_tests=tests,
        test_execution_data=exec_data,
        created_date="2026-09-19",
    )
    TEST_JOB_REPOSITORY.save(job)
    return job


def _create_sample_attempt(
    job_id: str = "JOB-REV-001",
    test_id: str = "A.4.4",
    attempt_number: int = 1,
    status: AttemptStatus = AttemptStatus.COMPLETED,
    verdict: Verdict = Verdict.PASS,
    operator: str = "INSP-LEGAL-01",
) -> TestAttempt:
    """Helper to persist a completed test attempt."""
    attempt_id = f"ATT-{job_id}-{test_id}-{attempt_number}"
    attempt = TestAttempt(
        id=attempt_id,
        job_id=job_id,
        test_id=test_id,
        attempt_number=attempt_number,
        operator=operator,
        started_at="2026-09-19T10:00:00Z",
        status=status,
        result=verdict,
        completed_at="2026-09-19T10:30:00Z",
    )
    ATTEMPT_REPOSITORY.save(attempt)
    return attempt


# =============================================================================
# 1. Submission & Eligibility Tests
# =============================================================================

class TestReviewSubmission:
    __test__ = True

    def test_eligible_job_submits_for_review_successfully(self):
        """Eligible IN_PROGRESS job with execution data transitions to REVIEW and creates PENDING review."""
        job = _create_sample_job("JOB-SUB-01", status=JobStatus.IN_PROGRESS, with_execution_data=True)
        review, updated_job = REVIEW_SERVICE.submit_for_review(
            job_id="JOB-SUB-01",
            reviewer="CONTROLLER-01",
            comments="Initial verification completed according to OIML R 76",
            submitted_by="INSP-01",
        )

        assert review.id.startswith("REV-")
        assert review.job_id == "JOB-SUB-01"
        assert review.status == ReviewStatus.PENDING
        assert review.reviewer == "CONTROLLER-01"
        assert review.decision is None
        assert updated_job.status == JobStatus.REVIEW
        assert updated_job.current_review_id == review.id

    def test_submission_with_attempt_data_instead_of_direct_flag(self):
        """Job without direct test_execution_data but with completed attempts in ATTEMPT_REPOSITORY is eligible."""
        job = _create_sample_job("JOB-SUB-02", status=JobStatus.IN_PROGRESS, with_execution_data=False)
        _create_sample_attempt(job_id="JOB-SUB-02", test_id="A.4.4", attempt_number=1)

        review, updated_job = REVIEW_SERVICE.submit_for_review("JOB-SUB-02", reviewer="CONTROLLER-01")
        assert updated_job.status == JobStatus.REVIEW
        assert review.status == ReviewStatus.PENDING

    def test_submission_fails_without_execution_data_or_attempts(self):
        """Job without test execution data or attempts cannot be submitted for review."""
        _create_sample_job("JOB-SUB-03", status=JobStatus.IN_PROGRESS, with_execution_data=False)
        with pytest.raises(ReviewEligibilityError) as exc_info:
            REVIEW_SERVICE.submit_for_review("JOB-SUB-03", reviewer="CONTROLLER-01")
        assert "cannot enter review without required test execution data" in str(exc_info.value).lower()

    def test_submission_fails_for_nonexistent_job(self):
        """Submitting nonexistent job raises JobNotFoundError (404)."""
        with pytest.raises(JobNotFoundError):
            REVIEW_SERVICE.submit_for_review("JOB-DOES-NOT-EXIST")

    def test_submission_fails_for_incompatible_states(self):
        """Jobs in DRAFT, READY, APPROVED cannot be submitted for review."""
        for state in (JobStatus.DRAFT, JobStatus.READY, JobStatus.APPROVED):
            jid = f"JOB-SUB-STATE-{state.value}"
            _create_sample_job(jid, status=state, with_execution_data=True)
            with pytest.raises((ReviewEligibilityError, ReviewWorkflowStateError)):
                REVIEW_SERVICE.submit_for_review(jid)


# =============================================================================
# 2. Review Decision Tests (APPROVE / REJECT / RETURN_FOR_CORRECTION)
# =============================================================================

class TestReviewDecisions:
    __test__ = True

    def test_approval_decision(self):
        """Authorized reviewer approves job; transitions REVIEW -> APPROVED."""
        job = _create_sample_job("JOB-DEC-01", status=JobStatus.IN_PROGRESS, assigned_inspector="INSP-A")
        review, _ = REVIEW_SERVICE.submit_for_review("JOB-DEC-01", reviewer="CONTROLLER-01")

        completed_rev, approved_job = REVIEW_SERVICE.execute_review(
            job_id="JOB-DEC-01",
            decision=ReviewDecision.APPROVE,
            comments="All MPE tolerance thresholds verified within permissible limits.",
            reviewer="CONTROLLER-01",
            role=ReviewRole.CONTROLLER,
        )

        assert completed_rev.id == review.id
        assert completed_rev.status == ReviewStatus.COMPLETED
        assert completed_rev.decision == ReviewDecision.APPROVE
        assert completed_rev.reviewed_at is not None
        assert approved_job.status == JobStatus.APPROVED

    def test_rejection_decision(self):
        """Authorized reviewer rejects job; transitions REVIEW -> REJECTED with comments."""
        job = _create_sample_job("JOB-DEC-02", status=JobStatus.IN_PROGRESS, assigned_inspector="INSP-A")
        REVIEW_SERVICE.submit_for_review("JOB-DEC-02", reviewer="CONTROLLER-01")

        completed_rev, rejected_job = REVIEW_SERVICE.execute_review(
            job_id="JOB-DEC-02",
            decision=ReviewDecision.REJECT,
            comments="Eccentricity error exceeded maximum permissible error on corner 3.",
            reviewer="CONTROLLER-01",
            role=ReviewRole.SENIOR_INSPECTOR,
        )

        assert completed_rev.status == ReviewStatus.COMPLETED
        assert completed_rev.decision == ReviewDecision.REJECT
        assert rejected_job.status == JobStatus.REJECTED

        # Rejected job can transition back to IN_PROGRESS for rework via WORKFLOW_SERVICE
        reworked_job = WORKFLOW_SERVICE.transition_job(
            job_id="JOB-DEC-02",
            target_state=JobStatus.IN_PROGRESS,
            actor="INSP-A",
            reason="Beginning corner re-alignment and retest",
        )
        assert reworked_job.status == JobStatus.IN_PROGRESS

    def test_return_for_correction_decision(self):
        """Reviewer returns job for correction; transitions REVIEW -> IN_PROGRESS."""
        job = _create_sample_job("JOB-DEC-03", status=JobStatus.IN_PROGRESS, assigned_inspector="INSP-A")
        REVIEW_SERVICE.submit_for_review("JOB-DEC-03", reviewer="CONTROLLER-01")

        completed_rev, returned_job = REVIEW_SERVICE.execute_review(
            job_id="JOB-DEC-03",
            decision=ReviewDecision.RETURN_FOR_CORRECTION,
            comments="Missing ambient atmospheric pressure log entry.",
            reviewer="CONTROLLER-01",
            role=ReviewRole.REVIEWER,
        )

        assert completed_rev.status == ReviewStatus.COMPLETED
        assert completed_rev.decision == ReviewDecision.RETURN_FOR_CORRECTION
        assert returned_job.status == JobStatus.IN_PROGRESS

    def test_rejection_requires_comments(self):
        """Rejection and return for correction strictly require explanatory comments."""
        _create_sample_job("JOB-DEC-04", status=JobStatus.IN_PROGRESS, assigned_inspector="INSP-A")
        REVIEW_SERVICE.submit_for_review("JOB-DEC-04", reviewer="CONTROLLER-01")

        with pytest.raises(InvalidReviewDecisionError):
            REVIEW_SERVICE.execute_review(
                job_id="JOB-DEC-04",
                decision=ReviewDecision.REJECT,
                comments="",  # Missing comments
                reviewer="CONTROLLER-01",
            )


# =============================================================================
# 3. Authorization & Four-Eyes Principle Tests
# =============================================================================

class TestReviewAuthorization:
    __test__ = True

    def test_self_approval_by_assigned_inspector_rejected(self):
        """Assigned inspector cannot review/approve their own job (Four-Eyes Principle)."""
        _create_sample_job("JOB-AUTH-01", status=JobStatus.IN_PROGRESS, assigned_inspector="INSP-OP-01")
        REVIEW_SERVICE.submit_for_review("JOB-AUTH-01")

        with pytest.raises(UnauthorizedReviewerError) as exc_info:
            REVIEW_SERVICE.execute_review(
                job_id="JOB-AUTH-01",
                decision=ReviewDecision.APPROVE,
                reviewer="INSP-OP-01",  # Same as assigned inspector
            )
        assert "self-review and self-approval are strictly prohibited" in str(exc_info.value).lower()

    def test_self_approval_by_attempt_operator_rejected(self):
        """Operator who performed test attempts cannot approve the job."""
        _create_sample_job("JOB-AUTH-02", status=JobStatus.IN_PROGRESS, assigned_inspector="INSP-GENERAL")
        _create_sample_attempt(job_id="JOB-AUTH-02", operator="OPERATOR-BOB")
        REVIEW_SERVICE.submit_for_review("JOB-AUTH-02")

        with pytest.raises(UnauthorizedReviewerError) as exc_info:
            REVIEW_SERVICE.execute_review(
                job_id="JOB-AUTH-02",
                decision=ReviewDecision.APPROVE,
                reviewer="OPERATOR-BOB",  # Same as attempt operator
            )
        assert "four-eyes" in str(exc_info.value).lower()

    def test_operator_role_cannot_review(self):
        """Users with explicit OPERATOR role cannot render review decisions."""
        _create_sample_job("JOB-AUTH-03", status=JobStatus.IN_PROGRESS, assigned_inspector="INSP-A")
        REVIEW_SERVICE.submit_for_review("JOB-AUTH-03")

        with pytest.raises(UnauthorizedReviewerError) as exc_info:
            REVIEW_SERVICE.execute_review(
                job_id="JOB-AUTH-03",
                decision=ReviewDecision.APPROVE,
                reviewer="THIRD-PARTY-USER",
                role=ReviewRole.OPERATOR,
            )
        assert "not authorized" in str(exc_info.value).lower()


# =============================================================================
# 4. Multi-Cycle Review History Tests
# =============================================================================

class TestReviewHistory:
    __test__ = True

    def test_multiple_review_cycles_preserved_chronologically(self):
        """
        Validates complete lifecycle traceability:
        Cycle 1: Submit -> Return for correction -> IN_PROGRESS
        Cycle 2: Submit -> Reject -> IN_PROGRESS (rework)
        Cycle 3: Submit -> Approve -> APPROVED
        All 3 reviews must be preserved in review history.
        """
        jid = "JOB-MULTI-REV"
        _create_sample_job(jid, status=JobStatus.IN_PROGRESS, assigned_inspector="INSP-A")

        # Cycle 1: Return for correction
        rev1, _ = REVIEW_SERVICE.submit_for_review(jid, reviewer="SUPERVISOR-1", comments="Cycle 1 submission")
        REVIEW_SERVICE.execute_review(
            job_id=jid,
            decision=ReviewDecision.RETURN_FOR_CORRECTION,
            comments="Please re-run zero stability test",
            reviewer="SUPERVISOR-1",
        )

        # Cycle 2: Resubmit and Reject
        rev2, _ = REVIEW_SERVICE.submit_for_review(jid, reviewer="SUPERVISOR-2", comments="Cycle 2 submission")
        REVIEW_SERVICE.execute_review(
            job_id=jid,
            decision=ReviewDecision.REJECT,
            comments="Zero drift still out of limits",
            reviewer="SUPERVISOR-2",
        )
        # Move back to IN_PROGRESS for final rework
        WORKFLOW_SERVICE.transition_job(jid, JobStatus.IN_PROGRESS, actor="INSP-A", reason="Recalibrated loadcell")

        # Cycle 3: Resubmit and Approve
        rev3, final_job = REVIEW_SERVICE.submit_for_review(jid, reviewer="CONTROLLER-CHIEF", comments="Cycle 3 submission")
        REVIEW_SERVICE.execute_review(
            job_id=jid,
            decision=ReviewDecision.APPROVE,
            comments="All parameters confirmed compliant with Legal Metrology 2011 Rules.",
            reviewer="CONTROLLER-CHIEF",
        )

        assert final_job.status == JobStatus.APPROVED

        history = REVIEW_SERVICE.get_review_history(jid)
        assert len(history) == 3
        assert history[0].id == rev1.id
        assert history[0].decision == ReviewDecision.RETURN_FOR_CORRECTION
        assert history[1].id == rev2.id
        assert history[1].decision == ReviewDecision.REJECT
        assert history[2].id == rev3.id
        assert history[2].decision == ReviewDecision.APPROVE


# =============================================================================
# 5. REST API Endpoints Tests
# =============================================================================

class TestReviewAPIEndpoints:
    __test__ = True

    def test_api_submit_review_success(self, client):
        """POST /jobs/{id}/submit-review transitions job to REVIEW."""
        _create_sample_job("JOB-API-REV-01", status=JobStatus.IN_PROGRESS, with_execution_data=True)
        response = client.post(
            "/jobs/JOB-API-REV-01/submit-review",
            json={
                "reviewer": "CONTROLLER-01",
                "comments": "Testing successfully completed, ready for approval.",
                "submitted_by": "INSP-01",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["current_state"] == "REVIEW"
        assert data["data"]["review"]["status"] == "PENDING"

    def test_api_execute_review_approve(self, client):
        """POST /jobs/{id}/review records decision and updates state."""
        _create_sample_job("JOB-API-REV-02", status=JobStatus.IN_PROGRESS, assigned_inspector="INSP-A")
        client.post("/jobs/JOB-API-REV-02/submit-review", json={"reviewer": "CONTROLLER-01"})

        response = client.post(
            "/jobs/JOB-API-REV-02/review",
            json={
                "decision": "APPROVE",
                "reviewer": "CONTROLLER-01",
                "role": "CONTROLLER",
                "comments": "Approved for official stamping and report generation.",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["current_state"] == "APPROVED"
        assert data["data"]["review"]["decision"] == "APPROVE"

    def test_api_get_current_and_history(self, client):
        """GET /jobs/{id}/review and GET /jobs/{id}/reviews return correct review metadata."""
        _create_sample_job("JOB-API-REV-03", status=JobStatus.IN_PROGRESS, assigned_inspector="INSP-A")
        client.post("/jobs/JOB-API-REV-03/submit-review", json={"reviewer": "CONTROLLER-01"})

        # Get current
        r_curr = client.get("/jobs/JOB-API-REV-03/review")
        assert r_curr.status_code == 200
        assert r_curr.json()["data"]["status"] == "PENDING"

        # Get history
        r_hist = client.get("/jobs/JOB-API-REV-03/reviews")
        assert r_hist.status_code == 200
        assert r_hist.json()["count"] == 1
