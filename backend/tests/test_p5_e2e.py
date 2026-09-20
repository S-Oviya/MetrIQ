"""
MetrIQ P5 End-to-End Integration & Verification Test Suite
==========================================================
Person 5: Workflow + Evidence Engineer

Comprehensive end-to-end testing covering:
1. Realistic 17-step full lifecycle integration test:
   Job Creation -> Workflow -> Equipment & Standards -> Environment Monitoring ->
   Attempt 1 (FAIL) -> Retest Request -> Workflow State Management ->
   Attempt 2 (PASS) -> Evidence Upload -> Review Submission ->
   Supervisory Approval (Four-Eyes Enforcement) -> Complete Audit Trail Verification.
2. Negative end-to-end tests:
   - Illegal state transition rejection
   - Expired equipment association rejection
   - Invalid retest request rejection
   - Anti-self-approval / Four-Eyes authorization rejection
   - Invalid evidence relationship and cross-job containment rejection
3. Full REST API End-to-End lifecycle validation.
"""

from datetime import date, timedelta
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.router import api_router
from app.attempts.models import AttemptStatus, Verdict
from app.attempts.repository import ATTEMPT_REPOSITORY
from app.attempts.service import (
    ATTEMPT_SERVICE,
    AttemptNotFoundError,
    AttemptValidationError,
)
from app.audit.models import AuditAction, EntityType
from app.audit.repository import AUDIT_REPOSITORY
from app.audit.service import AUDIT_SERVICE
from app.environment.repository import ENVIRONMENT_REPOSITORY
from app.environment.service import ENVIRONMENT_SERVICE
from app.equipment.models import EquipmentStatus
from app.equipment.repository import EQUIPMENT_REPOSITORY
from app.equipment.service import (
    CalibrationExpiredError,
    EQUIPMENT_SERVICE,
)
from app.evidence.models import EvidenceStatus, EvidenceType
from app.evidence.repository import EVIDENCE_REPOSITORY
from app.evidence.service import (
    EVIDENCE_SERVICE,
    EvidenceSecurityError,
    EvidenceValidationError,
)
from app.evidence.storage import FILE_STORAGE_SERVICE
from app.jobs.models import JobPriority, JobStatus, JobType, TestJob
from app.jobs.repository import TEST_JOB_REPOSITORY
from app.review.models import ReviewDecision, ReviewRole, ReviewStatus
from app.review.repository import REVIEW_REPOSITORY
from app.review.service import (
    REVIEW_SERVICE,
    UnauthorizedReviewerError,
)
from app.workflow.service import WORKFLOW_SERVICE
from app.workflow.state_machine import WorkflowStateTransitionError


@pytest.fixture(autouse=True)
def reset_all_repositories():
    """Resets all P5 in-memory data structures before and after each test for strict isolation."""
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
    """FastAPI test client with the unified API router."""
    app = FastAPI(title="Test MetrIQ P5 E2E")
    app.include_router(api_router)
    return TestClient(app)


# =============================================================================
# 1. Realistic 17-Step End-to-End Lifecycle Integration Test
# =============================================================================

class TestP5EndToEndLifecycle:
    __test__ = True

    def test_complete_p5_statutory_lifecycle(self):
        """
        Executes the full 17-step statutory verification lifecycle:
        Job Create -> DRAFT -> READY -> IN_PROGRESS -> Associate Equipment ->
        Associate Standard -> Record Environment -> Attempt 1 (FAIL) -> Retest Request ->
        RETEST_REQUIRED -> IN_PROGRESS -> Attempt 2 (PASS) -> Upload Evidence ->
        Submit for Review -> Review APPROVE -> Job APPROVED -> Verify Audit Trail.
        """
        job_id = "JOB-E2E-001"
        operator_alice = "INSP-ALICE"
        supervisor_bob = "CONTROLLER-BOB"
        test_id = "A.4.4"  # Eccentricity test

        # ---------------------------------------------------------------------
        # Step 1: Create Job in DRAFT state
        # ---------------------------------------------------------------------
        job = TestJob(
            job_id=job_id,
            instrument_id="INS-SCALE-100",
            job_type=JobType.INITIAL_VERIFICATION,
            status=JobStatus.DRAFT,
            priority=JobPriority.HIGH,
            assigned_inspector_id=operator_alice,
            applicable_tests=[test_id, "A.4.7"],
            test_execution_data={},
            created_date=date.today().isoformat(),
        )
        TEST_JOB_REPOSITORY.save(job)
        assert job.status == JobStatus.DRAFT

        # ---------------------------------------------------------------------
        # Step 2: Move Job through valid workflow (DRAFT -> READY -> IN_PROGRESS)
        # ---------------------------------------------------------------------
        # 2a. DRAFT -> READY
        res_ready = WORKFLOW_SERVICE.transition_job(
            job_id=job_id,
            target_state=JobStatus.READY,
            actor=operator_alice,
            reason="Prerequisites confirmed: instrument presented at test centre",
        )
        assert res_ready.status == JobStatus.READY

        # 2b. READY -> IN_PROGRESS
        res_in_progress = WORKFLOW_SERVICE.transition_job(
            job_id=job_id,
            target_state=JobStatus.IN_PROGRESS,
            actor=operator_alice,
            reason="Beginning statutory verification testing",
        )
        assert res_in_progress.status == JobStatus.IN_PROGRESS

        # ---------------------------------------------------------------------
        # Step 3: Associate Equipment
        # ---------------------------------------------------------------------
        one_year_later = (date.today() + timedelta(days=365)).isoformat()
        eq = EQUIPMENT_SERVICE.create_equipment({
            "name": "Class M1 Working Standards Weight Box",
            "type": "MASS_STANDARD",
            "serial_number": "M1-BOX-789",
            "manufacturer": "National Physical Metrology Ltd",
            "model": "M1-50KG",
            "calibration_certificate": "CAL-M1-2026-99",
            "calibration_date": date.today().isoformat(),
            "calibration_due_date": one_year_later,
            "status": "ACTIVE",
        })
        assoc_eq = EQUIPMENT_SERVICE.associate_equipment_with_job(job_id, eq.id)
        assert eq.id in assoc_eq.equipment_ids
        job_equipment = EQUIPMENT_SERVICE.get_job_equipment(job_id)
        assert len(job_equipment) == 1
        assert job_equipment[0].id == eq.id

        # ---------------------------------------------------------------------
        # Step 4: Associate Test Standard
        # ---------------------------------------------------------------------
        std = EQUIPMENT_SERVICE.create_test_standard({
            "name": "Class F1 Precision Reference Standard",
            "type": "PRECISION_WEIGHT",
            "accuracy_class": "F1",
            "nominal_value": 20.0,
            "unit": "kg",
            "serial_number": "F1-STD-555",
            "certificate_number": "NPL-F1-2026-004",
            "calibration_date": date.today().isoformat(),
            "calibration_due_date": one_year_later,
            "expiry_date": one_year_later,
            "status": "ACTIVE",
        })
        assoc_std = EQUIPMENT_SERVICE.associate_test_standard_with_job(job_id, std.id)
        assert std.id in assoc_std.test_standard_ids
        job_standards = EQUIPMENT_SERVICE.get_job_test_standards(job_id)
        assert len(job_standards) == 1
        assert job_standards[0].id == std.id

        # ---------------------------------------------------------------------
        # Step 5: Record Environment Conditions
        # ---------------------------------------------------------------------
        env_rec = ENVIRONMENT_SERVICE.record_environment(
            job_id=job_id,
            data={
                "temperature": 21.8,
                "humidity": 49.5,
                "atmospheric_pressure": 1012.4,
                "location": "Metrology Verification Laboratory Bay A",
                "operator": operator_alice,
                "notes": "Stable ambient conditions throughout testing",
            },
        )
        assert env_rec.id.startswith("ENV-")
        conditions = ENVIRONMENT_SERVICE.get_environment_history(job_id)
        assert len(conditions) == 1
        assert conditions[0].temperature == 21.8

        # ---------------------------------------------------------------------
        # Step 6: Start Test Attempt 1
        # ---------------------------------------------------------------------
        att1 = ATTEMPT_SERVICE.start_attempt(
            job_id=job_id,
            test_id=test_id,
            operator=operator_alice,
            test_run_id="RUN-P4-001",
            notes="Attempt 1: Initial eccentricity test at 1/3 Max load",
        )
        assert att1.attempt_number == 1
        assert att1.status == AttemptStatus.IN_PROGRESS
        assert att1.result is None

        # ---------------------------------------------------------------------
        # Step 7: Complete Attempt 1 = FAIL
        # ---------------------------------------------------------------------
        att1_completed = ATTEMPT_SERVICE.complete_attempt(
            attempt_id=att1.id,
            result=Verdict.FAIL,
            comments="Eccentricity error +1.4e exceeds maximum permissible error (+1.0e)",
            result_data={"mpe": 1.0, "observed_error": 1.4, "compliant": False},
            test_run_id="RUN-P4-001",
            completed_by=operator_alice,
        )
        assert att1_completed.status == AttemptStatus.COMPLETED
        assert att1_completed.result == Verdict.FAIL

        # ---------------------------------------------------------------------
        # Step 8: Request Retest
        # ---------------------------------------------------------------------
        retest_req = ATTEMPT_SERVICE.request_retest(
            job_id=job_id,
            test_id=test_id,
            attempt_id=att1.id,
            reason="Re-leveling scale footing and corner load cell mechanical re-alignment",
            requested_by=operator_alice,
        )
        assert retest_req.attempt_id == att1.id
        assert retest_req.test_id == test_id

        # ---------------------------------------------------------------------
        # Step 9: Verify Job transitioned to RETEST_REQUIRED
        # ---------------------------------------------------------------------
        job_retest = TEST_JOB_REPOSITORY.get(job_id)
        assert job_retest.status == JobStatus.RETEST_REQUIRED

        # ---------------------------------------------------------------------
        # Step 10: Job -> IN_PROGRESS (Resuming for Retest)
        # ---------------------------------------------------------------------
        job_resumed = WORKFLOW_SERVICE.transition_job(
            job_id=job_id,
            target_state=JobStatus.IN_PROGRESS,
            actor=operator_alice,
            reason="Scale re-leveling completed; ready for Attempt 2",
        )
        assert job_resumed.status == JobStatus.IN_PROGRESS

        # ---------------------------------------------------------------------
        # Step 11: Start Attempt 2
        # ---------------------------------------------------------------------
        att2 = ATTEMPT_SERVICE.start_attempt(
            job_id=job_id,
            test_id=test_id,
            operator=operator_alice,
            test_run_id="RUN-P4-002",
            notes="Attempt 2: Retest of eccentricity following mechanical adjustment",
        )
        assert att2.attempt_number == 2  # Strictly sequential
        assert att2.status == AttemptStatus.IN_PROGRESS

        # ---------------------------------------------------------------------
        # Step 12: Complete Attempt 2 = PASS
        # ---------------------------------------------------------------------
        att2_completed = ATTEMPT_SERVICE.complete_attempt(
            attempt_id=att2.id,
            result=Verdict.PASS,
            comments="Eccentricity error +0.3e is strictly within maximum permissible error (+1.0e)",
            result_data={"mpe": 1.0, "observed_error": 0.3, "compliant": True},
            test_run_id="RUN-P4-002",
            completed_by=operator_alice,
        )
        assert att2_completed.result == Verdict.PASS

        # Verify historical preservation: both Attempt 1 and Attempt 2 exist
        attempts = ATTEMPT_SERVICE.get_attempts_for_test(job_id, test_id)
        assert len(attempts) == 2
        assert attempts[0].attempt_number == 1 and attempts[0].result == Verdict.FAIL
        assert attempts[1].attempt_number == 2 and attempts[1].result == Verdict.PASS

        # ---------------------------------------------------------------------
        # Step 13: Upload Evidence (linked to Job, Test, and Attempt 2)
        # ---------------------------------------------------------------------
        ev1 = EVIDENCE_SERVICE.upload_evidence(
            job_id=job_id,
            test_id=test_id,
            attempt_id=att2.id,
            file_name="eccentricity_retest_leveling.jpg",
            content=b"JPEG_MOCK_IMAGE_DATA_FOR_VERIFICATION",
            evidence_type=EvidenceType.PHOTO,
            uploaded_by=operator_alice,
            description="Photo of leveled bubble and test load placement during Attempt 2",
        )
        assert ev1.id.startswith("EVD-")
        assert ev1.checksum is not None
        assert ev1.status == EvidenceStatus.ACTIVE

        ev2 = EVIDENCE_SERVICE.upload_evidence(
            job_id=job_id,
            file_name="f1_calibration_certificate.pdf",
            content=b"%PDF-1.4 Mock Calibration Certificate Bytes",
            evidence_type=EvidenceType.CALIBRATION_CERTIFICATE,
            uploaded_by=operator_alice,
            description="NPL India Certificate of Calibration for Standard F1-STD-555",
        )
        assert ev2.id.startswith("EVD-")

        # ---------------------------------------------------------------------
        # Step 14: Submit Job for Review (IN_PROGRESS -> REVIEW)
        # ---------------------------------------------------------------------
        review_sub, job_in_review = REVIEW_SERVICE.submit_for_review(
            job_id=job_id,
            reviewer=supervisor_bob,
            comments="All statutory tests completed successfully after valid retest. Evidence attached.",
            submitted_by=operator_alice,
        )
        assert review_sub.status == ReviewStatus.PENDING
        assert job_in_review.status == JobStatus.REVIEW

        # ---------------------------------------------------------------------
        # Step 15: Review -> APPROVE by Supervisor
        # ---------------------------------------------------------------------
        completed_review, job_approved = REVIEW_SERVICE.execute_review(
            job_id=job_id,
            decision=ReviewDecision.APPROVE,
            comments="Verification data, retest results, and calibration standards verified compliant with LM Rules.",
            reviewer=supervisor_bob,
            role=ReviewRole.SUPERVISOR,
        )
        assert completed_review.status == ReviewStatus.COMPLETED
        assert completed_review.decision == ReviewDecision.APPROVE

        # ---------------------------------------------------------------------
        # Step 16: Job -> APPROVED
        # ---------------------------------------------------------------------
        assert job_approved.status == JobStatus.APPROVED

        # ---------------------------------------------------------------------
        # Step 17: Verify Complete Audit Trail
        # ---------------------------------------------------------------------
        audit_trail = AUDIT_SERVICE.get_job_audit_trail(job_id)
        assert len(audit_trail) >= 10

        actions = [log.action for log in audit_trail]
        assert AuditAction.JOB_STATE_CHANGED in actions
        assert AuditAction.JOB_EQUIPMENT_ASSOCIATED in actions
        assert AuditAction.JOB_STANDARD_ASSOCIATED in actions
        assert AuditAction.ENVIRONMENT_RECORDED in actions
        assert AuditAction.TEST_ATTEMPT_STARTED in actions
        assert AuditAction.TEST_ATTEMPT_COMPLETED in actions
        assert AuditAction.RETEST_REQUESTED in actions
        assert AuditAction.EVIDENCE_UPLOADED in actions
        assert AuditAction.REVIEW_SUBMITTED in actions
        assert AuditAction.REVIEW_APPROVED in actions

        # Verify entity-level creation audit logs
        eq_trail = AUDIT_SERVICE.get_entity_audit_trail(EntityType.EQUIPMENT, eq.id)
        assert any(log.action == AuditAction.EQUIPMENT_CREATED for log in eq_trail)

        std_trail = AUDIT_SERVICE.get_entity_audit_trail(EntityType.TEST_STANDARD, std.id)
        assert any(log.action == AuditAction.TEST_STANDARD_CREATED for log in std_trail)

        # Verify state transition sequence in audit records
        state_changes = [
            (log.old_value.get("status"), log.new_value.get("status"))
            for log in audit_trail
            if log.action == AuditAction.JOB_STATE_CHANGED and log.old_value and log.new_value
        ]
        expected_sequence = [
            ("DRAFT", "READY"),
            ("READY", "IN_PROGRESS"),
            ("IN_PROGRESS", "RETEST_REQUIRED"),
            ("RETEST_REQUIRED", "IN_PROGRESS"),
            ("IN_PROGRESS", "REVIEW"),
            ("REVIEW", "APPROVED"),
        ]
        for expected in expected_sequence:
            assert expected in state_changes


# =============================================================================
# 2. Negative End-to-End Tests
# =============================================================================

class TestP5NegativeEndToEnd:
    __test__ = True

    def test_invalid_state_transition_rejected(self):
        """Illegal state transitions are rejected and do not mutate job status."""
        job = TestJob(
            job_id="JOB-NEG-001",
            instrument_id="INS-001",
            status=JobStatus.DRAFT,
            created_by="INSP-01",
        )
        TEST_JOB_REPOSITORY.save(job)

        # Direct DRAFT -> APPROVED is strictly illegal
        with pytest.raises(WorkflowStateTransitionError) as exc_info:
            WORKFLOW_SERVICE.transition_job(
                job_id="JOB-NEG-001",
                target_state=JobStatus.APPROVED,
                actor="INSP-01",
            )
        assert exc_info.value.current_state == "DRAFT"
        assert exc_info.value.target_state == "APPROVED"

        # Job state remains DRAFT
        refreshed = TEST_JOB_REPOSITORY.get("JOB-NEG-001")
        assert refreshed.status == JobStatus.DRAFT

        # Direct DRAFT -> REVIEW is also illegal
        with pytest.raises(WorkflowStateTransitionError):
            WORKFLOW_SERVICE.transition_job(
                job_id="JOB-NEG-001",
                target_state=JobStatus.REVIEW,
                actor="INSP-01",
            )
        assert TEST_JOB_REPOSITORY.get("JOB-NEG-001").status == JobStatus.DRAFT

    def test_expired_equipment_association_rejected(self):
        """Equipment with expired calibration certificate cannot be associated with a test job."""
        job = TestJob(
            job_id="JOB-NEG-002",
            instrument_id="INS-002",
            status=JobStatus.IN_PROGRESS,
            created_by="INSP-01",
        )
        TEST_JOB_REPOSITORY.save(job)

        # Create equipment with expired calibration
        expired_date = (date.today() - timedelta(days=30)).isoformat()
        eq = EQUIPMENT_SERVICE.create_equipment({
            "name": "Expired Test Weight",
            "type": "MASS_STANDARD",
            "serial_number": "SN-EXPIRED-99",
            "manufacturer": "NPL India",
            "model": "EX-10",
            "calibration_certificate": "CAL-EXP-2025",
            "calibration_date": "2024-01-01",
            "calibration_due_date": expired_date,
            "status": "ACTIVE",
        })

        with pytest.raises(CalibrationExpiredError):
            EQUIPMENT_SERVICE.associate_equipment_with_job("JOB-NEG-002", eq.id)

        # Equipment ID not added to job
        refreshed = TEST_JOB_REPOSITORY.get("JOB-NEG-002")
        assert eq.id not in refreshed.equipment_ids

    def test_invalid_retest_request_rejected(self):
        """Retest request fails if target attempt does not exist or target attempt PASSED."""
        job = TestJob(
            job_id="JOB-NEG-003",
            instrument_id="INS-003",
            status=JobStatus.IN_PROGRESS,
            applicable_tests=["A.4.4"],
            created_by="INSP-01",
        )
        TEST_JOB_REPOSITORY.save(job)

        # Attempt does not exist
        with pytest.raises(AttemptNotFoundError):
            ATTEMPT_SERVICE.request_retest(
                job_id="JOB-NEG-003",
                test_id="A.4.4",
                attempt_id="NON-EXISTENT-ATT",
                reason="Invalid attempt",
                requested_by="INSP-01",
            )

        # Attempt PASSED -> retest is illegal
        att = ATTEMPT_SERVICE.start_attempt(job_id="JOB-NEG-003", test_id="A.4.4", operator="INSP-01")
        ATTEMPT_SERVICE.complete_attempt(attempt_id=att.id, result=Verdict.PASS, completed_by="INSP-01")

        with pytest.raises(AttemptValidationError):
            ATTEMPT_SERVICE.request_retest(
                job_id="JOB-NEG-003",
                test_id="A.4.4",
                attempt_id=att.id,
                reason="Attempt passed; retest unnecessary",
                requested_by="INSP-01",
            )

    def test_unauthorized_approval_rejected(self):
        """Four-Eyes Principle: Submitting inspector cannot approve their own review."""
        job = TestJob(
            job_id="JOB-NEG-004",
            instrument_id="INS-004",
            status=JobStatus.IN_PROGRESS,
            applicable_tests=["A.4.4"],
            test_execution_data={"complete": True},
            created_by="INSP-ALICE",
            assigned_inspector_id="INSP-ALICE",
        )
        TEST_JOB_REPOSITORY.save(job)

        # Alice submits review
        REVIEW_SERVICE.submit_for_review(
            job_id="JOB-NEG-004",
            reviewer="INSP-ALICE",
            submitted_by="INSP-ALICE",
        )

        # Alice attempts to approve her own review -> UnauthorizedReviewerError
        with pytest.raises(UnauthorizedReviewerError):
            REVIEW_SERVICE.execute_review(
                job_id="JOB-NEG-004",
                decision=ReviewDecision.APPROVE,
                reviewer="INSP-ALICE",
                role=ReviewRole.SUPERVISOR,
            )

        # Job remains in REVIEW
        refreshed = TEST_JOB_REPOSITORY.get("JOB-NEG-004")
        assert refreshed.status == JobStatus.REVIEW

    def test_invalid_evidence_relationship_rejected(self):
        """Evidence upload fails if attempt_id belongs to a different job or test."""
        job_a = TestJob(
            job_id="JOB-A",
            instrument_id="INS-A",
            status=JobStatus.IN_PROGRESS,
            applicable_tests=["A.4.4"],
            created_by="INSP-01",
        )
        job_b = TestJob(
            job_id="JOB-B",
            instrument_id="INS-B",
            status=JobStatus.IN_PROGRESS,
            applicable_tests=["A.4.7"],
            created_by="INSP-01",
        )
        TEST_JOB_REPOSITORY.save(job_a)
        TEST_JOB_REPOSITORY.save(job_b)

        # Start attempt on Job B
        att_b = ATTEMPT_SERVICE.start_attempt(job_id="JOB-B", test_id="A.4.7", operator="INSP-01")

        # Attempt to upload evidence for Job A referencing attempt on Job B
        with pytest.raises(EvidenceValidationError):
            EVIDENCE_SERVICE.upload_evidence(
                job_id="JOB-A",
                test_id="A.4.4",
                attempt_id=att_b.id,
                file_name="mismatched.png",
                content=b"DATA",
                uploaded_by="INSP-01",
            )

        # Attempt to download Job B's evidence via Job A endpoint -> Access forbidden
        ev_b = EVIDENCE_SERVICE.upload_evidence(
            job_id="JOB-B",
            test_id="A.4.7",
            attempt_id=att_b.id,
            file_name="legit_b.png",
            content=b"DATA_B",
            uploaded_by="INSP-01",
        )
        with pytest.raises(EvidenceSecurityError):
            EVIDENCE_SERVICE.download_evidence(ev_b.id, requesting_job_id="JOB-A")


# =============================================================================
# 3. REST API End-to-End Validation
# =============================================================================

class TestP5RESTAPIE2E:
    __test__ = True

    def test_full_api_workflow_lifecycle(self, client):
        """Validates the complete P5 workflow progression across REST API endpoints."""
        job_id = "JOB-API-E2E"
        operator = "INSP-API"
        supervisor = "CONTROLLER-SUPER"

        # 1. Initialize Job in DRAFT
        job = TestJob(
            job_id=job_id,
            instrument_id="INS-API-01",
            status=JobStatus.DRAFT,
            applicable_tests=["A.4.4"],
            assigned_inspector_id=operator,
            test_execution_data={},
        )
        TEST_JOB_REPOSITORY.save(job)

        # 2. Transition DRAFT -> READY
        r_ready = client.post(
            f"/jobs/{job_id}/transition",
            json={"target_state": "READY", "actor": operator, "reason": "Ready"},
        )
        assert r_ready.status_code == 200
        assert r_ready.json()["current_state"] == "READY"

        # 3. Transition READY -> IN_PROGRESS
        r_prog = client.post(
            f"/jobs/{job_id}/transition",
            json={"target_state": "IN_PROGRESS", "actor": operator, "reason": "Starting execution"},
        )
        assert r_prog.status_code == 200
        assert r_prog.json()["current_state"] == "IN_PROGRESS"

        # 4. Record Environment via API
        r_env = client.post(
            f"/jobs/{job_id}/environment",
            json={
                "temperature": 22.0,
                "humidity": 50.0,
                "atmospheric_pressure": 1013.25,
                "location": "Bench 1",
                "operator": operator,
            },
        )
        assert r_env.status_code == 201
        assert r_env.json()["data"]["temperature"] == 22.0

        # 5. Start Attempt 1 via API
        r_att1 = client.post(
            f"/jobs/{job_id}/tests/A.4.4/attempts",
            json={"operator": operator, "notes": "API Attempt 1"},
        )
        assert r_att1.status_code == 201
        att1_id = r_att1.json()["data"]["id"]
        assert r_att1.json()["data"]["attempt_number"] == 1

        # 6. Complete Attempt 1 with FAIL via API
        r_comp1 = client.post(
            f"/attempts/{att1_id}/complete",
            json={"result": "FAIL", "comments": "Error too high", "completed_by": operator},
        )
        assert r_comp1.status_code == 200
        assert r_comp1.json()["data"]["result"] == "FAIL"

        # 7. Request Retest via API
        r_retest = client.post(
            f"/jobs/{job_id}/tests/A.4.4/attempts/{att1_id}/retest",
            json={"reason": "Mechanical realignment", "requested_by": operator},
        )
        assert r_retest.status_code == 200

        # 8. Transition from RETEST_REQUIRED to IN_PROGRESS
        r_res = client.post(f"/jobs/{job_id}/transition", json={"target_state": "IN_PROGRESS", "actor": operator})
        assert r_res.status_code == 200
        assert r_res.json()["current_state"] == "IN_PROGRESS"

        # 9. Start and Complete Attempt 2 with PASS
        r_att2 = client.post(
            f"/jobs/{job_id}/tests/A.4.4/attempts",
            json={"operator": operator, "notes": "API Attempt 2"},
        )
        att2_id = r_att2.json()["data"]["id"]
        assert r_att2.json()["data"]["attempt_number"] == 2

        client.post(
            f"/attempts/{att2_id}/complete",
            json={"result": "PASS", "comments": "Within tolerance", "completed_by": operator},
        )

        # 10. Upload Evidence via API
        r_ev = client.post(
            f"/jobs/{job_id}/evidence",
            json={
                "file_name": "test_evidence.png",
                "content_base64": "SGVsbG8gTWV0cklRIEV2aWRlbmNl",  # "Hello MetrIQ Evidence"
                "evidence_type": "PHOTO",
                "test_id": "A.4.4",
                "attempt_id": att2_id,
                "uploaded_by": operator,
            },
        )
        assert r_ev.status_code == 201
        ev_id = r_ev.json()["data"]["id"]

        # 11. Submit for Review via API
        r_sub_rev = client.post(
            f"/jobs/{job_id}/submit-review",
            json={"reviewer": supervisor, "comments": "Ready for approval", "submitted_by": operator},
        )
        assert r_sub_rev.status_code == 200

        # 12. Approve Review via API (Supervisor Bob)
        r_app_rev = client.post(
            f"/jobs/{job_id}/review",
            json={"decision": "APPROVE", "comments": "Stamping granted", "reviewer": supervisor, "role": "SUPERVISOR"},
        )
        assert r_app_rev.status_code == 200
        assert r_app_rev.json()["data"]["current_state"] == "APPROVED"

        # 13. Query Full Audit Trail via API
        r_audit = client.get(f"/jobs/{job_id}/audit")
        assert r_audit.status_code == 200
        audit_data = r_audit.json()
        assert audit_data["success"] is True
        assert audit_data["count"] >= 8
