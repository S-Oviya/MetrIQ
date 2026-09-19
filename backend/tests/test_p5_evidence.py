"""
MetrIQ P5 Evidence & Attachment Management Unit Tests
=====================================================
Person 5: Workflow + Evidence Engineer

Comprehensive test suite covering:
1. Storage layer: Path traversal rejection, safe filename sanitization, SHA-256 computation.
2. Evidence model & repository: Multi-level indexing (job, test, attempt), retention status.
3. Validation rules: Nonexistent job, test mismatch, attempt mismatch, empty file, oversized file, invalid extensions.
4. Workflow stage rules: Upload permitted in active stages, rejected in terminal stages; deletion locked in APPROVED.
5. REST API endpoints: Base64 upload, metadata retrieval, filtering, raw download, soft-delete, security checks.
6. Multi-attempt traceability: Linking evidence to specific retest attempts.
"""

import base64
import hashlib
import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from app.api.router import api_router
from app.attempts.models import AttemptStatus, TestAttempt, Verdict
from app.attempts.repository import ATTEMPT_REPOSITORY
from app.evidence.models import Evidence, EvidenceStatus, EvidenceType
from app.evidence.repository import EVIDENCE_REPOSITORY, EvidenceRepository
from app.evidence.service import (
    EVIDENCE_SERVICE,
    EvidenceNotFoundError,
    EvidenceSecurityError,
    EvidenceService,
    EvidenceValidationError,
    EvidenceWorkflowStateError,
)
from app.evidence.storage import (
    FILE_STORAGE_SERVICE,
    FileStorageService,
    StorageSecurityError,
)
from app.jobs.models import JobPriority, JobStatus, JobType, TestJob
from app.jobs.repository import TEST_JOB_REPOSITORY
from app.workflow.service import JobNotFoundError


@pytest.fixture(autouse=True)
def clean_repositories():
    """Ensures test isolation by resetting storage and repositories before/after each test."""
    EVIDENCE_REPOSITORY.clear()
    FILE_STORAGE_SERVICE.clear()
    TEST_JOB_REPOSITORY.clear()
    ATTEMPT_REPOSITORY.clear()
    yield
    EVIDENCE_REPOSITORY.clear()
    FILE_STORAGE_SERVICE.clear()
    TEST_JOB_REPOSITORY.clear()
    ATTEMPT_REPOSITORY.clear()


@pytest.fixture
def client():
    """FastAPI test client with the integrated API router."""
    from fastapi import FastAPI
    app = FastAPI(title="Test MetrIQ P5 Evidence")
    app.include_router(api_router)
    return TestClient(app)


def _create_sample_job(
    job_id: str = "JOB-EV-001",
    status: JobStatus = JobStatus.IN_PROGRESS,
    applicable_tests: list = None,
) -> TestJob:
    """Helper to persist a test job with specified status and applicable tests."""
    tests = applicable_tests if applicable_tests is not None else ["A.4.4", "A.4.7", "WEIGHING_PERFORMANCE"]
    job = TestJob(
        job_id=job_id,
        instrument_id="INS-EV-001",
        job_type=JobType.INITIAL_VERIFICATION,
        status=status,
        priority=JobPriority.NORMAL,
        assigned_inspector_id="OP-LEGAL-01",
        applicable_tests=tests,
        created_date="2026-09-19",
    )
    TEST_JOB_REPOSITORY.save(job)
    return job


def _create_sample_attempt(
    job_id: str = "JOB-EV-001",
    test_id: str = "A.4.4",
    attempt_number: int = 1,
    status: AttemptStatus = AttemptStatus.COMPLETED,
    verdict: Verdict = Verdict.FAIL,
) -> TestAttempt:
    """Helper to persist a test attempt in the repository."""
    attempt_id = f"ATT-{job_id}-{test_id}-{attempt_number}"
    attempt = TestAttempt(
        id=attempt_id,
        job_id=job_id,
        test_id=test_id,
        attempt_number=attempt_number,
        operator="OP-LEGAL-01",
        started_at="2026-09-19T10:30:00Z",
        status=status,
        result=verdict,
        completed_at="2026-09-19T10:45:00Z",
    )
    ATTEMPT_REPOSITORY.save(attempt)
    return attempt


# =============================================================================
# 1. Storage Layer Unit Tests
# =============================================================================

class TestFileStorageService:
    __test__ = True

    def test_sanitize_filename(self):
        """Sanitizer removes path navigation, null bytes, and dangerous characters."""
        assert FileStorageService.sanitize_filename("valid_photo.jpg") == "valid_photo.jpg"
        assert FileStorageService.sanitize_filename("../../evil.exe") == "evil.exe"
        assert FileStorageService.sanitize_filename("dir/subdir\\file.png") == "file.png"
        assert FileStorageService.sanitize_filename("bad\x00name$.pdf") == "badname_.pdf"
        assert FileStorageService.sanitize_filename(".hidden.jpg") == "hidden.jpg"
        assert FileStorageService.sanitize_filename("") == "attachment.bin"

    def test_path_traversal_detection(self):
        """Storage service strictly prohibits directory traversal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FileStorageService(base_dir=tmpdir)
            with pytest.raises(StorageSecurityError):
                storage._resolve_safe_path("../outside.txt")
            with pytest.raises(StorageSecurityError):
                storage._resolve_safe_path("JOB-01/../../etc/passwd")

    def test_save_and_read_file(self):
        """Storage correctly writes and reads file content with verified checksum."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FileStorageService(base_dir=tmpdir)
            data = b"Statutory verification seal photo data"
            expected_hash = hashlib.sha256(data).hexdigest()

            rel_path, size, checksum = storage.save_file(
                job_id="JOB-100",
                evidence_id="EV-100",
                filename="seal.jpg",
                content=data,
            )

            assert checksum == expected_hash
            assert size == len(data)
            assert "JOB-100" in rel_path
            assert "seal.jpg" in rel_path
            assert not os.path.isabs(rel_path)

            read_data = storage.read_file(rel_path)
            assert read_data == data

    def test_delete_file(self):
        """Storage deletes existing file and returns boolean status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FileStorageService(base_dir=tmpdir)
            rel_path, _, _ = storage.save_file("JOB-100", "EV-101", "test.pdf", b"document")
            assert storage.file_exists(rel_path) is True
            assert storage.delete_file(rel_path) is True
            assert storage.file_exists(rel_path) is False
            assert storage.delete_file(rel_path) is False


# =============================================================================
# 2. Evidence Model & Repository Tests
# =============================================================================

class TestEvidenceRepository:
    __test__ = True

    def test_evidence_model_properties_and_dict(self):
        """Evidence dataclass provides aliases and dictionary serialization."""
        ev = Evidence(
            id="EV-001",
            job_id="JOB-001",
            type=EvidenceType.PHOTO,
            file_name="seal.png",
            storage_reference="JOB-001/EV-001_seal.png",
            mime_type="image/png",
            file_size=1024,
            checksum="abc123hash",
            uploaded_by="OP-01",
            test_id="A.4.4",
            attempt_id="ATT-001",
            description="Calibration seal photo",
        )
        assert ev.hash == "abc123hash"
        assert ev.file_path == "JOB-001/EV-001_seal.png"
        assert ev.evidence_id == "EV-001"

        d = ev.to_dict()
        assert d["id"] == "EV-001"
        assert d["type"] == "PHOTO"
        assert d["test_id"] == "A.4.4"
        assert d["attempt_id"] == "ATT-001"
        assert d["checksum"] == "abc123hash"

    def test_repository_indexing(self):
        """Repository indexes by job, test, and attempt correctly."""
        repo = EvidenceRepository()
        ev1 = Evidence(
            id="EV-1", job_id="JOB-A", type=EvidenceType.PHOTO, file_name="p1.jpg",
            storage_reference="JOB-A/EV-1_p1.jpg", mime_type="image/jpeg",
            file_size=100, checksum="h1", uploaded_by="OP-01", test_id="A.4.4", attempt_id="ATT-1",
        )
        ev2 = Evidence(
            id="EV-2", job_id="JOB-A", type=EvidenceType.TEST_OBSERVATION, file_name="obs.pdf",
            storage_reference="JOB-A/EV-2_obs.pdf", mime_type="application/pdf",
            file_size=200, checksum="h2", uploaded_by="OP-01", test_id="A.4.4", attempt_id="ATT-2",
        )
        ev3 = Evidence(
            id="EV-3", job_id="JOB-B", type=EvidenceType.CALIBRATION_CERTIFICATE, file_name="cert.pdf",
            storage_reference="JOB-B/EV-3_cert.pdf", mime_type="application/pdf",
            file_size=300, checksum="h3", uploaded_by="OP-02",
        )

        repo.save(ev1)
        repo.save(ev2)
        repo.save(ev3)

        assert len(repo.get_by_job("JOB-A")) == 2
        assert len(repo.get_by_job("JOB-B")) == 1
        assert len(repo.get_by_test("JOB-A", "A.4.4")) == 2
        assert len(repo.get_by_attempt("ATT-1")) == 1
        assert repo.get_by_attempt("ATT-1")[0].id == "EV-1"
        assert len(repo.get_by_attempt("ATT-2")) == 1
        assert repo.get_by_attempt("ATT-2")[0].id == "EV-2"


# =============================================================================
# 3. Evidence Service Validation & Business Rules
# =============================================================================

class TestEvidenceServiceValidation:
    __test__ = True

    def test_upload_missing_job_fails(self):
        """Uploading evidence for a non-existent job raises JobNotFoundError."""
        with pytest.raises(JobNotFoundError):
            EVIDENCE_SERVICE.upload_evidence(
                job_id="JOB-DOES-NOT-EXIST",
                file_name="photo.jpg",
                content=b"test data",
                uploaded_by="OP-01",
            )

    def test_upload_invalid_test_id_fails(self):
        """Uploading evidence for a test not part of the job raises TestNotFoundError."""
        _create_sample_job("JOB-EV-VAL-1", applicable_tests=["A.4.4"])
        with pytest.raises(Exception) as exc_info:
            EVIDENCE_SERVICE.upload_evidence(
                job_id="JOB-EV-VAL-1",
                file_name="photo.jpg",
                content=b"test data",
                uploaded_by="OP-01",
                test_id="INVALID_TEST",
            )
        assert "applicable test" in str(exc_info.value).lower() or "not found" in str(exc_info.value).lower()

    def test_upload_invalid_attempt_id_fails(self):
        """Uploading evidence for a non-existent attempt raises AttemptNotFoundError."""
        _create_sample_job("JOB-EV-VAL-2", applicable_tests=["A.4.4"])
        with pytest.raises(Exception):
            EVIDENCE_SERVICE.upload_evidence(
                job_id="JOB-EV-VAL-2",
                file_name="photo.jpg",
                content=b"test data",
                uploaded_by="OP-01",
                test_id="A.4.4",
                attempt_id="ATT-DOES-NOT-EXIST",
            )

    def test_upload_attempt_mismatched_test_fails(self):
        """Uploading evidence when attempt belongs to a different test raises EvidenceValidationError."""
        _create_sample_job("JOB-EV-VAL-3", applicable_tests=["A.4.4", "A.4.7"])
        _create_sample_attempt(job_id="JOB-EV-VAL-3", test_id="A.4.4", attempt_number=1)

        with pytest.raises(EvidenceValidationError) as exc_info:
            EVIDENCE_SERVICE.upload_evidence(
                job_id="JOB-EV-VAL-3",
                file_name="photo.jpg",
                content=b"test data",
                uploaded_by="OP-01",
                test_id="A.4.7",  # Attempt was created for A.4.4
                attempt_id="ATT-JOB-EV-VAL-3-A.4.4-1",
            )
        assert "belongs to test" in str(exc_info.value).lower()

    def test_upload_empty_file_fails(self):
        """Uploading empty file raises EvidenceValidationError."""
        _create_sample_job("JOB-EV-VAL-4")
        with pytest.raises(EvidenceValidationError) as exc_info:
            EVIDENCE_SERVICE.upload_evidence(
                job_id="JOB-EV-VAL-4",
                file_name="empty.jpg",
                content=b"",
                uploaded_by="OP-01",
            )
        assert "empty" in str(exc_info.value).lower()

    def test_upload_unsupported_extension_fails(self):
        """Uploading dangerous or unsupported file types (.exe, .sh) raises EvidenceValidationError."""
        _create_sample_job("JOB-EV-VAL-5")
        with pytest.raises(EvidenceValidationError) as exc_info:
            EVIDENCE_SERVICE.upload_evidence(
                job_id="JOB-EV-VAL-5",
                file_name="malware.exe",
                content=b"MZ\x90binary",
                uploaded_by="OP-01",
            )
        assert "not supported" in str(exc_info.value).lower()

    def test_upload_oversized_file_fails(self):
        """Uploading file exceeding max size limit raises EvidenceValidationError."""
        _create_sample_job("JOB-EV-VAL-6")
        huge_data = b"X" * (50 * 1024 * 1024 + 1)  # 50MB + 1 byte
        with pytest.raises(EvidenceValidationError) as exc_info:
            EVIDENCE_SERVICE.upload_evidence(
                job_id="JOB-EV-VAL-6",
                file_name="large.jpg",
                content=huge_data,
                uploaded_by="OP-01",
            )
        assert "exceeds maximum permitted limit" in str(exc_info.value).lower()


# =============================================================================
# 4. Workflow Stage & Lifecycle Rules
# =============================================================================

class TestEvidenceWorkflowRules:
    __test__ = True

    def test_upload_prohibited_in_terminal_state(self):
        """Uploading evidence when job is in REPORT_GENERATED raises EvidenceWorkflowStateError."""
        _create_sample_job("JOB-EV-WF-1", status=JobStatus.REPORT_GENERATED)
        with pytest.raises(EvidenceWorkflowStateError) as exc_info:
            EVIDENCE_SERVICE.upload_evidence(
                job_id="JOB-EV-WF-1",
                file_name="photo.jpg",
                content=b"statutory seal",
                uploaded_by="OP-01",
            )
        assert "cannot upload evidence" in str(exc_info.value).lower()

    def test_upload_permitted_in_active_stages(self):
        """Evidence upload is permitted in DRAFT, READY, IN_PROGRESS, RETEST_REQUIRED, REVIEW."""
        stages = [
            JobStatus.DRAFT,
            JobStatus.READY,
            JobStatus.IN_PROGRESS,
            JobStatus.RETEST_REQUIRED,
            JobStatus.REVIEW,
        ]
        for idx, stage in enumerate(stages):
            jid = f"JOB-EV-STAGE-{idx}"
            _create_sample_job(jid, status=stage)
            ev = EVIDENCE_SERVICE.upload_evidence(
                job_id=jid,
                file_name=f"seal_{idx}.jpg",
                content=b"test photo bytes",
                uploaded_by="OP-01",
            )
            assert ev.id.startswith("EVD-")
            assert ev.job_id == jid
            assert ev.status == EvidenceStatus.ACTIVE

    def test_deletion_prohibited_in_approved_job(self):
        """Evidence deletion is permanently locked once job reaches APPROVED or beyond."""
        job = _create_sample_job("JOB-EV-LOCK-1", status=JobStatus.IN_PROGRESS)
        ev = EVIDENCE_SERVICE.upload_evidence(
            job_id="JOB-EV-LOCK-1",
            file_name="seal.jpg",
            content=b"seal content",
            uploaded_by="OP-01",
        )

        # Transition to APPROVED
        job.status = JobStatus.APPROVED
        TEST_JOB_REPOSITORY.save(job)

        with pytest.raises(EvidenceWorkflowStateError) as exc_info:
            EVIDENCE_SERVICE.delete_evidence(ev.id, user_id="INSPECTOR-01", reason="Audit cleanup")
        assert "cannot delete evidence" in str(exc_info.value).lower()
        assert "approved" in str(exc_info.value).lower()

    def test_soft_delete_archives_evidence_in_active_job(self):
        """In active jobs, delete_evidence sets status to ARCHIVED with reason and user audit."""
        _create_sample_job("JOB-EV-DEL-1", status=JobStatus.IN_PROGRESS)
        ev = EVIDENCE_SERVICE.upload_evidence(
            job_id="JOB-EV-DEL-1",
            file_name="chart.pdf",
            content=b"old calibration chart",
            uploaded_by="OP-01",
        )
        archived = EVIDENCE_SERVICE.delete_evidence(
            ev.id,
            user_id="OP-01",
            reason="Superseded by clearer observation scan",
        )
        assert archived.status == EvidenceStatus.ARCHIVED
        assert archived.metadata.get("archived_by") == "OP-01"
        assert archived.metadata.get("archive_reason") == "Superseded by clearer observation scan"

        # By default, list excludes archived
        active_list = EVIDENCE_SERVICE.list_job_evidence("JOB-EV-DEL-1", include_archived=False)
        assert len(active_list) == 0

        # When requested, archived records are visible
        all_list = EVIDENCE_SERVICE.list_job_evidence("JOB-EV-DEL-1", include_archived=True)
        assert len(all_list) == 1
        assert all_list[0].id == ev.id


# =============================================================================
# 5. REST API Endpoints Tests
# =============================================================================

class TestEvidenceAPIEndpoints:
    __test__ = True

    def test_api_upload_evidence_base64_json(self, client):
        """POST /jobs/{id}/evidence accepts JSON payload with base64 content and metadata."""
        _create_sample_job("JOB-API-01", applicable_tests=["A.4.4"])
        raw_bytes = b"Digital photo of verification scale pan"
        b64_str = base64.b64encode(raw_bytes).decode("utf-8")

        payload = {
            "file_name": "pan_photo.jpg",
            "content_base64": b64_str,
            "type": "PHOTO",
            "test_id": "A.4.4",
            "description": "Leveling and pan verification photo",
            "uploaded_by": "OP-LEGAL-01",
        }

        response = client.post("/jobs/JOB-API-01/evidence", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        evidence_data = data["data"]
        assert evidence_data["job_id"] == "JOB-API-01"
        assert evidence_data["file_name"] == "pan_photo.jpg"
        assert evidence_data["type"] == "PHOTO"
        assert evidence_data["checksum"] == hashlib.sha256(raw_bytes).hexdigest()
        assert evidence_data["file_size"] == len(raw_bytes)
        assert evidence_data["test_id"] == "A.4.4"

    def test_api_list_and_filter_evidence(self, client):
        """GET /jobs/{id}/evidence lists job evidence with optional filters."""
        _create_sample_job("JOB-API-02", applicable_tests=["A.4.4", "A.4.7"])
        _create_sample_attempt("JOB-API-02", "A.4.4", 1)

        # Upload photo for test A.4.4
        client.post(
            "/jobs/JOB-API-02/evidence",
            json={
                "file_name": "photo1.png",
                "content": "photo content 1",
                "type": "PHOTO",
                "test_id": "A.4.4",
                "attempt_id": "ATT-JOB-API-02-A.4.4-1",
            },
        )
        # Upload certificate for general job
        client.post(
            "/jobs/JOB-API-02/evidence",
            json={
                "file_name": "weights_cert.pdf",
                "content": "certificate pdf data",
                "type": "CALIBRATION_CERTIFICATE",
            },
        )

        # 1. List all for job
        r_all = client.get("/jobs/JOB-API-02/evidence")
        assert r_all.status_code == 200
        assert r_all.json()["count"] == 2

        # 2. Filter by test_id
        r_test = client.get("/jobs/JOB-API-02/evidence?test_id=A.4.4")
        assert r_test.status_code == 200
        assert r_test.json()["count"] == 1
        assert r_test.json()["data"][0]["type"] == "PHOTO"

        # 3. Filter by type
        r_type = client.get("/jobs/JOB-API-02/evidence?evidence_type=CALIBRATION_CERTIFICATE")
        assert r_type.status_code == 200
        assert r_type.json()["count"] == 1
        assert r_type.json()["data"][0]["file_name"] == "weights_cert.pdf"

        # 4. Filter by test endpoint directly
        r_test_ep = client.get("/jobs/JOB-API-02/tests/A.4.4/evidence")
        assert r_test_ep.status_code == 200
        assert r_test_ep.json()["count"] == 1

    def test_api_download_evidence(self, client):
        """GET /evidence/{id}/download serves raw file stream with correct headers."""
        _create_sample_job("JOB-API-03")
        content = b"Exact test report sheet PDF data bytes \x01\x02\x03"
        b64 = base64.b64encode(content).decode("utf-8")

        r_up = client.post(
            "/jobs/JOB-API-03/evidence",
            json={
                "file_name": "observation_sheet.pdf",
                "content_base64": b64,
                "type": "TEST_OBSERVATION",
            },
        )
        ev_id = r_up.json()["data"]["id"]

        # Download direct
        r_down = client.get(f"/evidence/{ev_id}/download")
        assert r_down.status_code == 200
        assert r_down.content == content
        assert "application/pdf" in r_down.headers.get("content-type", "").lower()
        assert 'filename="observation_sheet.pdf"' in r_down.headers.get("content-disposition", "")

        # Download with verified job_id check
        r_job_down = client.get(f"/jobs/JOB-API-03/evidence/{ev_id}/download")
        assert r_job_down.status_code == 200
        assert r_job_down.content == content

        # Cross-job download attempt is rejected (403 Forbidden)
        r_wrong_job = client.get(f"/jobs/JOB-OTHER-999/evidence/{ev_id}/download")
        assert r_wrong_job.status_code == 403

    def test_api_delete_evidence(self, client):
        """DELETE /jobs/{id}/evidence/{id} soft-deletes the record."""
        _create_sample_job("JOB-API-04")
        r_up = client.post(
            "/jobs/JOB-API-04/evidence",
            json={
                "file_name": "temp_note.txt",
                "content": "preliminary notes",
                "type": "OTHER",
            },
        )
        ev_id = r_up.json()["data"]["id"]

        # Delete
        r_del = client.delete(
            f"/jobs/JOB-API-04/evidence/{ev_id}?reason=Preliminary+superseded&user_id=OP-01"
        )
        assert r_del.status_code == 200
        assert r_del.json()["data"]["status"] == "ARCHIVED"

        # List should exclude it
        r_list = client.get("/jobs/JOB-API-04/evidence")
        assert r_list.json()["count"] == 0

        # List with include_archived=true should include it
        r_list_archived = client.get("/jobs/JOB-API-04/evidence?include_archived=true")
        assert r_list_archived.json()["count"] == 1


# =============================================================================
# 6. Retest Traceability Integration
# =============================================================================

class TestEvidenceRetestTraceability:
    __test__ = True

    def test_evidence_traceable_to_specific_retest_attempts(self, client):
        """
        Validates statutory traceability:
        Attempt 1 (FAIL) has photo 1 attached.
        Retest Attempt 2 (PASS) has photo 2 attached.
        Both evidence records are preserved and individually traceable.
        """
        job = _create_sample_job("JOB-RETEST-EV", applicable_tests=["A.4.4"])

        # Attempt 1
        att1 = _create_sample_attempt("JOB-RETEST-EV", "A.4.4", 1, status=AttemptStatus.COMPLETED, verdict=Verdict.FAIL)
        # Attempt 2
        att2 = _create_sample_attempt("JOB-RETEST-EV", "A.4.4", 2, status=AttemptStatus.COMPLETED, verdict=Verdict.PASS)

        # Upload evidence for Attempt 1
        ev1 = EVIDENCE_SERVICE.upload_evidence(
            job_id="JOB-RETEST-EV",
            file_name="attempt1_fail_seal.jpg",
            content=b"Damaged seal photo",
            type="PHOTO",
            test_id="A.4.4",
            attempt_id=att1.id,
            description="Visual defect found on lead seal",
            uploaded_by="OP-01",
        )

        # Upload evidence for Attempt 2
        ev2 = EVIDENCE_SERVICE.upload_evidence(
            job_id="JOB-RETEST-EV",
            file_name="attempt2_pass_seal.jpg",
            content=b"Re-stamped legal seal photo",
            type="PHOTO",
            test_id="A.4.4",
            attempt_id=att2.id,
            description="Re-stamped verification seal after servicing",
            uploaded_by="OP-01",
        )

        # Query by attempt
        att1_ev = EVIDENCE_SERVICE.list_job_evidence("JOB-RETEST-EV", attempt_id=att1.id)
        assert len(att1_ev) == 1
        assert att1_ev[0].id == ev1.id
        assert att1_ev[0].file_name == "attempt1_fail_seal.jpg"

        att2_ev = EVIDENCE_SERVICE.list_job_evidence("JOB-RETEST-EV", attempt_id=att2.id)
        assert len(att2_ev) == 1
        assert att2_ev[0].id == ev2.id
        assert att2_ev[0].file_name == "attempt2_pass_seal.jpg"

        # Query by test returns both
        test_ev = EVIDENCE_SERVICE.list_test_evidence("JOB-RETEST-EV", "A.4.4")
        assert len(test_ev) == 2
        evidence_file_names = {e.file_name for e in test_ev}
        assert "attempt1_fail_seal.jpg" in evidence_file_names
        assert "attempt2_pass_seal.jpg" in evidence_file_names
