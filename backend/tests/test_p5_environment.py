"""
MetrIQ P5 Environment Condition Recording Unit Tests
====================================================
Person 5: Workflow + Evidence Engineer

Comprehensive test suite validating:
1. Environment Condition domain models and measurement validation
2. Validation rules (ranges for temp, humidity, pressure; non-empty strings; timestamps)
3. One-to-many job relationship and chronological history tracking
4. Workflow stage restrictions (allowed in READY/IN_PROGRESS/RETEST_REQUIRED; rejected in REPORT_GENERATED)
5. Update restrictions (prevented in REVIEW, APPROVED, and terminal states)
6. REST API endpoints (/jobs/{id}/environment, /history, /environment/{id}, /test-jobs compatibility)
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app.api.router import api_router
from app.environment.models import EnvironmentCondition
from app.environment.repository import ENVIRONMENT_REPOSITORY, EnvironmentRepository
from app.environment.service import (
    ENVIRONMENT_SERVICE,
    EnvironmentNotFoundError,
    EnvironmentService,
    EnvironmentStageError,
    EnvironmentUpdateRestrictedError,
    EnvironmentValidationError,
)
from app.jobs.models import JobPriority, JobStatus, JobType, TestJob
from app.jobs.repository import TEST_JOB_REPOSITORY


@pytest.fixture(autouse=True)
def clean_repositories():
    """Ensures test isolation by resetting repositories before each test."""
    ENVIRONMENT_REPOSITORY.clear()
    TEST_JOB_REPOSITORY.clear()
    yield
    ENVIRONMENT_REPOSITORY.clear()
    TEST_JOB_REPOSITORY.clear()


@pytest.fixture
def client():
    """FastAPI test client with the integrated API router."""
    from fastapi import FastAPI
    app = FastAPI(title="Test MetrIQ P5 Environment")
    app.include_router(api_router)
    return TestClient(app)


def _create_sample_job(
    job_id: str = "JOB-ENV-001",
    status: JobStatus = JobStatus.IN_PROGRESS,
) -> TestJob:
    """Helper to persist a test job with specified status."""
    job = TestJob(
        job_id=job_id,
        instrument_id="INST-NAWI-001",
        job_type=JobType.RE_VERIFICATION,
        status=status,
        priority=JobPriority.NORMAL,
        test_execution_data={"status": "INITIAL_RUN", "readings_count": 5},
    )
    TEST_JOB_REPOSITORY.save(job)
    return job


# =============================================================================
# 1. Domain Model & Validation Tests
# =============================================================================

class TestP5EnvironmentDomain:
    """Tests core business logic and validations for EnvironmentCondition entities."""

    def test_01_record_valid_environment(self):
        """Records a valid ambient observation during IN_PROGRESS stage."""
        job = _create_sample_job("JOB-01", status=JobStatus.IN_PROGRESS)

        rec = ENVIRONMENT_SERVICE.record_environment("JOB-01", {
            "temperature": 23.5,
            "humidity": 55.0,
            "atmospheric_pressure": 1013.25,
            "location": "GATC Weighing Bay 3",
            "operator": "Insp. Sharma",
            "notes": "HVAC steady, no draft.",
        })

        assert rec.id.startswith("ENV-")
        assert rec.job_id == "JOB-01"
        assert rec.temperature == 23.5
        assert rec.humidity == 55.0
        assert rec.atmospheric_pressure == 1013.25
        assert rec.location == "GATC Weighing Bay 3"
        assert rec.operator == "Insp. Sharma"
        assert rec.notes == "HVAC steady, no draft."
        assert rec.created_at is not None

        # Verify job has record in environment_records
        updated_job = TEST_JOB_REPOSITORY.get("JOB-01")
        assert len(updated_job.environment_records) == 1
        assert updated_job.environment_records[0]["id"] == rec.id
        assert updated_job.latest_environment["id"] == rec.id

    def test_02_record_environment_non_existent_job(self):
        """Fails with JobNotFoundError when recording on a non-existent job."""
        from app.workflow.service import JobNotFoundError
        with pytest.raises(JobNotFoundError):
            ENVIRONMENT_SERVICE.record_environment("NON-EXISTENT-JOB", {
                "temperature": 20.0,
                "humidity": 50.0,
                "atmospheric_pressure": 1010.0,
                "location": "Lab A",
                "operator": "Operator 1",
            })

    def test_03_temperature_range_validation(self):
        """Enforces realistic temperature limits (-50°C to +100°C)."""
        job = _create_sample_job("JOB-TEMP", status=JobStatus.IN_PROGRESS)

        # Extreme cold below -50°C
        with pytest.raises(EnvironmentValidationError) as exc:
            ENVIRONMENT_SERVICE.record_environment("JOB-TEMP", {
                "temperature": -51.0,
                "humidity": 45.0,
                "atmospheric_pressure": 1000.0,
                "location": "Site",
                "operator": "Op",
            })
        assert "temperature" in str(exc.value).lower()

        # Extreme heat above 100°C
        with pytest.raises(EnvironmentValidationError) as exc:
            ENVIRONMENT_SERVICE.record_environment("JOB-TEMP", {
                "temperature": 105.0,
                "humidity": 45.0,
                "atmospheric_pressure": 1000.0,
                "location": "Site",
                "operator": "Op",
            })
        assert "temperature" in str(exc.value).lower()

        # Non-numeric temperature
        with pytest.raises(EnvironmentValidationError):
            ENVIRONMENT_SERVICE.record_environment("JOB-TEMP", {
                "temperature": "very-cold",
                "humidity": 45.0,
                "atmospheric_pressure": 1000.0,
                "location": "Site",
                "operator": "Op",
            })

        # Boolean temperature (must be rejected)
        with pytest.raises(EnvironmentValidationError):
            ENVIRONMENT_SERVICE.record_environment("JOB-TEMP", {
                "temperature": True,
                "humidity": 45.0,
                "atmospheric_pressure": 1000.0,
                "location": "Site",
                "operator": "Op",
            })

    def test_04_humidity_range_validation(self):
        """Enforces relative humidity range 0% to 100%."""
        job = _create_sample_job("JOB-HUM", status=JobStatus.IN_PROGRESS)

        # Negative humidity
        with pytest.raises(EnvironmentValidationError) as exc:
            ENVIRONMENT_SERVICE.record_environment("JOB-HUM", {
                "temperature": 22.0,
                "humidity": -1.0,
                "atmospheric_pressure": 1013.0,
                "location": "Site",
                "operator": "Op",
            })
        assert "humidity" in str(exc.value).lower()

        # Humidity > 100%
        with pytest.raises(EnvironmentValidationError) as exc:
            ENVIRONMENT_SERVICE.record_environment("JOB-HUM", {
                "temperature": 22.0,
                "humidity": 101.5,
                "atmospheric_pressure": 1013.0,
                "location": "Site",
                "operator": "Op",
            })
        assert "humidity" in str(exc.value).lower()

        # Valid boundaries 0.0 and 100.0
        rec0 = ENVIRONMENT_SERVICE.record_environment("JOB-HUM", {
            "temperature": 20.0,
            "humidity": 0.0,
            "atmospheric_pressure": 1013.0,
            "location": "Chamber",
            "operator": "Op",
        })
        assert rec0.humidity == 0.0

        rec100 = ENVIRONMENT_SERVICE.record_environment("JOB-HUM", {
            "temperature": 20.0,
            "humidity": 100.0,
            "atmospheric_pressure": 1013.0,
            "location": "Chamber",
            "operator": "Op",
        })
        assert rec100.humidity == 100.0

    def test_05_pressure_validation(self):
        """Enforces positive atmospheric pressure."""
        job = _create_sample_job("JOB-PRESS", status=JobStatus.IN_PROGRESS)

        # Zero pressure
        with pytest.raises(EnvironmentValidationError) as exc:
            ENVIRONMENT_SERVICE.record_environment("JOB-PRESS", {
                "temperature": 20.0,
                "humidity": 50.0,
                "atmospheric_pressure": 0.0,
                "location": "Site",
                "operator": "Op",
            })
        assert "pressure" in str(exc.value).lower()

        # Negative pressure
        with pytest.raises(EnvironmentValidationError):
            ENVIRONMENT_SERVICE.record_environment("JOB-PRESS", {
                "temperature": 20.0,
                "humidity": 50.0,
                "atmospheric_pressure": -1013.0,
                "location": "Site",
                "operator": "Op",
            })

    def test_06_string_and_timestamp_validations(self):
        """Validates mandatory location, operator, and timestamp format."""
        job = _create_sample_job("JOB-STR", status=JobStatus.IN_PROGRESS)

        # Empty location
        with pytest.raises(EnvironmentValidationError) as exc:
            ENVIRONMENT_SERVICE.record_environment("JOB-STR", {
                "temperature": 20.0,
                "humidity": 50.0,
                "atmospheric_pressure": 1000.0,
                "location": "   ",
                "operator": "Op",
            })
        assert "location" in str(exc.value).lower()

        # Empty operator
        with pytest.raises(EnvironmentValidationError) as exc:
            ENVIRONMENT_SERVICE.record_environment("JOB-STR", {
                "temperature": 20.0,
                "humidity": 50.0,
                "atmospheric_pressure": 1000.0,
                "location": "Site A",
                "operator": "",
            })
        assert "operator" in str(exc.value).lower()

        # Malformed recorded_at timestamp
        with pytest.raises(EnvironmentValidationError) as exc:
            ENVIRONMENT_SERVICE.record_environment("JOB-STR", {
                "temperature": 20.0,
                "humidity": 50.0,
                "atmospheric_pressure": 1000.0,
                "location": "Site A",
                "operator": "Op",
                "recorded_at": "not-a-timestamp",
            })
        assert "recorded_at" in str(exc.value).lower()

        # Valid ISO timestamp
        rec = ENVIRONMENT_SERVICE.record_environment("JOB-STR", {
            "temperature": 21.0,
            "humidity": 52.0,
            "atmospheric_pressure": 1008.0,
            "location": "Site A",
            "operator": "Op",
            "recorded_at": "2026-09-19T10:30:00Z",
        })
        assert rec.recorded_at == "2026-09-19T10:30:00Z"


# =============================================================================
# 2. Workflow Stage Checks & One-to-Many History
# =============================================================================

class TestP5EnvironmentWorkflowAndHistory:
    """Tests lifecycle gating and historical observations."""

    def test_10_allowed_workflow_stages_for_recording(self):
        """Allows recording in READY, IN_PROGRESS, RETEST_REQUIRED, and DRAFT."""
        for state in [JobStatus.DRAFT, JobStatus.READY, JobStatus.IN_PROGRESS, JobStatus.RETEST_REQUIRED]:
            job_id = f"JOB-STAGE-{state.value}"
            _create_sample_job(job_id, status=state)

            rec = ENVIRONMENT_SERVICE.record_environment(job_id, {
                "temperature": 21.0,
                "humidity": 50.0,
                "atmospheric_pressure": 1012.0,
                "location": "Test Area",
                "operator": "Inspector",
            })
            assert rec is not None
            assert rec.job_id == job_id

    def test_11_reject_recording_in_terminal_state(self):
        """Rejects recording when job is in terminal state REPORT_GENERATED."""
        job = _create_sample_job("JOB-TERMINAL", status=JobStatus.REPORT_GENERATED)

        with pytest.raises(EnvironmentStageError) as exc:
            ENVIRONMENT_SERVICE.record_environment("JOB-TERMINAL", {
                "temperature": 20.0,
                "humidity": 50.0,
                "atmospheric_pressure": 1010.0,
                "location": "Test Area",
                "operator": "Inspector",
            })
        assert "terminal state" in str(exc.value).lower()

    def test_12_multiple_records_chronological_history(self):
        """Retains historical records without deletion and preserves chronological order."""
        job = _create_sample_job("JOB-HIST", status=JobStatus.IN_PROGRESS)

        # Record 1: Morning setup
        r1 = ENVIRONMENT_SERVICE.record_environment("JOB-HIST", {
            "temperature": 19.5,
            "humidity": 65.0,
            "atmospheric_pressure": 1015.0,
            "location": "Bench 1",
            "operator": "Op Morning",
            "recorded_at": "2026-09-19T08:00:00Z",
        })

        # Record 2: Mid-day test
        r2 = ENVIRONMENT_SERVICE.record_environment("JOB-HIST", {
            "temperature": 24.0,
            "humidity": 50.0,
            "atmospheric_pressure": 1014.0,
            "location": "Bench 1",
            "operator": "Op Noon",
            "recorded_at": "2026-09-19T12:00:00Z",
        })

        # Record 3: Evening retest
        r3 = ENVIRONMENT_SERVICE.record_environment("JOB-HIST", {
            "temperature": 22.0,
            "humidity": 58.0,
            "atmospheric_pressure": 1013.0,
            "location": "Bench 1",
            "operator": "Op Evening",
            "recorded_at": "2026-09-19T16:00:00Z",
        })

        history = ENVIRONMENT_SERVICE.get_environment_history("JOB-HIST")
        assert len(history) == 3
        assert [h.id for h in history] == [r1.id, r2.id, r3.id]
        assert history[0].temperature == 19.5
        assert history[1].temperature == 24.0
        assert history[2].temperature == 22.0

        latest = ENVIRONMENT_SERVICE.get_latest_environment("JOB-HIST")
        assert latest.id == r3.id
        assert latest.operator == "Op Evening"

        # Check job property
        job_entity = TEST_JOB_REPOSITORY.get("JOB-HIST")
        assert len(job_entity.environment_records) == 3
        assert job_entity.latest_environment["id"] == r3.id

    def test_13_update_environment_allowed_in_progress(self):
        """Allows updating records while job is IN_PROGRESS."""
        job = _create_sample_job("JOB-UPD", status=JobStatus.IN_PROGRESS)

        rec = ENVIRONMENT_SERVICE.record_environment("JOB-UPD", {
            "temperature": 20.0,
            "humidity": 50.0,
            "atmospheric_pressure": 1012.0,
            "location": "Lab",
            "operator": "Op",
        })

        updated = ENVIRONMENT_SERVICE.update_environment("JOB-UPD", rec.id, {
            "temperature": 21.5,
            "notes": "Corrected calibration thermometer reading",
        })

        assert updated.temperature == 21.5
        assert updated.notes == "Corrected calibration thermometer reading"
        assert updated.humidity == 50.0  # untouched

        # Check job entity was synchronized
        job_entity = TEST_JOB_REPOSITORY.get("JOB-UPD")
        assert job_entity.environment_records[0]["temperature"] == 21.5
        assert job_entity.environment_records[0]["notes"] == "Corrected calibration thermometer reading"

    def test_14_update_environment_rejected_in_review(self):
        """Rejects record modification once job enters REVIEW state."""
        job = _create_sample_job("JOB-REV", status=JobStatus.IN_PROGRESS)

        rec = ENVIRONMENT_SERVICE.record_environment("JOB-REV", {
            "temperature": 20.0,
            "humidity": 50.0,
            "atmospheric_pressure": 1012.0,
            "location": "Lab",
            "operator": "Op",
        })

        # Transition job to REVIEW
        job.status = JobStatus.REVIEW
        TEST_JOB_REPOSITORY.save(job)

        with pytest.raises(EnvironmentUpdateRestrictedError) as exc:
            ENVIRONMENT_SERVICE.update_environment("JOB-REV", rec.id, {
                "temperature": 22.0,
            })
        assert "review" in str(exc.value).lower()

    def test_15_update_environment_rejected_in_approved(self):
        """Rejects record modification once job is APPROVED."""
        job = _create_sample_job("JOB-APP", status=JobStatus.IN_PROGRESS)

        rec = ENVIRONMENT_SERVICE.record_environment("JOB-APP", {
            "temperature": 20.0,
            "humidity": 50.0,
            "atmospheric_pressure": 1012.0,
            "location": "Lab",
            "operator": "Op",
        })

        # Transition job to APPROVED
        job.status = JobStatus.APPROVED
        TEST_JOB_REPOSITORY.save(job)

        with pytest.raises(EnvironmentUpdateRestrictedError) as exc:
            ENVIRONMENT_SERVICE.update_environment("JOB-APP", rec.id, {
                "temperature": 22.0,
            })
        assert "approved" in str(exc.value).lower()

    def test_16_update_non_existent_or_mismatched_record(self):
        """Fails gracefully when record not found or belongs to another job."""
        _create_sample_job("JOB-A", status=JobStatus.IN_PROGRESS)
        _create_sample_job("JOB-B", status=JobStatus.IN_PROGRESS)

        rec = ENVIRONMENT_SERVICE.record_environment("JOB-A", {
            "temperature": 20.0,
            "humidity": 50.0,
            "atmospheric_pressure": 1012.0,
            "location": "Lab",
            "operator": "Op",
        })

        # Non-existent record ID
        with pytest.raises(EnvironmentNotFoundError):
            ENVIRONMENT_SERVICE.update_environment("JOB-A", "ENV-NONEXISTENT", {"temperature": 21.0})

        # Record belongs to JOB-A, attempted update under JOB-B
        with pytest.raises(EnvironmentValidationError) as exc:
            ENVIRONMENT_SERVICE.update_environment("JOB-B", rec.id, {"temperature": 21.0})
        assert "belongs to job" in str(exc.value).lower()


# =============================================================================
# 3. REST API Endpoint Tests
# =============================================================================

class TestP5EnvironmentAPI:
    """Tests the FastAPI REST endpoints for environment recording and retrieval."""

    def test_20_api_record_environment_success(self, client):
        """POST /jobs/{jobId}/environment successfully records condition."""
        _create_sample_job("JOB-API-01", status=JobStatus.IN_PROGRESS)

        res = client.post("/jobs/JOB-API-01/environment", json={
            "temperature": 22.4,
            "humidity": 48.0,
            "atmospheric_pressure": 1013.2,
            "location": "Test Platform 1",
            "operator": "Insp. Roy",
            "notes": "Ambient conditions nominal",
        })
        assert res.status_code == 201
        body = res.json()
        assert body["success"] is True
        assert body["data"]["job_id"] == "JOB-API-01"
        assert body["data"]["temperature"] == 22.4
        assert body["data"]["humidity"] == 48.0

    def test_21_api_record_environment_job_not_found(self, client):
        """POST /jobs/{jobId}/environment returns 404 for missing job."""
        res = client.post("/jobs/JOB-MISSING/environment", json={
            "temperature": 22.0,
            "humidity": 50.0,
            "atmospheric_pressure": 1010.0,
            "location": "Loc",
            "operator": "Op",
        })
        assert res.status_code == 404
        assert res.json()["error"] == "JOB_NOT_FOUND"

    def test_22_api_record_environment_validation_error(self, client):
        """POST /jobs/{jobId}/environment returns 400 for out-of-range humidity."""
        _create_sample_job("JOB-API-VAL", status=JobStatus.IN_PROGRESS)

        res = client.post("/jobs/JOB-API-VAL/environment", json={
            "temperature": 22.0,
            "humidity": 120.0,  # invalid
            "atmospheric_pressure": 1010.0,
            "location": "Loc",
            "operator": "Op",
        })
        assert res.status_code == 400
        assert res.json()["error"] == "VALIDATION_ERROR"

    def test_23_api_record_environment_terminal_state_rejected(self, client):
        """POST /jobs/{jobId}/environment returns 400 when job is in REPORT_GENERATED."""
        _create_sample_job("JOB-API-TERM", status=JobStatus.REPORT_GENERATED)

        res = client.post("/jobs/JOB-API-TERM/environment", json={
            "temperature": 22.0,
            "humidity": 50.0,
            "atmospheric_pressure": 1010.0,
            "location": "Loc",
            "operator": "Op",
        })
        assert res.status_code == 400
        assert res.json()["error"] == "JOB_TERMINAL_STATE"

    def test_24_api_get_latest_and_history(self, client):
        """GET /jobs/{jobId}/environment and /history endpoints."""
        _create_sample_job("JOB-API-HIST", status=JobStatus.IN_PROGRESS)

        # Initially no record
        res0 = client.get("/jobs/JOB-API-HIST/environment")
        assert res0.status_code == 404
        assert res0.json()["error"] == "ENVIRONMENT_RECORD_NOT_FOUND"

        # Record first observation
        client.post("/jobs/JOB-API-HIST/environment", json={
            "temperature": 20.0,
            "humidity": 50.0,
            "atmospheric_pressure": 1012.0,
            "location": "Lab",
            "operator": "Op 1",
            "recorded_at": "2026-09-19T09:00:00Z",
        })

        # Record second observation
        client.post("/jobs/JOB-API-HIST/environment", json={
            "temperature": 25.0,
            "humidity": 45.0,
            "atmospheric_pressure": 1011.0,
            "location": "Lab",
            "operator": "Op 2",
            "recorded_at": "2026-09-19T14:00:00Z",
        })

        # GET latest
        res_latest = client.get("/jobs/JOB-API-HIST/environment")
        assert res_latest.status_code == 200
        assert res_latest.json()["data"]["temperature"] == 25.0
        assert res_latest.json()["data"]["operator"] == "Op 2"

        # GET history
        res_hist = client.get("/jobs/JOB-API-HIST/environment/history")
        assert res_hist.status_code == 200
        assert res_hist.json()["count"] == 2
        assert len(res_hist.json()["data"]) == 2

    def test_25_api_update_environment_restrictions(self, client):
        """PUT /jobs/{jobId}/environment/{recordId} updates or rejects in REVIEW."""
        job = _create_sample_job("JOB-API-UPD", status=JobStatus.IN_PROGRESS)

        post_res = client.post("/jobs/JOB-API-UPD/environment", json={
            "temperature": 21.0,
            "humidity": 50.0,
            "atmospheric_pressure": 1012.0,
            "location": "Lab",
            "operator": "Op",
        })
        record_id = post_res.json()["data"]["id"]

        # Valid update
        put_res = client.put(f"/jobs/JOB-API-UPD/environment/{record_id}", json={
            "temperature": 23.0,
            "notes": "Updated note via API",
        })
        assert put_res.status_code == 200
        assert put_res.json()["data"]["temperature"] == 23.0

        # Change job to REVIEW
        job.status = JobStatus.REVIEW
        TEST_JOB_REPOSITORY.save(job)

        # Update should now be rejected
        put_blocked = client.put(f"/jobs/JOB-API-UPD/environment/{record_id}", json={
            "temperature": 24.0,
        })
        assert put_blocked.status_code == 400
        assert put_blocked.json()["error"] == "ENVIRONMENT_UPDATE_RESTRICTED"

    def test_26_api_get_by_id_and_test_jobs_compatibility(self, client):
        """GET /environment/{id} and /test-jobs/{id}/environment compatibility alias."""
        _create_sample_job("JOB-COMPAT", status=JobStatus.READY)

        # Test-jobs alias POST
        post_res = client.post("/test-jobs/JOB-COMPAT/environment", json={
            "temperature": 18.5,
            "humidity": 60.0,
            "atmospheric_pressure": 1015.0,
            "location": "Field Site",
            "operator": "Insp. Patel",
        })
        assert post_res.status_code == 201
        rec_id = post_res.json()["data"]["id"]

        # Global GET by ID
        get_res = client.get(f"/environment/{rec_id}")
        assert get_res.status_code == 200
        assert get_res.json()["data"]["id"] == rec_id

        # GET by ID not found
        get_nf = client.get("/environment/ENV-NONEXISTENT")
        assert get_nf.status_code == 404

        # Test-jobs alias GET latest & history
        alias_get = client.get("/test-jobs/JOB-COMPAT/environment")
        assert alias_get.status_code == 200
        assert alias_get.json()["data"]["temperature"] == 18.5

        alias_hist = client.get("/test-jobs/JOB-COMPAT/environment/history")
        assert alias_hist.status_code == 200
        assert alias_hist.json()["count"] == 1
