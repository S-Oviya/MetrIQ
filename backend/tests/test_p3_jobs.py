"""
MetrIQ Person 3 Test Suite — Test Job Management & Regulatory Integration
=========================================================================
Tests TestJob models, repository, statutory GATC routing, Person 2 test plan
attachment, regulatory profile association, controlled state machine transitions,
and boundary enforcement with Person 4.
"""

import os
import sys
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.regulatory.models import AccuracyClass, MassUnit
from app.instruments.models import Instrument, InstrumentStatus, InstrumentType
from app.instruments.registry import InstrumentRegistry
from app.jobs.models import JobPriority, JobStatus, JobType, TestJob
from app.jobs.repository import TestJobRepository
from app.jobs.service import TestJobService
from app.jobs.state_machine import JobStateMachine, JobStateTransitionError


class TestP3Jobs(unittest.TestCase):
    """Tests Test Job creation, statutory routing, test plan integration, and lifecycle."""

    def setUp(self) -> None:
        self.instruments = InstrumentRegistry()
        self.jobs = TestJobRepository()
        self.service = TestJobService(
            job_repository=self.jobs,
            instrument_registry=self.instruments,
        )

    def test_01_job_model_creation_and_serialization(self):
        """Verify TestJob entity instantiation, default fields, and serialization."""
        job = TestJob(
            job_id="JOB-TEST-001",
            instrument_id="INST-RETAIL-001",
            job_type=JobType.RE_VERIFICATION,
            status=JobStatus.DRAFT,
            priority=JobPriority.HIGH,
            assigned_inspector_name="Insp. Ramesh",
        )

        d = job.to_dict()
        self.assertEqual(d["job_id"], "JOB-TEST-001")
        self.assertEqual(d["job_type"], "RE_VERIFICATION")
        self.assertEqual(d["status"], "DRAFT")
        self.assertEqual(d["priority"], "HIGH")
        self.assertIsNotNone(d["job_number"])
        self.assertIsNotNone(d["created_date"])

        reconstructed = TestJob.from_dict(d)
        self.assertEqual(reconstructed.job_id, job.job_id)
        self.assertEqual(reconstructed.job_type, JobType.RE_VERIFICATION)

    def test_02_create_job_with_p2_test_plan_and_gatc_routing(self):
        """
        Verify that creating a test job automatically:
        1. Evaluates GATC routing (Class III <= 150kg -> GATC eligible).
        2. Consumes Person 2's API to attach the official test plan with load points & MPEs.
        3. Updates instrument status to IN_VERIFICATION.
        """
        payload = {
            "job_id": "JOB-AUTO-001",
            "instrument_id": "INST-RETAIL-001",  # 15 kg Class III counter scale
            "job_type": "RE_VERIFICATION",
            "priority": "NORMAL",
            "scheduled_date": "2026-09-20",
        }

        res = self.service.create_job(payload)
        self.assertTrue(res["success"])
        self.assertEqual(res["status_code"], 201)
        self.assertTrue(res["has_test_plan"])

        # 1. Verify GATC Routing (Class III 15 kg is legally eligible)
        routing = res["statutory_routing"]
        self.assertTrue(routing["eligible_for_gatc"])
        self.assertEqual(routing["target_authority"], "GATC")

        # 2. Verify Person 2 Test Plan was generated and attached
        job_data = res["data"]
        self.assertIsNotNone(job_data["test_plan"])
        test_plan = job_data["test_plan"]
        self.assertEqual(test_plan["accuracy_class"], "III")
        self.assertIn("tests", test_plan)
        test_ids = [t["test_id"] for t in test_plan["tests"]]
        self.assertIn("A.4.4", test_ids)   # Weighing Performance
        self.assertIn("A.4.7", test_ids)   # Eccentricity
        self.assertIn("A.4.10", test_ids)  # Repeatability

        # 3. Verify Instrument status moved to IN_VERIFICATION
        inst = self.instruments.get("INST-RETAIL-001")
        self.assertEqual(inst.status, InstrumentStatus.IN_VERIFICATION)

    def test_03_create_job_gatc_ineligible_routing(self):
        """
        Verify that creating a job for a Class II instrument (e.g. 6,000 g lab balance)
        correctly routes to State Legal Metrology Officer under GATC Rules, 2013.
        """
        payload = {
            "job_id": "JOB-LAB-001",
            "instrument_id": "INST-LAB-002",  # 6,000 g Class II lab balance
            "job_type": "RE_VERIFICATION",
        }

        res = self.service.create_job(payload)
        self.assertTrue(res["success"])

        # Under GATC Rules 2013 First Schedule, Class II is strictly ineligible
        routing = res["statutory_routing"]
        self.assertFalse(routing["eligible_for_gatc"])
        self.assertEqual(routing["target_authority"], "STATE_LEGAL_METROLOGY_OFFICER")
        self.assertIn("Class II", routing["reason"])

    def test_04_get_job_test_plan_for_person_4(self):
        """
        Verify that Person 4 (Test Execution Engine) can retrieve the exact statutory
        test plan (loads, positions, tolerances) via get_job_test_plan.
        """
        payload = {
            "job_id": "JOB-FOR-P4",
            "instrument_id": "INST-RETAIL-001",
            "job_type": "INITIAL_VERIFICATION",
        }
        self.service.create_job(payload)

        # Person 4 retrieves test plan
        plan = self.service.get_job_test_plan("JOB-FOR-P4")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["max_capacity"], 15.0)

        # Check weighing performance points
        weighing_test = next(t for t in plan["tests"] if t["test_id"] == "A.4.4")
        self.assertGreater(len(weighing_test["test_loads"]), 0)
        first_load = weighing_test["test_loads"][0]
        self.assertIn("load", first_load)
        self.assertIn("mpe_absolute", first_load)
        self.assertIn("position", first_load)

    def test_05_assign_inspector_and_test_centre(self):
        """Verify inspector and test centre assignment transitions job to READY_FOR_TEST."""
        payload = {
            "job_id": "JOB-ASSIGN-01",
            "instrument_id": "INST-RETAIL-001",
            "job_type": "RE_VERIFICATION",
        }
        self.service.create_job(payload)

        res = self.service.assign_inspector(
            job_id="JOB-ASSIGN-01",
            inspector_id="INSP-882",
            inspector_name="S. Sundaram",
            testing_centre_id="GATC-BLR-01",
            testing_centre_name="Bangalore Legal Metrology Test Centre",
            scheduled_date="2026-09-25",
        )
        self.assertTrue(res["success"])
        updated_job = self.jobs.get("JOB-ASSIGN-01")
        self.assertIn(updated_job.status, (JobStatus.ASSIGNED, JobStatus.READY_FOR_TEST))
        self.assertEqual(updated_job.assigned_inspector_id, "INSP-882")
        self.assertEqual(updated_job.testing_centre_id, "GATC-BLR-01")

    def test_06_invalid_instrument_rejection(self):
        """Verify job creation with non-existent instrument ID returns 404."""
        payload = {
            "job_id": "JOB-BAD-INST",
            "instrument_id": "NON-EXISTENT-INST-999",
            "job_type": "RE_VERIFICATION",
        }
        res = self.service.create_job(payload)
        self.assertFalse(res["success"])
        self.assertEqual(res["status_code"], 404)
        self.assertIn("not found in registry", res["message"])

    def test_07_invalid_job_type_rejection(self):
        """Verify job creation with invalid job type returns 422 Unprocessable Entity."""
        payload = {
            "job_id": "JOB-BAD-TYPE",
            "instrument_id": "INST-RETAIL-001",
            "job_type": "INVALID_METROLOGICAL_ACTION",
        }
        res = self.service.create_job(payload)
        self.assertFalse(res["success"])
        self.assertEqual(res["status_code"], 422)
        self.assertIn("Invalid job_type", res["message"])

    def test_08_duplicate_job_id_rejection(self):
        """Verify that passing an existing job_id is rejected with 409 Conflict."""
        payload1 = {
            "job_id": "JOB-UNIQUE-01",
            "instrument_id": "INST-RETAIL-001",
            "job_type": "RE_VERIFICATION",
        }
        res1 = self.service.create_job(payload1)
        self.assertTrue(res1["success"])

        # Second job with same ID must be rejected
        payload2 = {
            "job_id": "JOB-UNIQUE-01",
            "instrument_id": "INST-LAB-002",
            "job_type": "INITIAL_VERIFICATION",
        }
        res2 = self.service.create_job(payload2)
        self.assertFalse(res2["success"])
        self.assertEqual(res2["status_code"], 409)
        self.assertIn("already exists", res2["message"])

    def test_09_duplicate_active_job_for_same_instrument_rejected(self):
        """Verify that creating multiple active verification jobs on the same instrument is rejected."""
        payload1 = {
            "job_id": "JOB-ACTIVE-01",
            "instrument_id": "INST-RETAIL-001",
            "job_type": "RE_VERIFICATION",
        }
        res1 = self.service.create_job(payload1)
        self.assertTrue(res1["success"])

        # Attempting second active job without closing first
        payload2 = {
            "job_id": "JOB-ACTIVE-02",
            "instrument_id": "INST-RETAIL-001",
            "job_type": "RE_VERIFICATION",
        }
        res2 = self.service.create_job(payload2)
        self.assertFalse(res2["success"])
        self.assertEqual(res2["status_code"], 409)
        self.assertIn("already has active test job(s)", res2["message"])

    def test_10_regulatory_profile_and_version_association(self):
        """Verify that job creation associates regulatory profile ID, version, and statutory rules."""
        payload = {
            "job_id": "JOB-REG-ASSOC",
            "instrument_id": "INST-RETAIL-001",
            "job_type": "RE_VERIFICATION",
            "profile_id": "IN_LM_2011_ACTIVE",
        }
        res = self.service.create_job(payload)
        self.assertTrue(res["success"])
        data = res["data"]
        self.assertEqual(data["regulatory_profile_id"], "IN_LM_2011_ACTIVE")
        self.assertIsNotNone(data["regulatory_version"])
        self.assertGreater(len(data["regulatory_rule_references"]), 0)
        self.assertGreater(len(data["applicable_tests"]), 0)
        self.assertIn("A.4.4", data["applicable_tests"])

    def test_11_model_approval_auto_resolution(self):
        """Verify auto-resolution of model approval ID from instrument metadata."""
        inst = self.instruments.get("INST-RETAIL-001")
        self.assertIsNotNone(inst.model_approval_number)

        payload = {
            "job_id": "JOB-MA-RESOLV",
            "instrument_id": "INST-RETAIL-001",
            "job_type": "INITIAL_VERIFICATION",
        }
        res = self.service.create_job(payload)
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["model_approval_id"], inst.model_approval_number)

    def test_12_controlled_job_lifecycle_state_transitions(self):
        """
        Verify controlled 10-stage lifecycle progression:
        DRAFT -> CREATED -> VALIDATED -> TEST_PLAN_GENERATED -> READY_FOR_TEST -> IN_TESTING
        -> TEST_COMPLETED -> UNDER_REVIEW -> APPROVED -> CLOSED
        """
        job = TestJob(
            job_id="JOB-FULL-LIFE",
            instrument_id="INST-RETAIL-001",
            job_type=JobType.RE_VERIFICATION,
            status=JobStatus.DRAFT,
        )
        self.jobs.save(job)

        # 1. DRAFT -> CREATED
        res = self.service.transition_job_status("JOB-FULL-LIFE", JobStatus.CREATED, reason="Job registered")
        self.assertEqual(res["status"], "CREATED")

        # 2. CREATED -> VALIDATED
        res = self.service.transition_job_status("JOB-FULL-LIFE", JobStatus.VALIDATED, reason="Metrology validated")
        self.assertEqual(res["status"], "VALIDATED")

        # 3. VALIDATED -> TEST_PLAN_GENERATED
        res = self.service.transition_job_status("JOB-FULL-LIFE", JobStatus.TEST_PLAN_GENERATED, reason="Plan generated")
        self.assertEqual(res["status"], "TEST_PLAN_GENERATED")

        # 4. TEST_PLAN_GENERATED -> READY_FOR_TEST
        res = self.service.transition_job_status("JOB-FULL-LIFE", JobStatus.READY_FOR_TEST, reason="Inspector allocated")
        self.assertEqual(res["status"], "READY_FOR_TEST")

        # 5. READY_FOR_TEST -> IN_TESTING
        res = self.service.transition_job_status("JOB-FULL-LIFE", JobStatus.IN_TESTING, reason="Physical weights applied")
        self.assertEqual(res["status"], "IN_TESTING")

        # 6. IN_TESTING -> TEST_COMPLETED
        res = self.service.transition_job_status("JOB-FULL-LIFE", JobStatus.TEST_COMPLETED, reason="Readings recorded")
        self.assertEqual(res["status"], "TEST_COMPLETED")

        # 7. TEST_COMPLETED -> UNDER_REVIEW
        res = self.service.transition_job_status("JOB-FULL-LIFE", JobStatus.UNDER_REVIEW, reason="Submitted to Officer")
        self.assertEqual(res["status"], "UNDER_REVIEW")

        # 8. UNDER_REVIEW -> APPROVED
        res = self.service.transition_job_status("JOB-FULL-LIFE", JobStatus.APPROVED, reason="Passed all legal tolerances")
        self.assertEqual(res["status"], "APPROVED")

        # 9. APPROVED -> CLOSED
        res = self.service.transition_job_status("JOB-FULL-LIFE", JobStatus.CLOSED, reason="Stamping completed, cert issued")
        self.assertEqual(res["status"], "CLOSED")
        self.assertIsNotNone(res["data"]["completed_at"])

        # Verify instrument status updated to ACTIVE with updated verification date
        inst = self.instruments.get("INST-RETAIL-001")
        self.assertEqual(inst.status, InstrumentStatus.ACTIVE)
        self.assertIsNotNone(inst.last_verification_date)

    def test_13_illegal_state_transition_prevented(self):
        """Verify that skipping lifecycle states raises error."""
        job = TestJob(
            job_id="JOB-JUMP-02",
            instrument_id="INST-RETAIL-001",
            status=JobStatus.DRAFT,
        )
        self.jobs.save(job)

        # Illegal jump: DRAFT -> CLOSED is prohibited
        res = self.service.transition_job_status("JOB-JUMP-02", JobStatus.CLOSED)
        self.assertFalse(res["success"])
        self.assertEqual(res["status_code"], 400)
        self.assertIn("Invalid transition", res["message"])

    def test_14_p3_does_not_execute_tests(self):
        """Verify Person 3 raises NotImplementedError and does NOT perform test execution."""
        with self.assertRaises(NotImplementedError) as ctx:
            self.service.execute_test("JOB-001", "A.4.4", observations=[10.0, 20.0])
        self.assertIn("Person 3 does not perform test execution", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
