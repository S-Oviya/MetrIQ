"""
MetrIQ P5 Test Attempt & Retest Handling Unit Tests
===================================================
Person 5: Workflow + Evidence Engineer

Comprehensive test suite validating:
1. Sequential attempt numbering (1, 2, 3...), non-destructive preservation
2. Attempt creation in IN_PROGRESS state with operator and start timestamp (no auto pass/fail)
3. Completion with valid Verdict (PASS / FAIL / INCONCLUSIVE), completed_at, immutability against re-completion
4. Retest workflow: FAIL attempt preserved -> job transitions to RETEST_REQUIRED -> returns to IN_PROGRESS -> Attempt 2 created
5. PASS attempt preserved alongside previous failed attempts
6. Validation gates (non-existent test, non-existent job, invalid result, invalid job state, invalid retest)
7. Concurrency / integrity: thread-safe attempt number generation and uniqueness
8. REST API endpoints (/jobs/{id}/tests/{id}/attempts, /complete, /retest, /attempts aliases)
"""

import concurrent.futures
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app.api.router import api_router
from app.attempts.models import AttemptStatus, RetestRequest, TestAttempt, Verdict
from app.attempts.repository import (
    ATTEMPT_REPOSITORY,
    AttemptRepository,
    DuplicateAttemptNumberError,
)
from app.attempts.service import (
    ATTEMPT_SERVICE,
    AttemptAlreadyCompletedError,
    AttemptJobStateError,
    AttemptNotFoundError,
    AttemptService,
    AttemptValidationError,
    TestNotFoundError,
)
from app.jobs.models import JobPriority, JobStatus, JobType, TestJob
from app.jobs.repository import TEST_JOB_REPOSITORY
from app.workflow.service import WORKFLOW_SERVICE, JobNotFoundError


@pytest.fixture(autouse=True)
def clean_repositories():
    """Ensures test isolation by resetting repositories before each test."""
    ATTEMPT_REPOSITORY.clear()
    TEST_JOB_REPOSITORY.clear()
    yield
    ATTEMPT_REPOSITORY.clear()
    TEST_JOB_REPOSITORY.clear()


@pytest.fixture
def client():
    """FastAPI test client with the integrated API router."""
    from fastapi import FastAPI
    app = FastAPI(title="Test MetrIQ P5 Attempts")
    app.include_router(api_router)
    return TestClient(app)


def _create_sample_job(
    job_id: str = "JOB-ATT-001",
    status: JobStatus = JobStatus.IN_PROGRESS,
    applicable_tests: list = None,
) -> TestJob:
    """Helper to persist a test job with specified status and applicable tests."""
    tests = applicable_tests if applicable_tests is not None else ["A.4.4", "A.4.7", "WEIGHING_PERFORMANCE"]
    job = TestJob(
        job_id=job_id,
        instrument_id="INST-NAWI-001",
        job_type=JobType.RE_VERIFICATION,
        status=status,
        priority=JobPriority.NORMAL,
        applicable_tests=tests,
        test_execution_data={"status": "INITIAL_RUN", "readings_count": 5},
    )
    TEST_JOB_REPOSITORY.save(job)
    return job


# =============================================================================
# 1. Attempt Creation & Sequential Numbering Tests
# =============================================================================

class TestP5AttemptCreationAndNumbering:
    """Tests attempt creation, numbering sequence, and non-destructive preservation."""

    def test_01_first_attempt_gets_number_1(self):
        """First attempt for a test starts at attempt_number 1."""
        job = _create_sample_job("JOB-01", status=JobStatus.IN_PROGRESS)

        att1 = ATTEMPT_SERVICE.start_attempt(
            job_id="JOB-01",
            test_id="A.4.4",
            operator="Inspector Sharma",
            entered_values={"test_load_kg": 10.0},
        )

        assert att1.id.startswith("ATT-")
        assert att1.job_id == "JOB-01"
        assert att1.test_id == "A.4.4"
        assert att1.attempt_number == 1
        assert att1.status == AttemptStatus.IN_PROGRESS
        assert att1.result is None  # Not automatically marked at creation!
        assert att1.operator == "Inspector Sharma"
        assert att1.started_at is not None
        assert att1.completed_at is None
        assert att1.entered_values["test_load_kg"] == 10.0

        # Verify synchronized to job.test_attempts
        job_entity = TEST_JOB_REPOSITORY.get("JOB-01")
        assert len(job_entity.test_attempts) == 1
        assert job_entity.test_attempts[0]["id"] == att1.id
        assert job_entity.test_attempts[0]["attempt_number"] == 1

    def test_02_second_attempt_gets_number_2(self):
        """Subsequent attempt gets number 2 and preserves attempt 1."""
        job = _create_sample_job("JOB-02", status=JobStatus.IN_PROGRESS)

        att1 = ATTEMPT_SERVICE.start_attempt("JOB-02", "A.4.4", operator="Op 1")
        ATTEMPT_SERVICE.complete_attempt(att1.id, result=Verdict.FAIL, comments="Failed on eccentric load")

        att2 = ATTEMPT_SERVICE.start_attempt("JOB-02", "A.4.4", operator="Op 2")

        assert att1.attempt_number == 1
        assert att2.attempt_number == 2
        assert att1.id != att2.id

        # Verify both attempts preserved
        attempts = ATTEMPT_SERVICE.get_attempts_for_test("JOB-02", "A.4.4")
        assert len(attempts) == 2
        assert attempts[0].attempt_number == 1
        assert attempts[0].result == Verdict.FAIL
        assert attempts[1].attempt_number == 2
        assert attempts[1].result is None

        # Verify job entity reflects both
        job_entity = TEST_JOB_REPOSITORY.get("JOB-02")
        assert len(job_entity.test_attempts) == 2

    def test_03_independent_attempt_numbering_per_test(self):
        """Attempt numbering is distinct per test within the same job."""
        job = _create_sample_job("JOB-03", status=JobStatus.IN_PROGRESS)

        t1_a1 = ATTEMPT_SERVICE.start_attempt("JOB-03", "A.4.4", operator="Op")
        t2_a1 = ATTEMPT_SERVICE.start_attempt("JOB-03", "A.4.7", operator="Op")

        assert t1_a1.attempt_number == 1
        assert t2_a1.attempt_number == 1

        t1_a2 = ATTEMPT_SERVICE.start_attempt("JOB-03", "A.4.4", operator="Op")
        assert t1_a2.attempt_number == 2


# =============================================================================
# 2. Attempt Completion Tests
# =============================================================================

class TestP5AttemptCompletion:
    """Tests completing attempts, storing results, and preventing duplicate completions."""

    def test_10_complete_attempt_with_pass(self):
        """Completes an attempt with PASS verdict and stores metadata."""
        _create_sample_job("JOB-COMP-PASS", status=JobStatus.IN_PROGRESS)
        att = ATTEMPT_SERVICE.start_attempt("JOB-COMP-PASS", "A.4.4", operator="Inspector Roy")

        res_data = {"max_error": 0.2, "mpe": 0.5, "verdict": "PASS"}
        completed = ATTEMPT_SERVICE.complete_attempt(
            attempt_id=att.id,
            result="PASS",
            comments="Within OIML Class III limits",
            result_data=res_data,
            test_run_id="RUN-1001",
        )

        assert completed.status == AttemptStatus.COMPLETED
        assert completed.result == Verdict.PASS
        assert completed.is_pass is True
        assert completed.is_fail is False
        assert completed.is_completed is True
        assert completed.completed_at is not None
        assert completed.comments == "Within OIML Class III limits"
        assert completed.test_run_id == "RUN-1001"
        assert completed.result_data["verdict"] == "PASS"

    def test_11_complete_attempt_with_fail_and_inconclusive(self):
        """Supports FAIL and INCONCLUSIVE outcomes."""
        _create_sample_job("JOB-COMP-DIFF", status=JobStatus.IN_PROGRESS)

        att_fail = ATTEMPT_SERVICE.start_attempt("JOB-COMP-DIFF", "A.4.4", operator="Inspector")
        c_fail = ATTEMPT_SERVICE.complete_attempt(att_fail.id, result=Verdict.FAIL, comments="Exceeded MPE")
        assert c_fail.result == Verdict.FAIL
        assert c_fail.is_fail is True

        att_inc = ATTEMPT_SERVICE.start_attempt("JOB-COMP-DIFF", "A.4.7", operator="Inspector")
        c_inc = ATTEMPT_SERVICE.complete_attempt(att_inc.id, result=Verdict.INCONCLUSIVE, comments="Unstable bench")
        assert c_inc.result == Verdict.INCONCLUSIVE

    def test_12_cannot_complete_already_completed_attempt(self):
        """Fails when attempting to complete an already completed attempt."""
        _create_sample_job("JOB-ALREADY", status=JobStatus.IN_PROGRESS)
        att = ATTEMPT_SERVICE.start_attempt("JOB-ALREADY", "A.4.4", operator="Inspector")
        ATTEMPT_SERVICE.complete_attempt(att.id, result="PASS")

        with pytest.raises(AttemptAlreadyCompletedError) as exc:
            ATTEMPT_SERVICE.complete_attempt(att.id, result="FAIL")
        assert "already completed" in str(exc.value).lower()

    def test_13_reject_invalid_verdict_result(self):
        """Rejects attempt completion with unsupported result strings."""
        _create_sample_job("JOB-BAD-RES", status=JobStatus.IN_PROGRESS)
        att = ATTEMPT_SERVICE.start_attempt("JOB-BAD-RES", "A.4.4", operator="Inspector")

        with pytest.raises(AttemptValidationError) as exc:
            ATTEMPT_SERVICE.complete_attempt(att.id, result="MAYBE_PASSED")
        assert "invalid attempt result" in str(exc.value).lower()


# =============================================================================
# 3. Retest Handling & Workflow Integration Tests
# =============================================================================

class TestP5RetestWorkflow:
    """Tests the retest cycle: FAIL -> RETEST_REQUIRED -> IN_PROGRESS -> Attempt 2."""

    def test_20_retest_workflow_end_to_end(self):
        """
        Executes full statutory retest lifecycle:
        1. Job in IN_PROGRESS
        2. Attempt 1 executed -> completed with FAIL
        3. Retest requested -> job moves to RETEST_REQUIRED via state machine
        4. Job transitioned back to IN_PROGRESS
        5. Attempt 2 executed -> completed with PASS
        6. Previous failed attempt preserved completely.
        """
        job = _create_sample_job("JOB-RETEST-E2E", status=JobStatus.IN_PROGRESS)

        # 1. Attempt 1 fails
        att1 = ATTEMPT_SERVICE.start_attempt("JOB-RETEST-E2E", "A.4.4", operator="Insp. Rao")
        ATTEMPT_SERVICE.complete_attempt(
            att1.id,
            result="FAIL",
            comments="Zero return drift exceeded 0.5 e",
        )

        # 2. Request retest
        retest_req = ATTEMPT_SERVICE.request_retest(
            job_id="JOB-RETEST-E2E",
            test_id="A.4.4",
            attempt_id=att1.id,
            reason="Zero setting sensor adjusted; repeat statutory test",
            requested_by="Insp. Rao",
        )

        assert retest_req.retest_id.startswith("RET-")
        assert retest_req.job_id == "JOB-RETEST-E2E"
        assert retest_req.attempt_number == 1
        assert retest_req.reason == "Zero setting sensor adjusted; repeat statutory test"

        # Verify Job state moved to RETEST_REQUIRED via state machine
        job_after_retest = TEST_JOB_REPOSITORY.get("JOB-RETEST-E2E")
        assert job_after_retest.status == JobStatus.RETEST_REQUIRED
        # Verify state transition record in audit trail
        last_trans = job_after_retest.state_history[-1]
        assert last_trans.from_status == "IN_PROGRESS"
        assert last_trans.to_status == "RETEST_REQUIRED"
        assert last_trans.reason == "Zero setting sensor adjusted; repeat statutory test"

        # 3. Attempting to start attempt while in RETEST_REQUIRED must be rejected
        with pytest.raises(AttemptJobStateError):
            ATTEMPT_SERVICE.start_attempt("JOB-RETEST-E2E", "A.4.4", operator="Insp. Rao")

        # 4. Return job to IN_PROGRESS via existing state machine
        WORKFLOW_SERVICE.transition_job(
            job_id="JOB-RETEST-E2E",
            target_state=JobStatus.IN_PROGRESS,
            actor="Insp. Rao",
            reason="Commencing Retest Attempt 2",
        )
        assert TEST_JOB_REPOSITORY.get("JOB-RETEST-E2E").status == JobStatus.IN_PROGRESS

        # 5. Start Attempt 2
        att2 = ATTEMPT_SERVICE.start_attempt("JOB-RETEST-E2E", "A.4.4", operator="Insp. Rao")
        assert att2.attempt_number == 2

        # 6. Complete Attempt 2 with PASS
        c2 = ATTEMPT_SERVICE.complete_attempt(att2.id, result="PASS", comments="Passed on retest")
        assert c2.result == Verdict.PASS

        # 7. Verify both attempts preserved on test and job
        all_attempts = ATTEMPT_SERVICE.get_attempts_for_test("JOB-RETEST-E2E", "A.4.4")
        assert len(all_attempts) == 2
        assert all_attempts[0].attempt_number == 1
        assert all_attempts[0].result == Verdict.FAIL
        assert all_attempts[1].attempt_number == 2
        assert all_attempts[1].result == Verdict.PASS

        # Job helper method
        job_final = TEST_JOB_REPOSITORY.get("JOB-RETEST-E2E")
        assert len(job_final.get_attempts_for_test("A.4.4")) == 2
        assert job_final.get_latest_attempt_for_test("A.4.4")["result"] == "PASS"

    def test_21_cannot_request_retest_for_passing_attempt(self):
        """Retest request is strictly rejected if attempt did not FAIL."""
        _create_sample_job("JOB-PASS-NO-RET", status=JobStatus.IN_PROGRESS)
        att = ATTEMPT_SERVICE.start_attempt("JOB-PASS-NO-RET", "A.4.4", operator="Op")
        ATTEMPT_SERVICE.complete_attempt(att.id, result="PASS")

        with pytest.raises(AttemptValidationError) as exc:
            ATTEMPT_SERVICE.request_retest("JOB-PASS-NO-RET", "A.4.4", att.id, "Try again", "Op")
        assert "fail" in str(exc.value).lower()

    def test_22_cannot_request_retest_for_incomplete_attempt(self):
        """Retest request is rejected if attempt is still in progress."""
        _create_sample_job("JOB-INC-NO-RET", status=JobStatus.IN_PROGRESS)
        att = ATTEMPT_SERVICE.start_attempt("JOB-INC-NO-RET", "A.4.4", operator="Op")

        with pytest.raises(AttemptValidationError) as exc:
            ATTEMPT_SERVICE.request_retest("JOB-INC-NO-RET", "A.4.4", att.id, "Try again", "Op")
        assert "in progress" in str(exc.value).lower()


# =============================================================================
# 4. Validation & Edge Cases Tests
# =============================================================================

class TestP5AttemptValidation:
    """Tests validation of job state, non-existent entities, and parameters."""

    def test_30_reject_start_attempt_on_non_existent_job(self):
        """Rejects starting attempt if job does not exist."""
        with pytest.raises(JobNotFoundError):
            ATTEMPT_SERVICE.start_attempt("JOB-GHOST", "A.4.4", operator="Op")

    def test_31_reject_start_attempt_in_invalid_job_states(self):
        """Rejects starting attempt in DRAFT, READY, REVIEW, APPROVED, REPORT_GENERATED."""
        invalid_states = [
            JobStatus.DRAFT,
            JobStatus.READY,
            JobStatus.REVIEW,
            JobStatus.APPROVED,
            JobStatus.REPORT_GENERATED,
        ]
        for st in invalid_states:
            job_id = f"JOB-STATE-{st.value}"
            _create_sample_job(job_id, status=st)
            with pytest.raises(AttemptJobStateError):
                ATTEMPT_SERVICE.start_attempt(job_id, "A.4.4", operator="Op")

    def test_32_reject_unapplicable_test_id(self):
        """Rejects starting attempt for a test ID not in job's applicable tests."""
        job = _create_sample_job("JOB-APP-TESTS", status=JobStatus.IN_PROGRESS, applicable_tests=["A.4.4"])

        with pytest.raises(TestNotFoundError) as exc:
            ATTEMPT_SERVICE.start_attempt("JOB-APP-TESTS", "UNKNOWN_TEST_XYZ", operator="Op")
        assert "not an applicable test" in str(exc.value).lower()

    def test_33_reject_empty_operator(self):
        """Rejects starting attempt without operator name."""
        _create_sample_job("JOB-NO-OP", status=JobStatus.IN_PROGRESS)
        with pytest.raises(AttemptValidationError) as exc:
            ATTEMPT_SERVICE.start_attempt("JOB-NO-OP", "A.4.4", operator="   ")
        assert "operator" in str(exc.value).lower()


# =============================================================================
# 5. Concurrency & Uniqueness Integrity Tests
# =============================================================================

class TestP5AttemptConcurrency:
    """Tests concurrency safety and duplicate prevention."""

    def test_40_attempt_numbers_remain_unique_under_parallel_requests(self):
        """
        Tests that concurrent attempt creation for the same test on a job
        allocates unique sequential attempt numbers without collision.
        """
        _create_sample_job("JOB-CONCUR", status=JobStatus.IN_PROGRESS)

        created_attempts = []

        def worker(idx):
            return ATTEMPT_SERVICE.start_attempt(
                job_id="JOB-CONCUR",
                test_id="A.4.4",
                operator=f"Worker {idx}",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, i) for i in range(10)]
            for f in concurrent.futures.as_completed(futures):
                created_attempts.append(f.result())

        assert len(created_attempts) == 10
        numbers = [a.attempt_number for a in created_attempts]
        assert len(set(numbers)) == 10  # All 10 attempt numbers are strictly unique!
        assert sorted(numbers) == list(range(1, 11))


# =============================================================================
# 6. REST API Endpoint Tests
# =============================================================================

class TestP5AttemptAPI:
    """Tests REST endpoints for attempt management and retests."""

    def test_50_api_start_and_complete_attempt(self, client):
        """POST /jobs/{jobId}/tests/{testId}/attempts and /complete endpoints."""
        _create_sample_job("JOB-API-ATT", status=JobStatus.IN_PROGRESS)

        # 1. Start attempt
        start_res = client.post(
            "/jobs/JOB-API-ATT/tests/A.4.4/attempts",
            json={"operator": "Insp. Varma", "notes": "Baseline run"},
        )
        assert start_res.status_code == 201
        data = start_res.json()["data"]
        assert data["attempt_number"] == 1
        assert data["status"] == "IN_PROGRESS"
        attempt_id = data["id"]

        # 2. Complete attempt
        comp_res = client.post(
            f"/jobs/JOB-API-ATT/tests/A.4.4/attempts/{attempt_id}/complete",
            json={"result": "PASS", "comments": "Passes all verification criteria"},
        )
        assert comp_res.status_code == 200
        comp_data = comp_res.json()["data"]
        assert comp_data["result"] == "PASS"
        assert comp_data["status"] == "COMPLETED"

    def test_51_api_retest_and_get_endpoints(self, client):
        """End-to-end API test for retest request and attempt retrieval."""
        _create_sample_job("JOB-API-RET", status=JobStatus.IN_PROGRESS)

        # Start attempt 1
        post_res = client.post(
            "/jobs/JOB-API-RET/tests/A.4.4/attempts",
            json={"operator": "Insp. Varma"},
        )
        att_id = post_res.json()["data"]["id"]

        # Complete with FAIL
        client.post(
            f"/attempts/{att_id}/complete",
            json={"result": "FAIL", "comments": "Failed repeatability"},
        )

        # Request retest via API
        ret_res = client.post(
            f"/jobs/JOB-API-RET/tests/A.4.4/attempts/{att_id}/retest",
            json={"reason": "Recalibrated load cell", "requested_by": "Insp. Varma"},
        )
        assert ret_res.status_code == 200
        assert ret_res.json()["success"] is True

        # Check job moved to RETEST_REQUIRED
        job = TEST_JOB_REPOSITORY.get("JOB-API-RET")
        assert job.status == JobStatus.RETEST_REQUIRED

        # GET attempt by ID
        get_res = client.get(f"/attempts/{att_id}")
        assert get_res.status_code == 200
        assert get_res.json()["data"]["id"] == att_id

        # GET all attempts for test
        list_res = client.get("/jobs/JOB-API-RET/tests/A.4.4/attempts")
        assert list_res.status_code == 200
        assert list_res.json()["count"] == 1
        assert list_res.json()["data"][0]["attempt_number"] == 1
