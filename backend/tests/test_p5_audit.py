"""
MetrIQ P5 Audit Trail & Traceability Unit Tests
===============================================
Person 5: Workflow + Evidence Engineer

Comprehensive test suite covering:
1. Audit log record creation, timestamping, and metadata structure.
2. Append-only immutability and prevention of modification/deletion.
3. Security: automatic redaction of sensitive credentials and secrets.
4. Seamless integration across all P5 modules:
   - Job State Machine (JOB_STATE_CHANGED)
   - Equipment & Test Standards (EQUIPMENT_CREATED, JOB_EQUIPMENT_ASSOCIATED)
   - Environment Monitoring (ENVIRONMENT_RECORDED, ENVIRONMENT_UPDATED)
   - Test Attempts & Retests (TEST_ATTEMPT_STARTED, TEST_ATTEMPT_COMPLETED, RETEST_REQUESTED)
   - Evidence Management (EVIDENCE_UPLOADED, EVIDENCE_DELETED_OR_ARCHIVED)
   - Review & Approval (REVIEW_SUBMITTED, REVIEW_APPROVED, REVIEW_REJECTED, REVIEW_RETURNED_FOR_CORRECTION)
5. Read-only REST API endpoints (/jobs/{id}/audit, /audit/{type}/{id}, /audit).
"""

import pytest
from fastapi.testclient import TestClient

from app.api.router import api_router
from app.attempts.models import AttemptStatus, Verdict
from app.attempts.repository import ATTEMPT_REPOSITORY
from app.attempts.service import ATTEMPT_SERVICE
from app.audit.models import AuditAction, AuditLog, EntityType
from app.audit.repository import AUDIT_REPOSITORY, AuditImmutabilityError
from app.audit.service import AUDIT_SERVICE, record_audit
from app.environment.repository import ENVIRONMENT_REPOSITORY
from app.environment.service import ENVIRONMENT_SERVICE
from app.equipment.models import EquipmentStatus
from app.equipment.repository import EQUIPMENT_REPOSITORY
from app.equipment.service import EQUIPMENT_SERVICE
from app.evidence.models import EvidenceStatus, EvidenceType
from app.evidence.repository import EVIDENCE_REPOSITORY
from app.evidence.service import EVIDENCE_SERVICE
from app.evidence.storage import FILE_STORAGE_SERVICE
from app.jobs.models import JobPriority, JobStatus, JobType, TestJob
from app.jobs.repository import TEST_JOB_REPOSITORY
from app.review.models import ReviewDecision, ReviewRole
from app.review.repository import REVIEW_REPOSITORY
from app.review.service import REVIEW_SERVICE
from app.workflow.service import WORKFLOW_SERVICE


@pytest.fixture(autouse=True)
def clean_repositories():
    """Ensures test isolation by resetting all repositories before and after each test."""
    AUDIT_REPOSITORY.clear()
    TEST_JOB_REPOSITORY.clear()
    EQUIPMENT_REPOSITORY.clear()
    ENVIRONMENT_REPOSITORY.clear()
    ATTEMPT_REPOSITORY.clear()
    EVIDENCE_REPOSITORY.clear()
    FILE_STORAGE_SERVICE.clear()
    REVIEW_REPOSITORY.clear()
    yield
    AUDIT_REPOSITORY.clear()
    TEST_JOB_REPOSITORY.clear()
    EQUIPMENT_REPOSITORY.clear()
    ENVIRONMENT_REPOSITORY.clear()
    ATTEMPT_REPOSITORY.clear()
    EVIDENCE_REPOSITORY.clear()
    FILE_STORAGE_SERVICE.clear()
    REVIEW_REPOSITORY.clear()


@pytest.fixture
def client():
    """FastAPI test client with the integrated API router."""
    from fastapi import FastAPI
    app = FastAPI(title="Test MetrIQ P5 Audit")
    app.include_router(api_router)
    return TestClient(app)


def _create_sample_job(
    job_id: str = "JOB-AUD-001",
    status: JobStatus = JobStatus.IN_PROGRESS,
    applicable_tests: list = None,
    assigned_inspector: str = "INSP-AUD-01",
) -> TestJob:
    """Helper to persist a test job for audit testing."""
    tests = applicable_tests if applicable_tests is not None else ["A.4.4", "A.4.7"]
    job = TestJob(
        job_id=job_id,
        instrument_id="INS-AUD-001",
        job_type=JobType.INITIAL_VERIFICATION,
        status=status,
        priority=JobPriority.NORMAL,
        assigned_inspector_id=assigned_inspector,
        applicable_tests=tests,
        test_execution_data={"completed": True},
        created_date="2026-09-19",
    )
    TEST_JOB_REPOSITORY.save(job)
    return job


# =============================================================================
# 1. Audit Log Creation & Structure Tests
# =============================================================================

class TestAuditLogCreation:
    __test__ = True

    def test_record_audit_basic(self):
        """Audit record accurately captures actor, action, entity, diffs, and timestamp."""
        log = AUDIT_SERVICE.record_audit(
            actor="INSP-CHIEF",
            action=AuditAction.JOB_CREATED,
            entity_type=EntityType.JOB,
            entity_id="JOB-100",
            old_value=None,
            new_value={"status": "DRAFT", "instrument_id": "INS-001"},
            metadata={"source": "WEB_PORTAL"},
            job_id="JOB-100",
        )

        assert log.id.startswith("AUD-")
        assert log.actor == "INSP-CHIEF"
        assert log.action == AuditAction.JOB_CREATED
        assert log.entity_type == EntityType.JOB
        assert log.entity_id == "JOB-100"
        assert log.old_value is None
        assert log.new_value == {"status": "DRAFT", "instrument_id": "INS-001"}
        assert log.metadata.get("source") == "WEB_PORTAL"
        assert log.job_id == "JOB-100"

        # Verify in repository
        retrieved = AUDIT_REPOSITORY.get(log.id)
        assert retrieved is not None
        assert retrieved.id == log.id

    def test_sensitive_data_redaction(self):
        """Sensitive credentials (passwords, tokens, api keys) are automatically sanitized."""
        log = AUDIT_SERVICE.record_audit(
            actor="SYSTEM",
            action=AuditAction.JOB_UPDATED,
            entity_type=EntityType.JOB,
            entity_id="JOB-SEC-01",
            new_value={
                "public_name": "Verified Balance",
                "auth_token": "secret_token_12345",
                "password": "supersecretpassword",
                "nested": {
                    "api_key": "api_xyz",
                    "safe_value": 42,
                },
            },
        )

        assert log.new_value["public_name"] == "Verified Balance"
        assert log.new_value["auth_token"] == "[REDACTED]"
        assert log.new_value["password"] == "[REDACTED]"
        assert log.new_value["nested"]["api_key"] == "[REDACTED]"
        assert log.new_value["nested"]["safe_value"] == 42


# =============================================================================
# 2. Immutability Tests
# =============================================================================

class TestAuditImmutability:
    __test__ = True

    def test_audit_records_cannot_be_updated_or_deleted(self):
        """Direct mutation or deletion on the audit repository raises AuditImmutabilityError."""
        log = AUDIT_SERVICE.record_audit(
            actor="SYSTEM",
            action=AuditAction.JOB_STATE_CHANGED,
            entity_type=EntityType.JOB,
            entity_id="JOB-IMM-01",
        )

        with pytest.raises(AuditImmutabilityError):
            AUDIT_REPOSITORY.update("some_field")

        with pytest.raises(AuditImmutabilityError):
            AUDIT_REPOSITORY.delete(log.id)

        # Duplicate ID rejection
        with pytest.raises(AuditImmutabilityError):
            AUDIT_REPOSITORY.record(log)


# =============================================================================
# 3. Integration Tests across P5 Modules
# =============================================================================

class TestAuditModuleIntegrations:
    __test__ = True

    def test_workflow_state_transition_generates_audit_event(self):
        """Job state machine transition emits JOB_STATE_CHANGED audit event with before/after state."""
        job = _create_sample_job("JOB-TR-AUD", status=JobStatus.DRAFT)

        WORKFLOW_SERVICE.transition_job(
            job_id="JOB-TR-AUD",
            target_state=JobStatus.READY,
            actor="OPERATOR-ALICE",
            reason="All equipment and standards prepared",
        )

        logs = AUDIT_SERVICE.get_job_audit_trail("JOB-TR-AUD")
        assert len(logs) >= 1

        state_log = next(l for l in logs if l.action == AuditAction.JOB_STATE_CHANGED)
        assert state_log.actor == "OPERATOR-ALICE"
        assert state_log.old_value == {"status": "DRAFT"}
        assert state_log.new_value == {"status": "READY"}
        assert "All equipment" in state_log.metadata.get("reason", "")

    def test_equipment_module_generates_audit_events(self):
        """Registering and associating equipment generates EQUIPMENT_CREATED and JOB_EQUIPMENT_ASSOCIATED."""
        job = _create_sample_job("JOB-EQ-AUD", status=JobStatus.DRAFT)

        eq = EQUIPMENT_SERVICE.create_equipment({
            "name": "Class F1 Weight Set",
            "type": "MASS_STANDARD",
            "serial_number": "SN-F1-999",
            "manufacturer": "NPL India",
            "model": "F1-500",
            "calibration_certificate": "CAL-NPL-2026-001",
            "calibration_date": "2026-01-01",
            "calibration_due_date": "2027-01-01",
            "status": "ACTIVE",
        })

        EQUIPMENT_SERVICE.associate_equipment_with_job("JOB-EQ-AUD", eq.id)

        eq_logs = AUDIT_SERVICE.get_entity_audit_trail(EntityType.EQUIPMENT, eq.id)
        actions = [l.action for l in eq_logs]
        assert AuditAction.EQUIPMENT_CREATED in actions
        assert AuditAction.JOB_EQUIPMENT_ASSOCIATED in actions

    def test_environment_module_generates_audit_events(self):
        """Recording environment conditions generates ENVIRONMENT_RECORDED audit entry."""
        job = _create_sample_job("JOB-ENV-AUD", status=JobStatus.IN_PROGRESS)

        rec = ENVIRONMENT_SERVICE.record_environment(
            job_id="JOB-ENV-AUD",
            data={
                "temperature": 20.5,
                "humidity": 55.0,
                "atmospheric_pressure": 1013.25,
                "location": "Verification Bench 1",
                "operator": "INSP-LEGAL",
            },
        )

        env_logs = AUDIT_SERVICE.get_entity_audit_trail(EntityType.ENVIRONMENT, rec.id)
        assert len(env_logs) == 1
        assert env_logs[0].action == AuditAction.ENVIRONMENT_RECORDED
        assert env_logs[0].new_value["temperature"] == 20.5

    def test_attempt_module_generates_audit_events(self):
        """Starting attempt, completing attempt, and requesting retest generate respective audit events."""
        job = _create_sample_job("JOB-ATT-AUD", status=JobStatus.IN_PROGRESS, applicable_tests=["A.4.4"])

        # 1. Start Attempt
        att = ATTEMPT_SERVICE.start_attempt(
            job_id="JOB-ATT-AUD",
            test_id="A.4.4",
            operator="INSP-01",
        )

        # 2. Complete Attempt (FAIL)
        ATTEMPT_SERVICE.complete_attempt(
            attempt_id=att.id,
            result=Verdict.FAIL,
            comments="Eccentricity discrepancy at 1/3 Max",
            completed_by="INSP-01",
        )

        # 3. Request Retest
        retest_req = ATTEMPT_SERVICE.request_retest(
            job_id="JOB-ATT-AUD",
            test_id="A.4.4",
            attempt_id=att.id,
            reason="Sensor realignment needed",
            requested_by="INSP-01",
        )

        job_logs = AUDIT_SERVICE.get_job_audit_trail("JOB-ATT-AUD")
        actions = [l.action for l in job_logs]

        assert AuditAction.TEST_ATTEMPT_STARTED in actions
        assert AuditAction.TEST_ATTEMPT_COMPLETED in actions
        assert AuditAction.RETEST_REQUESTED in actions

    def test_evidence_module_generates_audit_events(self):
        """Evidence upload and archiving emit EVIDENCE_UPLOADED and EVIDENCE_DELETED_OR_ARCHIVED."""
        job = _create_sample_job("JOB-EVD-AUD", status=JobStatus.IN_PROGRESS)

        ev = EVIDENCE_SERVICE.upload_evidence(
            job_id="JOB-EVD-AUD",
            file_name="seal_verification.png",
            content=b"Digital seal verification photo bytes",
            evidence_type=EvidenceType.PHOTO,
            uploaded_by="INSP-01",
        )

        EVIDENCE_SERVICE.delete_evidence(
            evidence_id=ev.id,
            user_id="INSP-SUPERVISOR",
            reason="Replaced with higher resolution capture",
        )

        ev_logs = AUDIT_SERVICE.get_entity_audit_trail(EntityType.EVIDENCE, ev.id)
        assert len(ev_logs) == 2
        assert ev_logs[0].action == AuditAction.EVIDENCE_UPLOADED
        assert ev_logs[1].action == AuditAction.EVIDENCE_DELETED_OR_ARCHIVED
        assert ev_logs[1].old_value["status"] == "ACTIVE"
        assert ev_logs[1].new_value["status"] == "ARCHIVED"

    def test_review_module_generates_audit_events(self):
        """Review submission and supervisory approval emit REVIEW_SUBMITTED and REVIEW_APPROVED."""
        job = _create_sample_job("JOB-REV-AUD", status=JobStatus.IN_PROGRESS, assigned_inspector="INSP-OP-1")

        # 1. Submit for review
        review, _ = REVIEW_SERVICE.submit_for_review(
            job_id="JOB-REV-AUD",
            reviewer="CONTROLLER-REGIONAL",
            comments="Testing completed successfully",
            submitted_by="INSP-OP-1",
        )

        # 2. Approve review
        REVIEW_SERVICE.execute_review(
            job_id="JOB-REV-AUD",
            decision=ReviewDecision.APPROVE,
            comments="Stamping certified according to Legal Metrology Act",
            reviewer="CONTROLLER-REGIONAL",
            role=ReviewRole.CONTROLLER,
        )

        rev_logs = AUDIT_SERVICE.get_entity_audit_trail(EntityType.REVIEW, review.id)
        assert len(rev_logs) == 2
        assert rev_logs[0].action == AuditAction.REVIEW_SUBMITTED
        assert rev_logs[1].action == AuditAction.REVIEW_APPROVED
        assert rev_logs[1].new_value["decision"] == "APPROVE"


# =============================================================================
# 4. REST API Endpoints Tests
# =============================================================================

class TestAuditAPIEndpoints:
    __test__ = True

    def test_api_get_job_audit_trail(self, client):
        """GET /jobs/{id}/audit returns chronological audit trail for a job."""
        job = _create_sample_job("JOB-API-AUD-01", status=JobStatus.DRAFT)
        WORKFLOW_SERVICE.transition_job("JOB-API-AUD-01", JobStatus.READY, actor="OP-01")

        response = client.get("/jobs/JOB-API-AUD-01/audit")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job_id"] == "JOB-API-AUD-01"
        assert data["count"] >= 1
        assert data["data"][0]["action"] == "JOB_STATE_CHANGED"

    def test_api_get_entity_audit_trail(self, client):
        """GET /audit/{type}/{id} returns audit trail for a specific entity."""
        AUDIT_SERVICE.record_audit(
            actor="INSP-01",
            action=AuditAction.EQUIPMENT_STATUS_CHANGED,
            entity_type=EntityType.EQUIPMENT,
            entity_id="EQ-TEST-99",
            old_value={"status": "ACTIVE"},
            new_value={"status": "OUT_OF_SERVICE"},
        )

        response = client.get("/audit/EQUIPMENT/EQ-TEST-99")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["entity_type"] == "EQUIPMENT"
        assert data["entity_id"] == "EQ-TEST-99"
        assert len(data["data"]) == 1

    def test_api_query_audit_with_filters(self, client):
        """GET /audit supports filtering by action and actor."""
        AUDIT_SERVICE.record_audit("USER-A", AuditAction.JOB_CREATED, EntityType.JOB, "J1")
        AUDIT_SERVICE.record_audit("USER-B", AuditAction.JOB_STATE_CHANGED, EntityType.JOB, "J2")

        # Filter by actor
        r_actor = client.get("/audit?actor=USER-A")
        assert r_actor.status_code == 200
        assert r_actor.json()["count"] == 1
        assert r_actor.json()["data"][0]["actor"] == "USER-A"

        # Filter by action
        r_action = client.get("/audit?action=JOB_STATE_CHANGED")
        assert r_action.status_code == 200
        assert r_action.json()["count"] == 1
        assert r_action.json()["data"][0]["action"] == "JOB_STATE_CHANGED"

    def test_api_mutations_are_not_allowed(self, client):
        """Audit endpoints do not expose POST or DELETE routes (405 Method Not Allowed)."""
        r_post = client.post("/jobs/JOB-API-AUD-01/audit", json={})
        assert r_post.status_code == 405

        r_del = client.delete("/jobs/JOB-API-AUD-01/audit")
        assert r_del.status_code == 405
