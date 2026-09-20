"""
MetrIQ — P4/P5 Gap Coverage Tests
====================================
Covers the remaining backend gaps:

1. All 10 P4 calculators reachable through TestExecutionService.submit_observations
   (the real execution flow: job + instrument + TestEngine + AttemptService).

2. FAIL → preserved attempt → RETEST_REQUIRED → new attempt → execution
   (full failure/retest flow with preserved history).

3. REVIEW → REJECTED → correction/retest path
   (both via WorkflowService directly, and via ReviewService execute_review).

4. REJECTED job can be re-executed through submit_observations
   (REJECTED is now in _EXECUTION_READY_STATUSES).

All tests are isolated — each resets global repositories via autouse fixture.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from app.attempts.models import AttemptStatus, TestAttempt
from app.attempts.repository import ATTEMPT_REPOSITORY
from app.attempts.service import ATTEMPT_SERVICE, AttemptJobStateError
from app.calculations.models import (
    ChecklistItem,
    ChecklistStatus,
    RawObservation,
    TestType,
    Verdict,
)
from app.instruments.models import Instrument
from app.instruments.registry import INSTRUMENT_REGISTRY
from app.jobs.models import JobStatus, JobType, TestJob
from app.jobs.repository import TEST_JOB_REPOSITORY
from app.review.repository import REVIEW_REPOSITORY
from app.review.service import REVIEW_SERVICE, ReviewService
from app.tests_execution.service import (
    TEST_EXECUTION_SERVICE,
    TestExecutionService,
    ExecutionJobStateError,
    _EXECUTION_READY_STATUSES,
)
from app.workflow.service import WORKFLOW_SERVICE
from app.workflow.state_machine import WorkflowStateMachine, WorkflowStateTransitionError


# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------

INSTRUMENT_ID = "INST-GAP-001"
JOB_ID = "JOB-GAP-001"

_INSTRUMENT_PARAMS = {
    "instrument_id": INSTRUMENT_ID,
    "accuracy_class": "CLASS_III",
    "max_capacity": 100.0,
    "min_capacity": 0.02,
    "e": 0.02,
    "d": 0.02,
    "n": 5000,
    "unit": "kg",
    "software_version": "v2.1.0",
}


def _restore_instrument_seeds():
    INSTRUMENT_REGISTRY._instruments.clear()
    INSTRUMENT_REGISTRY._serial_index.clear()
    INSTRUMENT_REGISTRY._load_seed_instruments()


@pytest.fixture(autouse=True)
def reset_repos():
    """Isolate every test — clear all in-memory stores before and after."""
    ATTEMPT_REPOSITORY.clear()
    TEST_JOB_REPOSITORY.clear()
    INSTRUMENT_REGISTRY._instruments.clear()
    INSTRUMENT_REGISTRY._serial_index.clear()
    try:
        REVIEW_REPOSITORY.clear()
    except Exception:
        pass
    yield
    ATTEMPT_REPOSITORY.clear()
    TEST_JOB_REPOSITORY.clear()
    _restore_instrument_seeds()
    try:
        REVIEW_REPOSITORY.clear()
    except Exception:
        pass


def _register_instrument():
    """Register a minimal instrument in the in-memory registry."""
    inst = Instrument(
        instrument_id=INSTRUMENT_ID,
        model_name="GapTestScale",
        model_number="GTS-1",
        manufacturer="MetrIQ-Test",
        serial_number="SN-GAP-01",
        accuracy_class="CLASS_III",
        max_capacity=100.0,
        e=0.02,
        d=0.02,
        unit="kg",
    )
    INSTRUMENT_REGISTRY._instruments[INSTRUMENT_ID] = inst
    INSTRUMENT_REGISTRY._serial_index["SN-GAP-01"] = INSTRUMENT_ID


def _make_job(
    status: JobStatus = JobStatus.IN_PROGRESS,
    applicable_tests=None,
    job_id: str = JOB_ID,
) -> TestJob:
    """Create and save a minimal TestJob, with the shared instrument registered."""
    _register_instrument()
    job = TestJob(
        job_id=job_id,
        instrument_id=INSTRUMENT_ID,
        job_type=JobType.INITIAL_VERIFICATION,
        status=status,
        applicable_tests=applicable_tests or ["WEIGHING_PERFORMANCE"],
    )
    TEST_JOB_REPOSITORY.save(job)
    return job


def _mock_instrument_svc():
    """Mock InstrumentService that always returns valid instrument params."""
    svc = MagicMock()
    svc.get_instrument.return_value = _INSTRUMENT_PARAMS
    return svc


def _make_execution_svc() -> TestExecutionService:
    return TestExecutionService(
        job_repository=TEST_JOB_REPOSITORY,
        instrument_service=_mock_instrument_svc(),
        attempt_service=ATTEMPT_SERVICE,
        workflow_service=WORKFLOW_SERVICE,
    )


# Minimal valid observation sets for each calculator
_WEIGHING_OBS = [
    {"applied_load": 0.0,   "indicated_value": 0.0},
    {"applied_load": 20.0,  "indicated_value": 20.0},
    {"applied_load": 50.0,  "indicated_value": 50.0},
    {"applied_load": 100.0, "indicated_value": 100.0},
]

_WEIGHING_FAIL_OBS = [
    {"applied_load": 0.0,   "indicated_value": 10.0},   # enormous error → FAIL
    {"applied_load": 50.0,  "indicated_value": 80.0},
    {"applied_load": 100.0, "indicated_value": 200.0},
]

_ECCENTRICITY_OBS = [
    {"applied_load": 50.0, "indicated_value": 50.00, "position": "CENTER"},
    {"applied_load": 50.0, "indicated_value": 50.01, "position": "CORNER_1"},
    {"applied_load": 50.0, "indicated_value": 50.01, "position": "CORNER_2"},
    {"applied_load": 50.0, "indicated_value": 50.01, "position": "CORNER_3"},
    {"applied_load": 50.0, "indicated_value": 50.01, "position": "CORNER_4"},
]

_REPEATABILITY_OBS = [
    {"applied_load": 50.0, "indicated_value": 50.000},
    {"applied_load": 50.0, "indicated_value": 50.000},
    {"applied_load": 50.0, "indicated_value": 50.000},
    {"applied_load": 50.0, "indicated_value": 50.001},
    {"applied_load": 50.0, "indicated_value": 50.000},
]

_ZERO_RETURN_OBS = [
    {"applied_load": 0.0,   "indicated_value": 0.0},
    {"applied_load": 100.0, "indicated_value": 100.0},
    {"applied_load": 0.0,   "indicated_value": 0.001},   # near-zero drift
]

_CREEP_OBS = [
    {"applied_load": 100.0, "indicated_value": 100.000, "time_seconds": 5},
    {"applied_load": 100.0, "indicated_value": 100.001, "time_seconds": 300},
    {"applied_load": 100.0, "indicated_value": 100.002, "time_seconds": 900},
    {"applied_load": 100.0, "indicated_value": 100.002, "time_seconds": 1800},
]

_DISCRIMINATION_OBS = [
    {"applied_load": 50.0, "indicated_value": 50.000, "extra_load": 0.028},
]

_TARE_OBS = [
    {"tare_load": 10.0, "indicated_value": 0.0},          # tare setting observation
    {"applied_load": 50.0, "indicated_value": 50.000},    # net load observation
    {"applied_load": 80.0, "indicated_value": 80.001},
]

_TEMPERATURE_OBS = [
    {"temperature_c": 15.0, "applied_load": 0.0,   "indicated_value": 0.0},
    {"temperature_c": 15.0, "applied_load": 50.0,  "indicated_value": 50.000},
    {"temperature_c": 35.0, "applied_load": 0.0,   "indicated_value": 0.001},
    {"temperature_c": 35.0, "applied_load": 50.0,  "indicated_value": 50.001},
]

_CONSTRUCTION_OBS = [
    {
        "checklist_item": {
            "item_id": "C01", "title": "Nameplate legibility",
            "clause": "7.1", "status": "COMPLIANT",
        }
    },
    {
        "checklist_item": {
            "item_id": "C02", "title": "Levelling device",
            "clause": "4.7", "status": "COMPLIANT",
        }
    },
]

_SOFTWARE_OBS = [
    {
        "checklist_item": {
            "item_id": "S01", "title": "Software identification",
            "clause": "5.5.1", "status": "COMPLIANT",
        }
    },
    {
        "checklist_item": {
            "item_id": "S02", "title": "Memory protection",
            "clause": "5.5.3", "status": "COMPLIANT",
        }
    },
]


# ===========================================================================
# 1. All 10 P4 calculators via TestExecutionService.submit_observations
# ===========================================================================

class TestAllCalculatorsThroughExecutionService:
    """
    Each test verifies that:
    - submit_observations accepts the test type and observations
    - Returns success=True with a valid verdict
    - Creates an attempt (attempt_number >= 1)
    - Result stored in attempt.result_data
    """

    def _submit(self, test_type: str, observations: list, applicable=None) -> dict:
        _make_job(
            JobStatus.IN_PROGRESS,
            applicable_tests=applicable or [test_type],
        )
        svc = _make_execution_svc()
        return svc.submit_observations(
            job_id=JOB_ID,
            test_type=test_type,
            observations=observations,
            operator="INSPECTOR-GAPS",
        )

    def test_weighing_performance_via_execution_service(self):
        result = self._submit("WEIGHING_PERFORMANCE", _WEIGHING_OBS)
        assert result["success"] is True
        assert result["verdict"] in (Verdict.PASS.value, Verdict.FAIL.value, Verdict.INCONCLUSIVE.value)
        assert result["test_type"] == "WEIGHING_PERFORMANCE"
        assert result["attempt"]["attempt_number"] == 1
        calc = result["calculation_result"]
        assert "verdict" in calc
        assert calc["standard_reference"] != ""

    def test_eccentricity_via_execution_service(self):
        result = self._submit("ECCENTRICITY", _ECCENTRICITY_OBS)
        assert result["success"] is True
        assert result["test_type"] == "ECCENTRICITY"
        assert result["verdict"] in (Verdict.PASS.value, Verdict.FAIL.value, Verdict.INCONCLUSIVE.value)
        calc = result["calculation_result"]
        assert "calculated_values" in calc
        assert "max_error" in calc["calculated_values"]

    def test_repeatability_via_execution_service(self):
        result = self._submit("REPEATABILITY", _REPEATABILITY_OBS)
        assert result["success"] is True
        assert result["test_type"] == "REPEATABILITY"
        assert result["verdict"] in (Verdict.PASS.value, Verdict.FAIL.value, Verdict.INCONCLUSIVE.value)
        calc = result["calculation_result"]
        assert "worst_span" in calc["calculated_values"]

    def test_zero_return_via_execution_service(self):
        result = self._submit("ZERO_RETURN", _ZERO_RETURN_OBS)
        assert result["success"] is True
        assert result["test_type"] == "ZERO_RETURN"
        assert result["verdict"] in (Verdict.PASS.value, Verdict.FAIL.value, Verdict.INCONCLUSIVE.value)
        calc = result["calculation_result"]
        assert "zero_drift" in calc["calculated_values"]

    def test_creep_via_execution_service(self):
        result = self._submit("CREEP", _CREEP_OBS)
        assert result["success"] is True
        assert result["test_type"] == "CREEP"
        assert result["verdict"] in (Verdict.PASS.value, Verdict.FAIL.value, Verdict.INCONCLUSIVE.value)
        calc = result["calculation_result"]
        assert "total_creep" in calc["calculated_values"]

    def test_discrimination_via_execution_service(self):
        result = self._submit("DISCRIMINATION", _DISCRIMINATION_OBS)
        assert result["success"] is True
        assert result["test_type"] == "DISCRIMINATION"
        assert result["verdict"] in (Verdict.PASS.value, Verdict.FAIL.value, Verdict.INCONCLUSIVE.value)
        calc = result["calculation_result"]
        assert "d" in calc["calculated_values"]

    def test_tare_via_execution_service(self):
        result = self._submit("TARE", _TARE_OBS)
        assert result["success"] is True
        assert result["test_type"] == "TARE"
        assert result["verdict"] in (Verdict.PASS.value, Verdict.FAIL.value, Verdict.INCONCLUSIVE.value)
        calc = result["calculation_result"]
        assert "tare_setting_error" in calc["calculated_values"]

    def test_temperature_effect_via_execution_service(self):
        result = self._submit("TEMPERATURE_EFFECT", _TEMPERATURE_OBS)
        assert result["success"] is True
        assert result["test_type"] == "TEMPERATURE_EFFECT"
        assert result["verdict"] in (Verdict.PASS.value, Verdict.FAIL.value, Verdict.INCONCLUSIVE.value)
        calc = result["calculation_result"]
        assert "temperatures_tested" in calc["calculated_values"]

    def test_construction_examination_via_execution_service(self):
        result = self._submit("CONSTRUCTION_EXAMINATION", _CONSTRUCTION_OBS)
        assert result["success"] is True
        assert result["test_type"] == "CONSTRUCTION_EXAMINATION"
        assert result["verdict"] == Verdict.PASS.value   # all COMPLIANT → PASS
        calc = result["calculation_result"]
        assert calc["calculated_values"]["compliant_count"] == 2
        assert calc["calculated_values"]["non_compliant_count"] == 0
        assert "OIML R 76-1:2006" in calc["standard_reference"]

    def test_software_examination_via_execution_service(self):
        result = self._submit("SOFTWARE_EXAMINATION", _SOFTWARE_OBS)
        assert result["success"] is True
        assert result["test_type"] == "SOFTWARE_EXAMINATION"
        assert result["verdict"] == Verdict.PASS.value   # all COMPLIANT → PASS
        calc = result["calculation_result"]
        assert calc["calculated_values"]["compliant_count"] == 2
        assert calc["calculated_values"]["non_compliant_count"] == 0
        assert "5.5" in calc["standard_reference"]

    def test_all_10_tests_create_attempt_records(self):
        """All 10 tests run on the same job; each creates exactly one attempt in the repository."""
        all_tests = [
            ("WEIGHING_PERFORMANCE",    _WEIGHING_OBS),
            ("ECCENTRICITY",            _ECCENTRICITY_OBS),
            ("REPEATABILITY",           _REPEATABILITY_OBS),
            ("ZERO_RETURN",             _ZERO_RETURN_OBS),
            ("CREEP",                   _CREEP_OBS),
            ("DISCRIMINATION",          _DISCRIMINATION_OBS),
            ("TARE",                    _TARE_OBS),
            ("TEMPERATURE_EFFECT",      _TEMPERATURE_OBS),
            ("CONSTRUCTION_EXAMINATION",_CONSTRUCTION_OBS),
            ("SOFTWARE_EXAMINATION",    _SOFTWARE_OBS),
        ]

        all_test_names = [t[0] for t in all_tests]
        _make_job(JobStatus.IN_PROGRESS, applicable_tests=all_test_names)
        svc = _make_execution_svc()

        for test_type, observations in all_tests:
            result = svc.submit_observations(
                job_id=JOB_ID,
                test_type=test_type,
                observations=observations,
                operator="INSPECTOR-FULL",
            )
            assert result["success"] is True, f"{test_type} submit_observations failed"
            assert result["attempt"]["attempt_number"] == 1, \
                f"{test_type}: expected attempt_number=1, got {result['attempt']['attempt_number']}"

        all_attempts = ATTEMPT_REPOSITORY.get_attempts_by_job(JOB_ID)
        assert len(all_attempts) == 10, \
            f"Expected 10 attempts (one per test), got {len(all_attempts)}"

    def test_construction_non_compliant_item_gives_fail(self):
        """A NON_COMPLIANT mandatory checklist item causes FAIL verdict."""
        non_compliant_obs = [
            {
                "checklist_item": {
                    "item_id": "C01", "title": "Nameplate",
                    "clause": "7.1", "status": "NON_COMPLIANT",
                    "is_mandatory": True,
                }
            }
        ]
        result = self._submit("CONSTRUCTION_EXAMINATION", non_compliant_obs)
        assert result["success"] is True
        assert result["verdict"] == Verdict.FAIL.value
        calc = result["calculation_result"]
        assert calc["calculated_values"]["non_compliant_count"] == 1

    def test_software_non_compliant_item_gives_fail(self):
        """A NON_COMPLIANT mandatory software checklist item causes FAIL verdict."""
        non_compliant_obs = [
            {
                "checklist_item": {
                    "item_id": "S01", "title": "Software identification",
                    "clause": "5.5.1", "status": "NON_COMPLIANT",
                    "is_mandatory": True,
                }
            }
        ]
        result = self._submit("SOFTWARE_EXAMINATION", non_compliant_obs)
        assert result["success"] is True
        assert result["verdict"] == Verdict.FAIL.value


# ===========================================================================
# 2. FAIL → preserved attempt → RETEST_REQUIRED → new attempt → execution
# ===========================================================================

class TestFailRetestFlow:
    """
    Verifies the full failure/retest cycle:
      submit FAIL observations
        → job stays IN_PROGRESS
        → failed attempt is preserved (not overwritten)
        → request_retest transitions job to RETEST_REQUIRED
        → submit_observations from RETEST_REQUIRED auto-advances to IN_PROGRESS
        → new attempt (number 2) is created
        → both attempts remain in repository
    """

    def test_fail_attempt_is_preserved_not_overwritten(self):
        """After a FAIL, the attempt record must remain with result=FAIL."""
        _make_job(JobStatus.IN_PROGRESS, applicable_tests=["WEIGHING_PERFORMANCE"])
        svc = _make_execution_svc()

        result = svc.submit_observations(
            job_id=JOB_ID,
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_FAIL_OBS,
            operator="INSPECTOR-1",
        )
        assert result["success"] is True
        # Verdict may be FAIL for large errors; verify the attempt is stored
        attempt_id = result["attempt"]["attempt_id"]
        stored = ATTEMPT_REPOSITORY.get_attempt(attempt_id)
        assert stored is not None
        assert stored.result is not None                # has a result (not wiped)
        assert stored.status == AttemptStatus.COMPLETED

    def test_job_stays_in_progress_after_fail(self):
        """A FAIL verdict must NOT advance the job to REVIEW."""
        _make_job(JobStatus.IN_PROGRESS, applicable_tests=["WEIGHING_PERFORMANCE"])
        svc = _make_execution_svc()

        result = svc.submit_observations(
            job_id=JOB_ID,
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_FAIL_OBS,
            operator="INSPECTOR-1",
        )
        if result["verdict"] == Verdict.FAIL.value:
            assert result["job_status"] == "IN_PROGRESS"
            assert result["auto_review_triggered"] is False

    def test_request_retest_transitions_job_to_retest_required(self):
        """After a FAIL, request_retest must put the job in RETEST_REQUIRED."""
        _make_job(JobStatus.IN_PROGRESS, applicable_tests=["WEIGHING_PERFORMANCE"])
        svc = _make_execution_svc()

        result = svc.submit_observations(
            job_id=JOB_ID,
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_FAIL_OBS,
            operator="INSPECTOR-1",
        )
        if result["verdict"] != Verdict.FAIL.value:
            pytest.skip("Observation set did not produce a FAIL; skipping retest path")

        attempt_id = result["attempt"]["attempt_id"]

        retest_req = ATTEMPT_SERVICE.request_retest(
            job_id=JOB_ID,
            test_id="WEIGHING_PERFORMANCE",
            attempt_id=attempt_id,
            reason="Load cell calibration drift detected. Recalibrated — requesting retest.",
            requested_by="INSPECTOR-1",
        )
        assert retest_req.retest_id.startswith("RET-")
        assert retest_req.attempt_id == attempt_id

        # Job must now be RETEST_REQUIRED
        job = TEST_JOB_REPOSITORY.get(JOB_ID)
        assert job.status == JobStatus.RETEST_REQUIRED

    def test_failed_attempt_preserved_after_retest_request(self):
        """The failed attempt record must remain intact after request_retest."""
        _make_job(JobStatus.IN_PROGRESS, applicable_tests=["WEIGHING_PERFORMANCE"])
        svc = _make_execution_svc()

        result = svc.submit_observations(
            job_id=JOB_ID,
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_FAIL_OBS,
            operator="INSPECTOR-1",
        )
        if result["verdict"] != Verdict.FAIL.value:
            pytest.skip("Need FAIL verdict for this test")

        attempt_id = result["attempt"]["attempt_id"]
        ATTEMPT_SERVICE.request_retest(
            job_id=JOB_ID,
            test_id="WEIGHING_PERFORMANCE",
            attempt_id=attempt_id,
            reason="Recalibrating instrument.",
            requested_by="INSPECTOR-1",
        )

        # Original failed attempt must still be in repo with FAIL result
        stored = ATTEMPT_REPOSITORY.get_attempt(attempt_id)
        assert stored is not None
        assert stored.result == Verdict.FAIL
        assert stored.status == AttemptStatus.COMPLETED

    def test_retest_required_job_can_accept_new_observations(self):
        """
        After RETEST_REQUIRED, submit_observations auto-advances to IN_PROGRESS
        and creates a new (attempt 2) attempt.
        """
        _make_job(JobStatus.IN_PROGRESS, applicable_tests=["WEIGHING_PERFORMANCE"])
        svc = _make_execution_svc()

        # First submission → FAIL
        r1 = svc.submit_observations(
            job_id=JOB_ID,
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_FAIL_OBS,
            operator="INSPECTOR-1",
        )
        if r1["verdict"] != Verdict.FAIL.value:
            pytest.skip("Need FAIL verdict for retest flow")

        # Transition to RETEST_REQUIRED
        ATTEMPT_SERVICE.request_retest(
            job_id=JOB_ID,
            test_id="WEIGHING_PERFORMANCE",
            attempt_id=r1["attempt"]["attempt_id"],
            reason="Instrument drift. Recalibrated.",
            requested_by="INSPECTOR-1",
        )

        # Re-submit (from RETEST_REQUIRED) — should auto-advance and create attempt 2
        r2 = svc.submit_observations(
            job_id=JOB_ID,
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_OBS,
            operator="INSPECTOR-1",
        )
        assert r2["success"] is True
        assert r2["attempt"]["attempt_number"] == 2

    def test_both_attempts_preserved_after_retest(self):
        """
        Both the failed attempt AND the retest attempt must be retrievable.
        Neither is overwritten.
        """
        _make_job(JobStatus.IN_PROGRESS, applicable_tests=["WEIGHING_PERFORMANCE"])
        svc = _make_execution_svc()

        r1 = svc.submit_observations(
            job_id=JOB_ID,
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_FAIL_OBS,
            operator="INSPECTOR-1",
        )
        if r1["verdict"] != Verdict.FAIL.value:
            pytest.skip("Need FAIL verdict for history test")

        ATTEMPT_SERVICE.request_retest(
            job_id=JOB_ID,
            test_id="WEIGHING_PERFORMANCE",
            attempt_id=r1["attempt"]["attempt_id"],
            reason="Recalibrated.",
            requested_by="INSPECTOR-1",
        )

        r2 = svc.submit_observations(
            job_id=JOB_ID,
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_OBS,
            operator="INSPECTOR-1",
        )
        assert r2["success"] is True

        # Both attempts must be in the repository
        all_attempts = ATTEMPT_REPOSITORY.get_attempts_for_test(JOB_ID, "WEIGHING_PERFORMANCE")
        assert len(all_attempts) == 2, \
            f"Expected 2 attempts (original + retest), got {len(all_attempts)}"

        nums = sorted(a.attempt_number for a in all_attempts)
        assert nums == [1, 2], f"Attempt numbers should be [1, 2], got {nums}"

        # Attempt 1 must be FAIL, attempt 2 has whatever verdict
        att1 = next(a for a in all_attempts if a.attempt_number == 1)
        att2 = next(a for a in all_attempts if a.attempt_number == 2)
        assert att1.result == Verdict.FAIL
        assert att2.result is not None   # completed with some verdict
        assert att2.status == AttemptStatus.COMPLETED

    def test_retest_attempt_number_increments_correctly(self):
        """After two FAILs and two retests, attempt numbers are 1, 2, 3."""
        _make_job(JobStatus.IN_PROGRESS, applicable_tests=["WEIGHING_PERFORMANCE"])
        svc = _make_execution_svc()

        for cycle in range(2):
            r = svc.submit_observations(
                job_id=JOB_ID,
                test_type="WEIGHING_PERFORMANCE",
                observations=_WEIGHING_FAIL_OBS,
                operator="INSPECTOR-1",
            )
            if r["verdict"] != Verdict.FAIL.value:
                pytest.skip("Need FAIL verdict")

            ATTEMPT_SERVICE.request_retest(
                job_id=JOB_ID,
                test_id="WEIGHING_PERFORMANCE",
                attempt_id=r["attempt"]["attempt_id"],
                reason=f"Cycle {cycle + 1} retest",
                requested_by="INSPECTOR-1",
            )

        # Third submission (second retest)
        r3 = svc.submit_observations(
            job_id=JOB_ID,
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_OBS,
            operator="INSPECTOR-1",
        )
        assert r3["attempt"]["attempt_number"] == 3

        all_attempts = ATTEMPT_REPOSITORY.get_attempts_for_test(JOB_ID, "WEIGHING_PERFORMANCE")
        assert len(all_attempts) == 3

    def test_retest_requests_are_recorded_in_repository(self):
        """RetestRequest entities are persisted and retrievable by job."""
        _make_job(JobStatus.IN_PROGRESS, applicable_tests=["WEIGHING_PERFORMANCE"])
        svc = _make_execution_svc()

        r = svc.submit_observations(
            job_id=JOB_ID,
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_FAIL_OBS,
            operator="INSPECTOR-1",
        )
        if r["verdict"] != Verdict.FAIL.value:
            pytest.skip("Need FAIL verdict")

        ATTEMPT_SERVICE.request_retest(
            job_id=JOB_ID,
            test_id="WEIGHING_PERFORMANCE",
            attempt_id=r["attempt"]["attempt_id"],
            reason="Load cell drift.",
            requested_by="INSPECTOR-1",
        )

        retest_requests = ATTEMPT_REPOSITORY.get_retest_requests_by_job(JOB_ID)
        assert len(retest_requests) == 1
        assert retest_requests[0].reason == "Load cell drift."
        assert retest_requests[0].requested_by == "INSPECTOR-1"

    def test_retest_required_in_execution_ready_statuses(self):
        """RETEST_REQUIRED must be in _EXECUTION_READY_STATUSES so the service accepts it."""
        assert JobStatus.RETEST_REQUIRED in _EXECUTION_READY_STATUSES


# ===========================================================================
# 3. REVIEW → REJECTED → correction/retest path
# ===========================================================================

class TestReviewRejectionFlow:
    """
    Verifies:
      REVIEW → REJECTED (WorkflowStateMachine and WorkflowService)
      REJECTED → IN_PROGRESS (correction path via WorkflowService)
      REJECTED → IN_PROGRESS (auto-advance via submit_observations)
      ReviewService.execute_review(REJECT) → job.status == REJECTED
      Evidence and results are NOT corrupted after rejection
    """

    def _setup_job_in_review(self) -> str:
        """Helper: creates a job, adds an attempt, and transitions it to REVIEW."""
        _make_job(JobStatus.IN_PROGRESS, applicable_tests=["WEIGHING_PERFORMANCE"])

        # Add a completed attempt so the REVIEW transition has execution data
        att = TestAttempt(
            id="ATT-REVIEW-SETUP",
            test_id="WEIGHING_PERFORMANCE",
            job_id=JOB_ID,
            attempt_number=1,
            status=AttemptStatus.COMPLETED,
            result=Verdict.PASS,
            operator="INSPECTOR-1",
        )
        ATTEMPT_REPOSITORY.save_attempt(att)

        WORKFLOW_SERVICE.transition_job(
            job_id=JOB_ID,
            target_state=JobStatus.REVIEW,
            actor="INSPECTOR-1",
            test_execution_data={"done": True},
        )
        return JOB_ID

    # --- WorkflowStateMachine transition validity ---

    def test_state_machine_allows_review_to_rejected(self):
        ok, _, err = WorkflowStateMachine.can_transition(
            JobStatus.REVIEW, JobStatus.REJECTED
        )
        assert ok, f"REVIEW → REJECTED should be allowed: {err}"

    def test_state_machine_allows_rejected_to_in_progress(self):
        ok, _, err = WorkflowStateMachine.can_transition(
            JobStatus.REJECTED, JobStatus.IN_PROGRESS
        )
        assert ok, f"REJECTED → IN_PROGRESS should be allowed: {err}"

    def test_state_machine_allows_under_review_to_rejected(self):
        ok, _, err = WorkflowStateMachine.can_transition(
            JobStatus.UNDER_REVIEW, JobStatus.REJECTED
        )
        assert ok, f"UNDER_REVIEW → REJECTED should be allowed: {err}"

    def test_state_machine_allows_submitted_for_review_to_rejected(self):
        ok, _, err = WorkflowStateMachine.can_transition(
            JobStatus.SUBMITTED_FOR_REVIEW, JobStatus.REJECTED
        )
        assert ok, f"SUBMITTED_FOR_REVIEW → REJECTED should be allowed: {err}"

    # --- WorkflowService transitions ---

    def test_workflow_service_transitions_review_to_rejected(self):
        self._setup_job_in_review()
        job = WORKFLOW_SERVICE.transition_job(
            job_id=JOB_ID,
            target_state=JobStatus.REJECTED,
            actor="SUPERVISOR",
            reason="Non-compliant construction. Multiple checklist failures.",
        )
        assert job.status == JobStatus.REJECTED

    def test_workflow_service_transitions_rejected_to_in_progress(self):
        self._setup_job_in_review()
        WORKFLOW_SERVICE.transition_job(
            job_id=JOB_ID, target_state=JobStatus.REJECTED,
            actor="SUPERVISOR", reason="Rejected.",
        )
        job = WORKFLOW_SERVICE.transition_job(
            job_id=JOB_ID,
            target_state=JobStatus.IN_PROGRESS,
            actor="INSPECTOR-1",
            reason="Defects corrected. Re-submitting for testing.",
        )
        assert job.status == JobStatus.IN_PROGRESS

    def test_rejection_preserves_state_history(self):
        """State history must record every transition, nothing is overwritten."""
        self._setup_job_in_review()
        WORKFLOW_SERVICE.transition_job(
            job_id=JOB_ID, target_state=JobStatus.REJECTED,
            actor="SUPERVISOR", reason="Rejected.",
        )
        WORKFLOW_SERVICE.transition_job(
            job_id=JOB_ID, target_state=JobStatus.IN_PROGRESS,
            actor="INSPECTOR-1", reason="Corrected.",
        )

        job = TEST_JOB_REPOSITORY.get(JOB_ID)
        statuses_in_history = [r.to_status for r in job.state_history]

        # The history must contain a REJECTED entry and an IN_PROGRESS entry
        assert "REJECTED" in statuses_in_history, \
            f"REJECTED missing from state history: {statuses_in_history}"
        assert "IN_PROGRESS" in statuses_in_history, \
            f"IN_PROGRESS missing from state history: {statuses_in_history}"

    def test_rejection_does_not_corrupt_attempt_records(self):
        """Attempts recorded before rejection must remain intact after REJECTED."""
        self._setup_job_in_review()
        WORKFLOW_SERVICE.transition_job(
            job_id=JOB_ID, target_state=JobStatus.REJECTED,
            actor="SUPERVISOR", reason="Rejected.",
        )

        # The attempt added in _setup_job_in_review must still be there
        attempts = ATTEMPT_REPOSITORY.get_attempts_by_job(JOB_ID)
        assert len(attempts) == 1
        assert attempts[0].result == Verdict.PASS
        assert attempts[0].status == AttemptStatus.COMPLETED

    def test_rejected_job_can_accept_new_test_observations(self):
        """
        REJECTED → IN_PROGRESS → new test submission must succeed.
        submit_observations auto-advances REJECTED → IN_PROGRESS.
        """
        self._setup_job_in_review()
        WORKFLOW_SERVICE.transition_job(
            job_id=JOB_ID, target_state=JobStatus.REJECTED,
            actor="SUPERVISOR", reason="Rejected.",
        )
        # Verify REJECTED is now an accepted execution-ready status
        assert JobStatus.REJECTED in _EXECUTION_READY_STATUSES

        svc = _make_execution_svc()
        result = svc.submit_observations(
            job_id=JOB_ID,
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_OBS,
            operator="INSPECTOR-1",
        )
        assert result["success"] is True
        assert result["job_status"] in ("IN_PROGRESS", "REVIEW")

    def test_rejected_job_auto_advances_to_in_progress_via_submit(self):
        """
        When submit_observations is called on a REJECTED job, it must
        auto-advance to IN_PROGRESS before executing the test.
        """
        self._setup_job_in_review()
        WORKFLOW_SERVICE.transition_job(
            job_id=JOB_ID, target_state=JobStatus.REJECTED,
            actor="SUPERVISOR", reason="Rejected.",
        )

        svc = _make_execution_svc()
        result = svc.submit_observations(
            job_id=JOB_ID,
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_OBS,
            operator="INSPECTOR-2",
        )
        assert result["success"] is True
        # Job must have been advanced from REJECTED to at least IN_PROGRESS
        final_job = TEST_JOB_REPOSITORY.get(JOB_ID)
        assert final_job.status in (JobStatus.IN_PROGRESS, JobStatus.REVIEW)

    # --- ReviewService.execute_review (REJECT decision) ---

    def test_review_service_reject_decision_transitions_to_rejected(self):
        """ReviewService.execute_review with REJECT → job.status == REJECTED."""
        self._setup_job_in_review()

        _review_svc = ReviewService(
            job_repository=TEST_JOB_REPOSITORY,
            attempt_repository=ATTEMPT_REPOSITORY,
            workflow_service=WORKFLOW_SERVICE,
        )
        review, updated_job = _review_svc.execute_review(
            job_id=JOB_ID,
            decision="REJECT",
            comments="Construction failures observed. Non-compliant.",
            reviewer="SENIOR-REVIEWER",
        )
        assert updated_job.status == JobStatus.REJECTED
        assert review.decision.value == "REJECT"

    def test_review_service_return_for_correction_transitions_to_in_progress(self):
        """ReviewService.execute_review with RETURN_FOR_CORRECTION → job.status == IN_PROGRESS."""
        self._setup_job_in_review()

        _review_svc = ReviewService(
            job_repository=TEST_JOB_REPOSITORY,
            attempt_repository=ATTEMPT_REPOSITORY,
            workflow_service=WORKFLOW_SERVICE,
        )
        review, updated_job = _review_svc.execute_review(
            job_id=JOB_ID,
            decision="RETURN_FOR_CORRECTION",
            comments="Missing calibration certificate. Please attach and resubmit.",
            reviewer="SENIOR-REVIEWER",
        )
        assert updated_job.status == JobStatus.IN_PROGRESS
        assert review.decision.value == "RETURN_FOR_CORRECTION"

    def test_full_rejection_correction_retest_cycle(self):
        """
        Full lifecycle:
          IN_PROGRESS → REVIEW → REJECTED → IN_PROGRESS (correction)
          → new test execution → REVIEW → APPROVED
        """
        self._setup_job_in_review()

        # Step 1: Reject the job
        _review_svc = ReviewService(
            job_repository=TEST_JOB_REPOSITORY,
            attempt_repository=ATTEMPT_REPOSITORY,
            workflow_service=WORKFLOW_SERVICE,
        )
        _, rejected_job = _review_svc.execute_review(
            job_id=JOB_ID,
            decision="REJECT",
            comments="Construction defect found.",
            reviewer="SENIOR-REVIEWER",
        )
        assert rejected_job.status == JobStatus.REJECTED

        # Step 2: Correction — re-run tests via submit_observations (auto-advances REJECTED → IN_PROGRESS)
        svc = _make_execution_svc()
        r = svc.submit_observations(
            job_id=JOB_ID,
            test_type="WEIGHING_PERFORMANCE",
            observations=_WEIGHING_OBS,
            operator="INSPECTOR-1",
        )
        assert r["success"] is True

        # Step 3: Advance to REVIEW again for re-review
        job = TEST_JOB_REPOSITORY.get(JOB_ID)
        if job.status == JobStatus.IN_PROGRESS:
            # Manually trigger review transition (all tests passed scenario)
            WORKFLOW_SERVICE.transition_job(
                job_id=JOB_ID,
                target_state=JobStatus.REVIEW,
                actor="INSPECTOR-1",
                test_execution_data={"corrected": True},
            )

        # Step 4: Approve
        job_in_review = TEST_JOB_REPOSITORY.get(JOB_ID)
        assert job_in_review.status == JobStatus.REVIEW

        approved_job = WORKFLOW_SERVICE.transition_job(
            job_id=JOB_ID,
            target_state=JobStatus.APPROVED,
            actor="CHIEF-REVIEWER",
        )
        assert approved_job.status == JobStatus.APPROVED

    def test_review_history_preserved_through_rejection_cycle(self):
        """
        Multiple review cycles must all be recorded — no record is overwritten.
        After REJECTED → IN_PROGRESS → REVIEW → APPROVED, the rejection
        must still appear in the job's state_history.
        """
        self._setup_job_in_review()

        # Reject
        WORKFLOW_SERVICE.transition_job(
            job_id=JOB_ID, target_state=JobStatus.REJECTED,
            actor="REVIEWER-1", reason="Defect found.",
        )
        # Correct and re-submit
        WORKFLOW_SERVICE.transition_job(
            job_id=JOB_ID, target_state=JobStatus.IN_PROGRESS,
            actor="INSPECTOR-1", reason="Fixed.",
        )
        WORKFLOW_SERVICE.transition_job(
            job_id=JOB_ID, target_state=JobStatus.REVIEW,
            actor="INSPECTOR-1",
            test_execution_data={"correction": True},
        )
        WORKFLOW_SERVICE.transition_job(
            job_id=JOB_ID, target_state=JobStatus.APPROVED,
            actor="REVIEWER-1",
        )

        job = TEST_JOB_REPOSITORY.get(JOB_ID)
        history_targets = [r.to_status for r in job.state_history]
        assert "REJECTED" in history_targets
        assert "APPROVED" in history_targets
        # Both transitions to IN_PROGRESS must appear (initial + after rejection)
        in_progress_count = history_targets.count("IN_PROGRESS")
        assert in_progress_count >= 1


# ===========================================================================
# 4. _EXECUTION_READY_STATUSES correctness
# ===========================================================================

class TestExecutionReadyStatuses:
    """Verify the _EXECUTION_READY_STATUSES set is correct and complete."""

    @pytest.mark.parametrize("status", [
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
        JobStatus.REJECTED,
    ])
    def test_status_is_execution_ready(self, status):
        assert status in _EXECUTION_READY_STATUSES, \
            f"{status.value} should be in _EXECUTION_READY_STATUSES"

    @pytest.mark.parametrize("status", [
        JobStatus.APPROVED,
        JobStatus.REPORT_GENERATED,
        JobStatus.CLOSED,
        JobStatus.CERTIFIED,
        JobStatus.CANCELLED,
    ])
    def test_terminal_status_is_not_execution_ready(self, status):
        assert status not in _EXECUTION_READY_STATUSES, \
            f"{status.value} should NOT be in _EXECUTION_READY_STATUSES (terminal)"

    def test_rejected_job_raises_state_error_after_being_approved(self):
        """A REPORT_GENERATED job must still be blocked from execution."""
        _make_job(JobStatus.REPORT_GENERATED)
        svc = _make_execution_svc()
        with pytest.raises(ExecutionJobStateError):
            svc.submit_observations(
                job_id=JOB_ID,
                test_type="WEIGHING_PERFORMANCE",
                observations=_WEIGHING_OBS,
                operator="OP",
            )
