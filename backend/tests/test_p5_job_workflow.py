"""
MetrIQ P5 Test Suite — Test-Job Workflow & State Machine
========================================================
Person 5: Workflow + Evidence Engineer

Verifies the lifecycle state transitions, business rules, metadata auditing,
and REST endpoints for NAWI test jobs under Indian Legal Metrology Rules.
"""

import os
import sys
import unittest
from datetime import datetime, timezone

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.jobs.models import JobStatus, TestJob
from app.jobs.repository import TestJobRepository
from app.workflow.models import JobStateTransitionRecord
from app.workflow.service import (
    JobNotFoundError,
    WorkflowService,
    transition_job,
    transitionJob,
)
from app.workflow.state_machine import WorkflowStateMachine, WorkflowStateTransitionError

# FastAPI TestClient
try:
    from fastapi.testclient import TestClient
    from app.main import app
    HAS_TEST_CLIENT = True
except ImportError:
    HAS_TEST_CLIENT = False


class TestP5JobWorkflow(unittest.TestCase):
    """Unit tests for P5 test job lifecycle state machine and workflow service."""

    def setUp(self) -> None:
        from app.jobs.repository import TEST_JOB_REPOSITORY
        self.repo = TEST_JOB_REPOSITORY
        self.service = WorkflowService(job_repository=self.repo)

    def _create_sample_job(self, job_id: str = "JOB-TEST-001", status: JobStatus = JobStatus.DRAFT) -> TestJob:
        """Helper to create and save a valid TestJob in the repository."""
        job = TestJob(
            job_id=job_id,
            instrument_id="INST-SCALE-001",
            status=status,
            created_by="OFFICER_INIT",
        )
        return self.repo.save(job)

    # =========================================================================
    # Valid Transitions
    # =========================================================================

    def test_01_valid_transition_draft_to_ready(self):
        """Verify valid transition: DRAFT -> READY."""
        job = self._create_sample_job("JOB-V01", JobStatus.DRAFT)
        updated = self.service.transition_job(
            job_id=job.job_id,
            target_state=JobStatus.READY,
            actor="OFFICER_A",
            reason="Instrument pre-checks verified",
        )
        self.assertEqual(updated.status, JobStatus.READY)
        self.assertEqual(updated.current_state, "READY")
        self.assertEqual(updated.updated_by, "OFFICER_A")
        self.assertIsNotNone(updated.state_changed_at)
        self.assertEqual(len(updated.state_history), 1)
        self.assertEqual(updated.state_history[-1].from_status, "DRAFT")
        self.assertEqual(updated.state_history[-1].to_status, "READY")
        self.assertEqual(updated.state_history[-1].user_id, "OFFICER_A")
        self.assertEqual(updated.state_history[-1].reason, "Instrument pre-checks verified")

    def test_02_valid_transition_ready_to_in_progress(self):
        """Verify valid transition: READY -> IN_PROGRESS."""
        job = self._create_sample_job("JOB-V02", JobStatus.READY)
        updated = self.service.transition_job(
            job_id=job.job_id,
            target_state=JobStatus.IN_PROGRESS,
            actor="INSPECTOR_B",
            reason="Testing commenced on site",
        )
        self.assertEqual(updated.status, JobStatus.IN_PROGRESS)
        self.assertEqual(updated.state_history[-1].from_status, "READY")
        self.assertEqual(updated.state_history[-1].to_status, "IN_PROGRESS")

    def test_03_valid_transition_in_progress_to_retest_required(self):
        """Verify valid transition: IN_PROGRESS -> RETEST_REQUIRED."""
        job = self._create_sample_job("JOB-V03", JobStatus.IN_PROGRESS)
        # Add a prior failed test attempt
        job.test_attempts.append({
            "attempt_number": 1,
            "test_type": "WEIGHING_PERFORMANCE",
            "verdict": "FAIL",
            "reason": "MPE exceeded at 500kg load",
        })
        self.repo.save(job)

        updated = self.service.transition_job(
            job_id=job.job_id,
            target_state=JobStatus.RETEST_REQUIRED,
            actor="INSPECTOR_B",
            reason="Repeatability test failed tolerance, retest required",
        )
        self.assertEqual(updated.status, JobStatus.RETEST_REQUIRED)
        self.assertEqual(updated.state_history[-1].from_status, "IN_PROGRESS")
        self.assertEqual(updated.state_history[-1].to_status, "RETEST_REQUIRED")

        # Business Rule 5: Verify previous test attempt is preserved
        self.assertEqual(len(updated.test_attempts), 1)
        self.assertEqual(updated.test_attempts[0]["attempt_number"], 1)
        self.assertEqual(updated.test_attempts[0]["verdict"], "FAIL")

    def test_04_valid_transition_retest_required_to_in_progress(self):
        """Verify valid transition: RETEST_REQUIRED -> IN_PROGRESS."""
        job = self._create_sample_job("JOB-V04", JobStatus.RETEST_REQUIRED)
        job.test_attempts.append({
            "attempt_number": 1,
            "test_type": "WEIGHING_PERFORMANCE",
            "verdict": "FAIL",
        })
        self.repo.save(job)

        updated = self.service.transition_job(
            job_id=job.job_id,
            target_state=JobStatus.IN_PROGRESS,
            actor="INSPECTOR_B",
            reason="Corner weights readjusted; re-running test",
        )
        self.assertEqual(updated.status, JobStatus.IN_PROGRESS)
        self.assertEqual(updated.state_history[-1].from_status, "RETEST_REQUIRED")
        self.assertEqual(updated.state_history[-1].to_status, "IN_PROGRESS")

        # Prior attempt still preserved
        self.assertEqual(len(updated.test_attempts), 1)

    def test_05_valid_transition_in_progress_to_review(self):
        """Verify valid transition: IN_PROGRESS -> REVIEW when test execution data is present."""
        job = self._create_sample_job("JOB-V05", JobStatus.IN_PROGRESS)
        test_data = {
            "observations": [{"load": 10.0, "indicated": 10.0, "error": 0.0}],
            "verdict": "PASS",
        }
        updated = self.service.transition_job(
            job_id=job.job_id,
            target_state=JobStatus.REVIEW,
            actor="INSPECTOR_B",
            reason="All test executions completed",
            test_execution_data=test_data,
        )
        self.assertEqual(updated.status, JobStatus.REVIEW)
        self.assertEqual(updated.state_history[-1].from_status, "IN_PROGRESS")
        self.assertEqual(updated.state_history[-1].to_status, "REVIEW")
        self.assertIsNotNone(updated.test_execution_data)
        self.assertEqual(updated.test_execution_data.get("verdict"), "PASS")

    def test_06_valid_transition_review_to_approved(self):
        """Verify valid transition: REVIEW -> APPROVED."""
        job = self._create_sample_job("JOB-V06", JobStatus.REVIEW)
        updated = self.service.transition_job(
            job_id=job.job_id,
            target_state=JobStatus.APPROVED,
            actor="SENIOR_OFFICER",
            reason="All statutory limits satisfied; approved for certification",
        )
        self.assertEqual(updated.status, JobStatus.APPROVED)
        self.assertEqual(updated.state_history[-1].from_status, "REVIEW")
        self.assertEqual(updated.state_history[-1].to_status, "APPROVED")

    def test_07_valid_transition_review_to_rejected(self):
        """Verify valid transition: REVIEW -> REJECTED."""
        job = self._create_sample_job("JOB-V07", JobStatus.REVIEW)
        updated = self.service.transition_job(
            job_id=job.job_id,
            target_state=JobStatus.REJECTED,
            actor="SENIOR_OFFICER",
            reason="Documentation incomplete and turning points unverified",
        )
        self.assertEqual(updated.status, JobStatus.REJECTED)
        self.assertEqual(updated.state_history[-1].from_status, "REVIEW")
        self.assertEqual(updated.state_history[-1].to_status, "REJECTED")

    def test_08_valid_transition_review_to_in_progress(self):
        """Verify valid transition: REVIEW -> IN_PROGRESS (returned for correction)."""
        job = self._create_sample_job("JOB-V08", JobStatus.REVIEW)
        updated = self.service.transition_job(
            job_id=job.job_id,
            target_state=JobStatus.IN_PROGRESS,
            actor="SENIOR_OFFICER",
            reason="Returned for re-measurement of eccentricity position 3",
        )
        self.assertEqual(updated.status, JobStatus.IN_PROGRESS)
        self.assertEqual(updated.state_history[-1].from_status, "REVIEW")
        self.assertEqual(updated.state_history[-1].to_status, "IN_PROGRESS")

    def test_09_valid_transition_rejected_to_in_progress(self):
        """Verify valid transition: REJECTED -> IN_PROGRESS (correction/re-servicing path)."""
        job = self._create_sample_job("JOB-V09", JobStatus.REJECTED)
        updated = self.service.transition_job(
            job_id=job.job_id,
            target_state=JobStatus.IN_PROGRESS,
            actor="OFFICER_A",
            reason="Scale re-calibrated by technician; restarting inspection",
        )
        self.assertEqual(updated.status, JobStatus.IN_PROGRESS)
        self.assertEqual(updated.state_history[-1].from_status, "REJECTED")
        self.assertEqual(updated.state_history[-1].to_status, "IN_PROGRESS")

    def test_10_valid_transition_approved_to_report_generated(self):
        """Verify valid transition: APPROVED -> REPORT_GENERATED (terminal state)."""
        job = self._create_sample_job("JOB-V10", JobStatus.APPROVED)
        updated = self.service.transition_job(
            job_id=job.job_id,
            target_state=JobStatus.REPORT_GENERATED,
            actor="SYSTEM_P6",
            reason="Official verification certificate generated and archived",
        )
        self.assertEqual(updated.status, JobStatus.REPORT_GENERATED)
        self.assertEqual(updated.state_history[-1].from_status, "APPROVED")
        self.assertEqual(updated.state_history[-1].to_status, "REPORT_GENERATED")
        self.assertIsNotNone(updated.completed_at)

    def test_11_full_lifecycle_progression(self):
        """Traverse the entire valid lifecycle end-to-end and check history completeness."""
        job = self._create_sample_job("JOB-FULL-P5", JobStatus.DRAFT)
        
        # 1. DRAFT -> READY
        job = self.service.transition_job(job.job_id, "READY", actor="ACTOR_1", reason="Draft ready")
        self.assertEqual(job.status, JobStatus.READY)

        # 2. READY -> IN_PROGRESS
        job = self.service.transition_job(job.job_id, "IN_PROGRESS", actor="ACTOR_2", reason="Testing begins")
        self.assertEqual(job.status, JobStatus.IN_PROGRESS)

        # 3. IN_PROGRESS -> RETEST_REQUIRED
        job.test_attempts.append({"attempt": 1, "result": "FAIL"})
        job = self.service.transition_job(job.job_id, "RETEST_REQUIRED", actor="ACTOR_2", reason="Failure detected")
        self.assertEqual(job.status, JobStatus.RETEST_REQUIRED)

        # 4. RETEST_REQUIRED -> IN_PROGRESS
        job.test_attempts.append({"attempt": 2, "result": "PASS"})
        job = self.service.transition_job(job.job_id, "IN_PROGRESS", actor="ACTOR_2", reason="Retest pass")
        self.assertEqual(job.status, JobStatus.IN_PROGRESS)

        # 5. IN_PROGRESS -> REVIEW (test data attached)
        job = self.service.transition_job(
            job.job_id,
            "REVIEW",
            actor="ACTOR_2",
            reason="Submit to review",
            test_execution_data={"summary": "All tests passed on attempt 2"},
        )
        self.assertEqual(job.status, JobStatus.REVIEW)

        # 6. REVIEW -> REJECTED
        job = self.service.transition_job(job.job_id, "REJECTED", actor="ACTOR_3", reason="Signature missing")
        self.assertEqual(job.status, JobStatus.REJECTED)

        # 7. REJECTED -> IN_PROGRESS
        job = self.service.transition_job(job.job_id, "IN_PROGRESS", actor="ACTOR_2", reason="Signature uploaded")
        self.assertEqual(job.status, JobStatus.IN_PROGRESS)

        # 8. IN_PROGRESS -> REVIEW
        job = self.service.transition_job(job.job_id, "REVIEW", actor="ACTOR_2", reason="Resubmit for review")
        self.assertEqual(job.status, JobStatus.REVIEW)

        # 9. REVIEW -> APPROVED
        job = self.service.transition_job(job.job_id, "APPROVED", actor="ACTOR_3", reason="Approved")
        self.assertEqual(job.status, JobStatus.APPROVED)

        # 10. APPROVED -> REPORT_GENERATED
        job = self.service.transition_job(job.job_id, "REPORT_GENERATED", actor="ACTOR_P6", reason="Report ready")
        self.assertEqual(job.status, JobStatus.REPORT_GENERATED)

        # Verify previous state is never silently lost (10 transitions recorded)
        self.assertEqual(len(job.state_history), 10)
        expected_sequence = [
            ("DRAFT", "READY"),
            ("READY", "IN_PROGRESS"),
            ("IN_PROGRESS", "RETEST_REQUIRED"),
            ("RETEST_REQUIRED", "IN_PROGRESS"),
            ("IN_PROGRESS", "REVIEW"),
            ("REVIEW", "REJECTED"),
            ("REJECTED", "IN_PROGRESS"),
            ("IN_PROGRESS", "REVIEW"),
            ("REVIEW", "APPROVED"),
            ("APPROVED", "REPORT_GENERATED"),
        ]
        for record, (expected_from, expected_to) in zip(job.state_history, expected_sequence):
            self.assertEqual(record.from_status, expected_from)
            self.assertEqual(record.to_status, expected_to)
            self.assertIsNotNone(record.timestamp)
            self.assertIsNotNone(record.user_id)

    # =========================================================================
    # Invalid Transitions
    # =========================================================================

    def test_20_invalid_transition_draft_to_approved(self):
        """Rule 1: A job cannot be approved directly from DRAFT."""
        job = self._create_sample_job("JOB-INV-01", JobStatus.DRAFT)
        with self.assertRaises(WorkflowStateTransitionError) as ctx:
            self.service.transition_job(job.job_id, JobStatus.APPROVED)
        self.assertEqual(ctx.exception.error_code, "INVALID_STATE_TRANSITION")
        self.assertIn("Job in DRAFT cannot transition directly to APPROVED", str(ctx.exception))
        # Ensure state was not modified
        self.assertEqual(self.repo.get(job.job_id).status, JobStatus.DRAFT)

    def test_21_invalid_transition_draft_to_review(self):
        """Verify invalid transition: DRAFT -> REVIEW."""
        job = self._create_sample_job("JOB-INV-02", JobStatus.DRAFT)
        with self.assertRaises(WorkflowStateTransitionError) as ctx:
            self.service.transition_job(job.job_id, JobStatus.REVIEW)
        self.assertEqual(ctx.exception.error_code, "INVALID_STATE_TRANSITION")
        self.assertIn("Job in DRAFT cannot transition directly to REVIEW", str(ctx.exception))

    def test_22_invalid_transition_ready_to_approved(self):
        """Verify invalid transition: READY -> APPROVED."""
        job = self._create_sample_job("JOB-INV-03", JobStatus.READY)
        with self.assertRaises(WorkflowStateTransitionError) as ctx:
            self.service.transition_job(job.job_id, JobStatus.APPROVED)
        self.assertEqual(ctx.exception.error_code, "INVALID_STATE_TRANSITION")
        self.assertIn("Job in READY cannot transition directly to APPROVED", str(ctx.exception))

    def test_23_invalid_transition_in_progress_to_approved(self):
        """Rule 3: A job cannot become APPROVED unless review has been completed."""
        job = self._create_sample_job("JOB-INV-04", JobStatus.IN_PROGRESS)
        with self.assertRaises(WorkflowStateTransitionError) as ctx:
            self.service.transition_job(job.job_id, JobStatus.APPROVED)
        self.assertEqual(ctx.exception.error_code, "INVALID_STATE_TRANSITION")
        self.assertIn("Job in IN_PROGRESS cannot transition directly to APPROVED", str(ctx.exception))

    def test_24_invalid_transition_retest_required_to_approved(self):
        """Verify invalid transition: RETEST_REQUIRED -> APPROVED."""
        job = self._create_sample_job("JOB-INV-05", JobStatus.RETEST_REQUIRED)
        with self.assertRaises(WorkflowStateTransitionError) as ctx:
            self.service.transition_job(job.job_id, JobStatus.APPROVED)
        self.assertEqual(ctx.exception.error_code, "INVALID_STATE_TRANSITION")
        self.assertIn("Job in RETEST_REQUIRED cannot transition directly to APPROVED", str(ctx.exception))

    def test_25_invalid_transition_approved_to_in_progress(self):
        """Verify invalid transition: APPROVED -> IN_PROGRESS."""
        job = self._create_sample_job("JOB-INV-06", JobStatus.APPROVED)
        with self.assertRaises(WorkflowStateTransitionError) as ctx:
            self.service.transition_job(job.job_id, JobStatus.IN_PROGRESS)
        self.assertEqual(ctx.exception.error_code, "INVALID_STATE_TRANSITION")
        self.assertIn("Job in APPROVED cannot transition directly to IN_PROGRESS", str(ctx.exception))

    def test_26_invalid_transition_report_generated_to_anything(self):
        """Rule 6: REPORT_GENERATED is terminal for the current workflow."""
        job = self._create_sample_job("JOB-INV-07", JobStatus.REPORT_GENERATED)
        targets_to_test = [
            JobStatus.DRAFT,
            JobStatus.READY,
            JobStatus.IN_PROGRESS,
            JobStatus.RETEST_REQUIRED,
            JobStatus.REVIEW,
            JobStatus.REJECTED,
            JobStatus.APPROVED,
        ]
        for target in targets_to_test:
            with self.assertRaises(WorkflowStateTransitionError) as ctx:
                self.service.transition_job(job.job_id, target)
            self.assertEqual(ctx.exception.error_code, "INVALID_STATE_TRANSITION")
            self.assertIn("terminal state", str(ctx.exception).lower())

    def test_27_invalid_transition_self_state(self):
        """Verify self-transition is disallowed (no no-op transition without change)."""
        job = self._create_sample_job("JOB-INV-08", JobStatus.IN_PROGRESS)
        with self.assertRaises(WorkflowStateTransitionError) as ctx:
            self.service.transition_job(job.job_id, JobStatus.IN_PROGRESS)
        self.assertEqual(ctx.exception.error_code, "INVALID_STATE_TRANSITION")
        self.assertIn("already in IN_PROGRESS state", str(ctx.exception))

    def test_28_invalid_transition_review_without_test_execution_data(self):
        """Rule 2: A job cannot enter REVIEW unless the required test execution data is present."""
        job = self._create_sample_job("JOB-INV-09", JobStatus.IN_PROGRESS)
        # Job has empty test_execution_data and empty test_attempts
        with self.assertRaises(WorkflowStateTransitionError) as ctx:
            self.service.transition_job(job.job_id, JobStatus.REVIEW)
        self.assertEqual(ctx.exception.error_code, "MISSING_TEST_EXECUTION_DATA")
        self.assertIn("cannot enter review without required test execution data", str(ctx.exception).lower())

    def test_29_job_not_found(self):
        """Verify transitioning a non-existent job raises JobNotFoundError."""
        with self.assertRaises(JobNotFoundError):
            self.service.transition_job("JOB-NONEXISTENT", JobStatus.READY)

    # =========================================================================
    # Function aliases and interface compliance
    # =========================================================================

    def test_30_camel_case_transitionJob_alias(self):
        """Verify camelCase transitionJob(jobId, targetState, actor, reason) compliance."""
        job = self._create_sample_job("JOB-CAMEL-01", JobStatus.DRAFT)
        updated = transitionJob(
            jobId=job.job_id,
            targetState="READY",
            actor="OFFICER_P5",
            reason="Valid transition via camelCase helper",
        )
        self.assertEqual(updated.status, JobStatus.READY)

    def test_31_module_level_transition_job(self):
        """Verify snake_case module level transition_job function."""
        job = self._create_sample_job("JOB-SNAKE-01", JobStatus.READY)
        updated = transition_job(
            job_id=job.job_id,
            target_state="IN_PROGRESS",
            actor="OFFICER_P5",
            reason="Valid transition via snake_case helper",
        )
        self.assertEqual(updated.status, JobStatus.IN_PROGRESS)


class TestP5WorkflowAPI(unittest.TestCase):
    """Integration tests for P5 Workflow REST API endpoints using FastAPI TestClient."""

    @classmethod
    def setUpClass(cls) -> None:
        if not HAS_TEST_CLIENT:
            raise unittest.SkipTest("FastAPI TestClient not available")
        cls.client = TestClient(app)

    def setUp(self) -> None:
        from app.jobs.repository import TEST_JOB_REPOSITORY
        self.repo = TEST_JOB_REPOSITORY
        self.job = TestJob(
            job_id="API-JOB-001",
            instrument_id="INST-API-001",
            status=JobStatus.DRAFT,
            created_by="API_TESTER",
        )
        self.repo.save(self.job)

    def test_40_api_valid_transition(self):
        """Test POST /jobs/{jobId}/transition with valid payload."""
        response = self.client.post(
            f"/jobs/{self.job.job_id}/transition",
            json={
                "target_state": "READY",
                "reason": "Pre-test checklist satisfied",
                "actor": "TEST_OFFICER",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("current_state"), "READY")
        self.assertEqual(data.get("data", {}).get("status"), "READY")

    def test_41_api_invalid_transition(self):
        """Test POST /jobs/{jobId}/transition returns 400 and useful error for invalid transition."""
        response = self.client.post(
            f"/jobs/{self.job.job_id}/transition",
            json={
                "target_state": "APPROVED",
                "reason": "Trying to jump from DRAFT to APPROVED",
            },
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data.get("error"), "INVALID_STATE_TRANSITION")
        self.assertIn("Job in DRAFT cannot transition directly to APPROVED", data.get("message"))

    def test_42_api_missing_target_state(self):
        """Test POST /jobs/{jobId}/transition returns 400 if target_state is omitted."""
        response = self.client.post(
            f"/jobs/{self.job.job_id}/transition",
            json={"reason": "Missing target_state"},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data.get("error"), "MISSING_TARGET_STATE")

    def test_43_api_job_not_found(self):
        """Test POST /jobs/{jobId}/transition returns 404 for non-existent job."""
        response = self.client.post(
            "/jobs/NONEXISTENT-999/transition",
            json={"target_state": "READY"},
        )
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data.get("error"), "JOB_NOT_FOUND")

    def test_44_api_get_job_state(self):
        """Test GET /jobs/{jobId}/state returns state and transition history."""
        # Execute transition first
        self.client.post(
            f"/jobs/{self.job.job_id}/transition",
            json={"target_state": "READY", "reason": "Moving to ready"},
        )
        response = self.client.get(f"/jobs/{self.job.job_id}/state")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("current_state"), "READY")
        self.assertIsInstance(data.get("state_history"), list)
        self.assertGreater(len(data.get("state_history")), 0)


if __name__ == "__main__":
    unittest.main()
