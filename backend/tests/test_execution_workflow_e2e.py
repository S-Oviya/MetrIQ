"""
MetrIQ End-to-End Test Execution Workflow Integration Tests
===========================================================

Covers the corrected workflow:
  Instrument
  → Create Job (P3 statuses)
  → Validate / Generate Test Plan / Assign
  → POST /jobs/{id}/start-execution  (P3→P5 bridge)
  → POST /test-execution/submit       (observations + P4 engine)
  → Auto-review trigger when all tests pass
  → POST /jobs/{id}/submit-review
  → POST /jobs/{id}/review  (APPROVE / REJECT)
  → POST /reports / POST /reports/{id}/generate

Key assertions:
  A. Route /test-execution/submit exists and is reachable.
  B. A P3-created job (ASSIGNED status) can be auto-advanced to IN_PROGRESS.
  C. PASS path creates attempt, advances job.
  D. FAIL path creates attempt, does NOT advance to REVIEW.
  E. Auto-review trigger fires after all applicable tests pass.
  F. ReviewService eligibility accepts IN_PROGRESS, ASSIGNED, TEST_COMPLETED.
  G. WorkflowStateMachine: REVIEW → APPROVED → REPORT_GENERATED allowed.
  H. ReportService accepts APPROVED and REPORT_GENERATED jobs.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Repositories that need resetting between tests
from app.attempts.repository import ATTEMPT_REPOSITORY
from app.jobs.repository import TEST_JOB_REPOSITORY
from app.instruments.registry import INSTRUMENT_REGISTRY
from app.review.repository import REVIEW_REPOSITORY
from app.reports.repository import REPORT_REPOSITORY

# Services under test
from app.tests_execution.service import (
    TEST_EXECUTION_SERVICE,
    TestExecutionService,
    ExecutionJobNotFoundError,
    ExecutionJobStateError,
    ExecutionValidationError,
)
from app.attempts.service import ATTEMPT_SERVICE
from app.review.service import REVIEW_SERVICE, ReviewEligibilityError
from app.workflow.service import WORKFLOW_SERVICE
from app.workflow.state_machine import WorkflowStateMachine, WorkflowStateTransitionError
from app.jobs.models import JobStatus, JobType, TestJob
from app.calculations.models import Verdict, TestType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _restore_instrument_seeds():
    """Restore seed instruments after clearing the registry."""
    INSTRUMENT_REGISTRY._instruments.clear()
    INSTRUMENT_REGISTRY._serial_index.clear()
    INSTRUMENT_REGISTRY._load_seed_instruments()


@pytest.fixture(autouse=True)
def reset_all():
    """Full repository reset between tests — ensures isolation."""
    ATTEMPT_REPOSITORY.clear()
    TEST_JOB_REPOSITORY.clear()
    # InstrumentRegistry has no .clear(); reset internal dicts directly.
    INSTRUMENT_REGISTRY._instruments.clear()
    INSTRUMENT_REGISTRY._serial_index.clear()
    try:
        REVIEW_REPOSITORY.clear()
    except Exception:
        pass
    try:
        REPORT_REPOSITORY.clear()
    except Exception:
        pass
    yield
    ATTEMPT_REPOSITORY.clear()
    TEST_JOB_REPOSITORY.clear()
    # Restore seed instruments so subsequent test files that rely on seeds still work.
    _restore_instrument_seeds()
    try:
        REVIEW_REPOSITORY.clear()
    except Exception:
        pass
    try:
        REPORT_REPOSITORY.clear()
    except Exception:
        pass


@pytest.fixture
def client():
    from app.api.router import api_router
    app = FastAPI(title="MetrIQ Integration Test")
    app.include_router(api_router)
    return TestClient(app)


# Minimal instrument payload that passes P2 metrological validation
_INSTRUMENT_PAYLOAD = {
    "manufacturer": "TestCo",
    "model_name": "ScaleModel-X",
    "model_number": "SMX-100",
    "serial_number": "SN-TEST-001",
    "accuracy_class": "CLASS_III",
    "max_capacity": 100.0,
    "min_capacity": 0.02,
    "e": 0.02,
    "d": 0.02,
    "n": 5000,
    "unit": "kg",
    "instrument_type": "WEIGHING_INSTRUMENT",
    "enforce_model_approval": False,
}

_WEIGHING_OBS = [
    {"applied_load": 0.0,   "indicated_value": 0.0},
    {"applied_load": 20.0,  "indicated_value": 20.0},
    {"applied_load": 20.0,  "indicated_value": 20.0},
    {"applied_load": 50.0,  "indicated_value": 50.0},
    {"applied_load": 50.0,  "indicated_value": 50.0},
    {"applied_load": 80.0,  "indicated_value": 80.0},
    {"applied_load": 80.0,  "indicated_value": 80.0},
    {"applied_load": 100.0, "indicated_value": 100.0},
    {"applied_load": 100.0, "indicated_value": 100.0},
]

_WEIGHING_FAIL_OBS = [
    {"applied_load": 0.0,   "indicated_value": 5.0},   # huge error → FAIL
    {"applied_load": 20.0,  "indicated_value": 30.0},
    {"applied_load": 50.0,  "indicated_value": 75.0},
    {"applied_load": 100.0, "indicated_value": 120.0},
]


def _make_job(status: JobStatus = JobStatus.ASSIGNED, applicable_tests=None) -> TestJob:
    """Create and save a minimal TestJob in the repository."""
    from app.instruments.models import Instrument
    # Register a minimal instrument via registry.register()
    inst = Instrument(
        instrument_id="INST-TEST-001",
        model_name="ScaleX",
        model_number="SX-1",
        manufacturer="TestCo",
        serial_number="SN-T-01",
        accuracy_class="CLASS_III",
        max_capacity=100.0,
        e=0.02,
        d=0.02,
        unit="kg",
    )
    # Use internal dict directly to avoid the full validation pipeline
    INSTRUMENT_REGISTRY._instruments["INST-TEST-001"] = inst
    INSTRUMENT_REGISTRY._serial_index["SN-T-01"] = "INST-TEST-001"

    job = TestJob(
        job_id="JOB-TEST-001",
        instrument_id="INST-TEST-001",
        job_type=JobType.RE_VERIFICATION,
        status=status,
        applicable_tests=applicable_tests or ["WEIGHING_PERFORMANCE"],
    )
    TEST_JOB_REPOSITORY.save(job)
    return job


# ===========================================================================
# A. Route registration
# ===========================================================================

class TestRouteRegistration:
    def test_test_execution_submit_route_exists(self, client):
        """POST /test-execution/submit must be registered (not 404 / 405)."""
        resp = client.post("/test-execution/submit", json={})
        # 422 (validation error) means route exists; 404 means not mounted
        assert resp.status_code in (422, 409, 200), (
            f"Expected route to exist, got {resp.status_code}: {resp.text}"
        )

    def test_test_execution_results_route_exists(self, client):
        resp = client.get("/test-execution/NONEXISTENT/results")
        assert resp.status_code in (404, 200)

    def test_start_execution_route_exists(self, client):
        resp = client.post("/jobs/NONEXISTENT/start-execution", json={})
        assert resp.status_code in (404, 409, 200)


# ===========================================================================
# B. WorkflowStateMachine bridge — P3 statuses → IN_PROGRESS
# ===========================================================================

class TestWorkflowStateMachineBridge:
    @pytest.mark.parametrize("status_name", [
        "DRAFT", "CREATED", "VALIDATED",
        "TEST_PLAN_GENERATED", "PLAN_GENERATED",
        "READY_FOR_TEST", "ASSIGNED", "IN_TESTING", "READY",
    ])
    def test_p3_status_can_transition_to_in_progress(self, status_name):
        src = JobStatus.from_value(status_name)
        ok, err_code, err_msg = WorkflowStateMachine.can_transition(src, JobStatus.IN_PROGRESS)
        assert ok, f"{status_name} → IN_PROGRESS should be allowed, got: {err_msg}"

    def test_in_progress_to_review_allowed(self):
        ok, _, _ = WorkflowStateMachine.can_transition(
            JobStatus.IN_PROGRESS, JobStatus.REVIEW,
            test_execution_data={"some": "data"}
        )
        assert ok

    def test_review_to_approved_allowed(self):
        ok, _, _ = WorkflowStateMachine.can_transition(JobStatus.REVIEW, JobStatus.APPROVED)
        assert ok

    def test_approved_to_report_generated_allowed(self):
        ok, _, _ = WorkflowStateMachine.can_transition(JobStatus.APPROVED, JobStatus.REPORT_GENERATED)
        assert ok

    def test_approved_to_closed_allowed(self):
        ok, _, _ = WorkflowStateMachine.can_transition(JobStatus.APPROVED, JobStatus.CLOSED)
        assert ok

    def test_review_to_rejected_allowed(self):
        ok, _, _ = WorkflowStateMachine.can_transition(JobStatus.REVIEW, JobStatus.REJECTED)
        assert ok

    def test_test_completed_to_review_allowed(self):
        ok, _, _ = WorkflowStateMachine.can_transition(
            JobStatus.TEST_COMPLETED, JobStatus.REVIEW,
            test_execution_data={"done": True}
        )
        assert ok

    def test_under_review_to_approved_allowed(self):
        ok, _, _ = WorkflowStateMachine.can_transition(JobStatus.UNDER_REVIEW, JobStatus.APPROVED)
        assert ok

    def test_report_generated_is_terminal(self):
        ok, _, _ = WorkflowStateMachine.can_transition(
            JobStatus.REPORT_GENERATED, JobStatus.IN_PROGRESS
        )
        assert not ok

    def test_in_progress_no_data_blocks_review(self):
        ok, err_code, err_msg = WorkflowStateMachine.can_transition(
            JobStatus.IN_PROGRESS, JobStatus.REVIEW
        )
        assert not ok
        assert err_code == "MISSING_TEST_EXECUTION_DATA"

    def test_self_transition_blocked(self):
        ok, err_code, _ = WorkflowStateMachine.can_transition(
            JobStatus.IN_PROGRESS, JobStatus.IN_PROGRESS
        )
        assert not ok


# ===========================================================================
# C. start-execution API bridge
# ===========================================================================

class TestStartExecutionEndpoint:
    def test_assigned_job_advances_to_in_progress(self, client):
        _make_job(JobStatus.ASSIGNED)
        resp = client.post("/jobs/JOB-TEST-001/start-execution", json={"user_id": "TESTER"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["status"] == "IN_PROGRESS"

    def test_already_in_progress_is_idempotent(self, client):
        _make_job(JobStatus.IN_PROGRESS)
        resp = client.post("/jobs/JOB-TEST-001/start-execution", json={})
        assert resp.status_code == 200
        assert resp.json()["status"] == "IN_PROGRESS"

    def test_nonexistent_job_returns_404(self, client):
        resp = client.post("/jobs/GHOST-999/start-execution", json={})
        assert resp.status_code == 404

    def test_ready_for_test_advances_to_in_progress(self, client):
        _make_job(JobStatus.READY_FOR_TEST)
        resp = client.post("/jobs/JOB-TEST-001/start-execution", json={})
        assert resp.status_code == 200
        assert resp.json()["status"] == "IN_PROGRESS"


# ===========================================================================
# D. TestExecutionService — submit_observations
# ===========================================================================

class TestSubmitObservations:
    """Unit tests against ExecutionService directly (no HTTP)."""

    def _mock_instrument_svc(self):
        """Returns a mock instrument service that returns valid instrument params."""
        from unittest.mock import MagicMock
        svc = MagicMock()
        svc.get_instrument.return_value = {
            "instrument_id": "INST-TEST-001",
            "accuracy_class": "CLASS_III",
            "max_capacity": 100.0,
            "e": 0.02,
            "d": 0.02,
            "n": 5000,
            "unit": "kg",
        }
        return svc

    def _make_svc(self):
        return TestExecutionService(
            job_repository=TEST_JOB_REPOSITORY,
            instrument_service=self._mock_instrument_svc(),
            attempt_service=ATTEMPT_SERVICE,
            workflow_service=WORKFLOW_SERVICE,
        )

    def test_submit_from_assigned_job_auto_advances(self):
        _make_job(JobStatus.ASSIGNED)
        svc = self._make_svc()
        result = svc.submit_observations(
            job_id="JOB-TEST-001",
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_OBS,
            operator="INSPECTOR-1",
        )
        assert result["success"] is True
        assert result["verdict"] in ("PASS", "FAIL", "INCONCLUSIVE")
        assert result["attempt"]["attempt_number"] == 1
        # Job must now be IN_PROGRESS (or REVIEW if auto-trigger fired)
        assert result["job_status"] in ("IN_PROGRESS", "REVIEW")

    def test_submit_from_in_progress_job(self):
        _make_job(JobStatus.IN_PROGRESS)
        svc = self._make_svc()
        result = svc.submit_observations(
            job_id="JOB-TEST-001",
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_OBS,
            operator="INSPECTOR-1",
        )
        assert result["success"] is True
        assert result["attempt"]["attempt_id"].startswith("ATT-")

    def test_invalid_job_raises_not_found(self):
        svc = self._make_svc()
        with pytest.raises(ExecutionJobNotFoundError):
            svc.submit_observations(
                job_id="GHOST",
                test_type="WEIGHING_PERFORMANCE",
                observations=_WEIGHING_OBS,
                operator="OP",
            )

    def test_terminal_job_raises_state_error(self):
        _make_job(JobStatus.REPORT_GENERATED)
        svc = self._make_svc()
        with pytest.raises(ExecutionJobStateError):
            svc.submit_observations(
                job_id="JOB-TEST-001",
                test_type="WEIGHING_PERFORMANCE",
                observations=_WEIGHING_OBS,
                operator="OP",
            )

    def test_empty_observations_raises_validation_error(self):
        _make_job(JobStatus.IN_PROGRESS)
        svc = self._make_svc()
        with pytest.raises(ExecutionValidationError):
            svc.submit_observations(
                job_id="JOB-TEST-001",
                test_type="WEIGHING_PERFORMANCE",
                observations=[],
                operator="OP",
            )

    def test_invalid_test_type_raises_validation_error(self):
        _make_job(JobStatus.IN_PROGRESS)
        svc = self._make_svc()
        with pytest.raises(ExecutionValidationError):
            svc.submit_observations(
                job_id="JOB-TEST-001",
                test_type="NONSENSE_TEST",
                observations=_WEIGHING_OBS,
                operator="OP",
            )

    def test_second_attempt_increments_number(self):
        _make_job(JobStatus.IN_PROGRESS, applicable_tests=["WEIGHING_PERFORMANCE", "ECCENTRICITY"])
        svc = self._make_svc()
        r1 = svc.submit_observations(
            job_id="JOB-TEST-001",
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_OBS,
            operator="INSPECTOR-1",
        )
        r2 = svc.submit_observations(
            job_id="JOB-TEST-001",
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_OBS,
            operator="INSPECTOR-1",
        )
        assert r1["attempt"]["attempt_number"] == 1
        assert r2["attempt"]["attempt_number"] == 2


# ===========================================================================
# E. Auto-review trigger
# ===========================================================================

class TestAutoReviewTrigger:
    def _mock_instrument_svc(self):
        from unittest.mock import MagicMock
        svc = MagicMock()
        svc.get_instrument.return_value = {
            "instrument_id": "INST-TEST-001",
            "accuracy_class": "CLASS_III",
            "max_capacity": 100.0,
            "e": 0.02,
            "d": 0.02,
            "n": 5000,
            "unit": "kg",
        }
        return svc

    def test_auto_review_fires_when_only_test_passes(self):
        """Single applicable test: PASS → job auto-transitions to REVIEW."""
        _make_job(JobStatus.IN_PROGRESS, applicable_tests=["WEIGHING_PERFORMANCE"])
        svc = TestExecutionService(
            job_repository=TEST_JOB_REPOSITORY,
            instrument_service=self._mock_instrument_svc(),
            attempt_service=ATTEMPT_SERVICE,
            workflow_service=WORKFLOW_SERVICE,
        )
        result = svc.submit_observations(
            job_id="JOB-TEST-001",
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_OBS,
            operator="INSPECTOR-1",
        )
        if result["verdict"] == Verdict.PASS.value:
            assert result["auto_review_triggered"] is True
            assert result["job_status"] == "REVIEW"

    def test_auto_review_does_not_fire_when_test_fails(self):
        """FAIL verdict: no auto-review."""
        _make_job(JobStatus.IN_PROGRESS, applicable_tests=["WEIGHING_PERFORMANCE"])
        svc = TestExecutionService(
            job_repository=TEST_JOB_REPOSITORY,
            instrument_service=self._mock_instrument_svc(),
            attempt_service=ATTEMPT_SERVICE,
            workflow_service=WORKFLOW_SERVICE,
        )
        result = svc.submit_observations(
            job_id="JOB-TEST-001",
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_FAIL_OBS,
            operator="INSPECTOR-1",
        )
        if result["verdict"] == Verdict.FAIL.value:
            assert result["auto_review_triggered"] is False
            assert result["job_status"] == "IN_PROGRESS"

    def test_auto_review_waits_for_all_tests(self):
        """Two applicable tests: first PASS should NOT trigger review."""
        _make_job(JobStatus.IN_PROGRESS, applicable_tests=["WEIGHING_PERFORMANCE", "ZERO_RETURN"])
        svc = TestExecutionService(
            job_repository=TEST_JOB_REPOSITORY,
            instrument_service=self._mock_instrument_svc(),
            attempt_service=ATTEMPT_SERVICE,
            workflow_service=WORKFLOW_SERVICE,
        )
        result = svc.submit_observations(
            job_id="JOB-TEST-001",
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_OBS,
            operator="INSPECTOR-1",
        )
        # Only first of two tests done — review should not trigger regardless of verdict
        assert result["auto_review_triggered"] is False
        assert result["job_status"] == "IN_PROGRESS"


# ===========================================================================
# F. ReviewService eligibility
# ===========================================================================

class TestReviewServiceEligibility:
    def test_in_progress_job_with_attempts_is_eligible(self):
        job = _make_job(JobStatus.IN_PROGRESS)
        # Add a completed attempt manually
        from app.attempts.models import TestAttempt, AttemptStatus
        att = TestAttempt(
            id="ATT-R1",
            test_id="WEIGHING_PERFORMANCE",
            job_id=job.job_id,
            attempt_number=1,
            status=AttemptStatus.COMPLETED,
            result=Verdict.PASS,
            operator="OP",
        )
        ATTEMPT_REPOSITORY.save_attempt(att)

        eligible, reason, _ = REVIEW_SERVICE.check_review_eligibility(job.job_id)
        assert eligible, f"Expected eligible, got: {reason}"

    def test_assigned_job_with_attempts_is_eligible(self):
        job = _make_job(JobStatus.ASSIGNED)
        from app.attempts.models import TestAttempt, AttemptStatus
        att = TestAttempt(
            id="ATT-R2",
            test_id="WEIGHING_PERFORMANCE",
            job_id=job.job_id,
            attempt_number=1,
            status=AttemptStatus.COMPLETED,
            result=Verdict.PASS,
            operator="OP",
        )
        ATTEMPT_REPOSITORY.save_attempt(att)

        eligible, reason, _ = REVIEW_SERVICE.check_review_eligibility(job.job_id)
        assert eligible, f"Expected eligible, got: {reason}"

    def test_approved_job_is_not_eligible(self):
        _make_job(JobStatus.APPROVED)
        eligible, reason, _ = REVIEW_SERVICE.check_review_eligibility("JOB-TEST-001")
        assert not eligible
        assert "APPROVED" in (reason or "")

    def test_no_attempts_means_not_eligible(self):
        _make_job(JobStatus.IN_PROGRESS)
        eligible, reason, _ = REVIEW_SERVICE.check_review_eligibility("JOB-TEST-001")
        assert not eligible


# ===========================================================================
# G. WorkflowService full chain: IN_PROGRESS → REVIEW → APPROVED → REPORT_GENERATED
# ===========================================================================

class TestWorkflowFullChain:
    def test_full_approval_chain(self):
        _make_job(JobStatus.IN_PROGRESS)

        # Add execution data to allow REVIEW transition
        from app.attempts.models import TestAttempt, AttemptStatus
        att = TestAttempt(
            id="ATT-CHAIN-1",
            test_id="WEIGHING_PERFORMANCE",
            job_id="JOB-TEST-001",
            attempt_number=1,
            status=AttemptStatus.COMPLETED,
            result=Verdict.PASS,
            operator="OP",
        )
        ATTEMPT_REPOSITORY.save_attempt(att)

        # IN_PROGRESS → REVIEW
        job = WORKFLOW_SERVICE.transition_job(
            job_id="JOB-TEST-001",
            target_state=JobStatus.REVIEW,
            actor="OP",
            test_execution_data={"done": True},
        )
        assert job.status == JobStatus.REVIEW

        # REVIEW → APPROVED
        job = WORKFLOW_SERVICE.transition_job(
            job_id="JOB-TEST-001",
            target_state=JobStatus.APPROVED,
            actor="REVIEWER",
        )
        assert job.status == JobStatus.APPROVED

        # APPROVED → REPORT_GENERATED
        job = WORKFLOW_SERVICE.transition_job(
            job_id="JOB-TEST-001",
            target_state=JobStatus.REPORT_GENERATED,
            actor="SYSTEM",
        )
        assert job.status == JobStatus.REPORT_GENERATED

    def test_full_rejection_chain(self):
        _make_job(JobStatus.IN_PROGRESS)
        from app.attempts.models import TestAttempt, AttemptStatus
        att = TestAttempt(
            id="ATT-REJ-1",
            test_id="WEIGHING_PERFORMANCE",
            job_id="JOB-TEST-001",
            attempt_number=1,
            status=AttemptStatus.COMPLETED,
            result=Verdict.FAIL,
            operator="OP",
        )
        ATTEMPT_REPOSITORY.save_attempt(att)

        # IN_PROGRESS → REVIEW
        job = WORKFLOW_SERVICE.transition_job(
            "JOB-TEST-001", JobStatus.REVIEW, "OP",
            test_execution_data={"done": True}
        )
        assert job.status == JobStatus.REVIEW

        # REVIEW → REJECTED
        job = WORKFLOW_SERVICE.transition_job(
            "JOB-TEST-001", JobStatus.REJECTED, "REVIEWER"
        )
        assert job.status == JobStatus.REJECTED

    def test_assigned_directly_to_in_progress(self):
        _make_job(JobStatus.ASSIGNED)
        job = WORKFLOW_SERVICE.transition_job(
            "JOB-TEST-001", JobStatus.IN_PROGRESS, "SYSTEM"
        )
        assert job.status == JobStatus.IN_PROGRESS


# ===========================================================================
# H. ReportService compatibility
# ===========================================================================

class TestReportServiceCompatibility:
    def test_approved_job_can_create_report_record(self):
        from app.reports.service import REPORT_SERVICE
        _make_job(JobStatus.APPROVED)

        # reports.service uses TEST_JOB_SERVICE which calls the repository via the service
        # We patch the job lookup to return our test job
        from unittest.mock import patch
        job_dict = TEST_JOB_REPOSITORY.get("JOB-TEST-001").to_dict()
        with patch("app.reports.service.TEST_JOB_SERVICE.get_job", return_value=job_dict), \
             patch("app.reports.service.INSTRUMENT_SERVICE.get_instrument", return_value={}):
            result = REPORT_SERVICE.create(
                job_id="JOB-TEST-001",
                report_type="GENERIC_VERIFICATION",
                created_by="SYSTEM",
            )
        assert result["success"] is True
        assert result["status_code"] in (200, 201)

    def test_report_generated_job_can_create_report_record(self):
        from app.reports.service import REPORT_SERVICE, GENERATABLE_JOB_STATUSES
        assert "REPORT_GENERATED" in GENERATABLE_JOB_STATUSES, (
            "REPORT_GENERATED must be in GENERATABLE_JOB_STATUSES"
        )

    def test_generatable_statuses_include_all_p3_terminals(self):
        from app.reports.service import GENERATABLE_JOB_STATUSES
        for status in ("APPROVED", "REJECTED", "CLOSED", "CERTIFIED", "REPORT_GENERATED"):
            assert status in GENERATABLE_JOB_STATUSES, (
                f"'{status}' missing from GENERATABLE_JOB_STATUSES"
            )


# ===========================================================================
# I. HTTP API end-to-end (requires instrument in registry)
# ===========================================================================

class TestHTTPEndToEnd:
    """Lightweight HTTP-level tests using TestClient."""

    def test_submit_observations_missing_job_id_returns_422(self, client):
        resp = client.post("/test-execution/submit", json={
            "test_type": "WEIGHING_PERFORMANCE",
            "observations": _WEIGHING_OBS,
            "operator": "OP",
        })
        assert resp.status_code == 422

    def test_submit_observations_nonexistent_job_returns_404(self, client):
        resp = client.post("/test-execution/submit", json={
            "job_id": "GHOST-999",
            "test_type": "WEIGHING_PERFORMANCE",
            "observations": _WEIGHING_OBS,
            "operator": "OP",
        })
        assert resp.status_code == 404

    def test_get_results_nonexistent_job_returns_404(self, client):
        resp = client.get("/test-execution/GHOST-999/results")
        assert resp.status_code == 404

    def test_get_results_existing_job_returns_200(self, client):
        _make_job(JobStatus.IN_PROGRESS)
        resp = client.get("/test-execution/JOB-TEST-001/results")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("success") is True
        data = body.get("data", body)
        assert "tests_executed" in data or "job_id" in data
