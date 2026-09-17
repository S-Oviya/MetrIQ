"""
MetrIQ Person 3 Test Suite — Instrument Lifecycle & State Machine
=================================================================
Tests statutory re-verification due dates, legal metrology seals,
job state machine transitions, and cross-module synchronization.
"""

import os
import sys
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.regulatory.models import AccuracyClass, JobType, MassUnit
from app.instruments.models import (
    CustomerLocation,
    Instrument,
    InstrumentLifecycleEvent,
    InstrumentStatus,
    InstrumentType,
    LifecycleEventType,
    PhysicalSeal,
    SealStatus,
    SealType,
)
from app.instruments.registry import InstrumentRegistry
from app.instruments.lifecycle import (
    InstrumentLifecycleManager,
    InstrumentLifecycleStateMachine,
    InstrumentLifecycleTransitionError,
)
from app.instruments.service import InstrumentService
from app.jobs.models import JobStatus, TestJob
from app.jobs.repository import TestJobRepository
from app.jobs.state_machine import JobStateMachine, JobStateTransitionError
from app.jobs.service import TestJobService


class TestP3Lifecycle(unittest.TestCase):
    """Tests instrument lifecycle, statutory seals, and job state transitions."""

    def setUp(self) -> None:
        self.instruments = InstrumentRegistry()
        self.jobs = TestJobRepository()
        self.service = TestJobService(
            job_repository=self.jobs,
            instrument_registry=self.instruments,
        )

    def test_01_re_verification_due_date_calculation(self):
        """Verify statutory re-verification calculation (12 months commercial, 24 months lab)."""
        # Commercial retail scale (12 months)
        inst_comm = Instrument(
            instrument_id="INST-COMM-01",
            serial_number="SN-COMM-01",
            manufacturer="Generic Mfr",
            model_name="Scale 1",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
            instrument_type=InstrumentType.ELECTRONIC_COUNTER_SCALE,
            re_verification_interval_months=12,
        )
        due_comm = InstrumentLifecycleManager.calculate_next_re_verification_due(inst_comm, "2026-09-17")
        self.assertEqual(due_comm, "2027-09-17")

        # Precision lab balance (24 months)
        inst_lab = Instrument(
            instrument_id="INST-LAB-01",
            serial_number="SN-LAB-01",
            manufacturer="Generic Mfr",
            model_name="Lab 1",
            accuracy_class=AccuracyClass.CLASS_II,
            max_capacity=6000.0,
            min_capacity=5.0,
            e=0.1,
            d=0.1,
            unit=MassUnit.G,
            instrument_type=InstrumentType.PRECISION_BALANCE,
            re_verification_interval_months=24,
        )
        due_lab = InstrumentLifecycleManager.calculate_next_re_verification_due(inst_lab, "2026-09-17")
        self.assertEqual(due_lab, "2028-09-17")

    def test_02_operational_status_deadlines(self):
        """Verify status transitions when due date expires or approaches."""
        inst = Instrument(
            instrument_id="INST-EXPIRE-01",
            serial_number="SN-EXP-01",
            manufacturer="Mfr",
            model_name="Model",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
            status=InstrumentStatus.ACTIVE,
            next_re_verification_due="2026-08-01", # Past deadline
        )

        status = InstrumentLifecycleManager.evaluate_operational_status(inst, as_of_date="2026-09-17")
        self.assertEqual(status, InstrumentStatus.RE_VERIFICATION_DUE)

    def test_03_broken_seal_invalidates_commercial_use(self):
        """
        Verify that a broken statutory seal immediately transitions instrument
        status to REPAIR_REQUIRED under Section 24 of the Legal Metrology Act, 2009.
        """
        inst = self.instruments.get("INST-RETAIL-001")
        self.assertEqual(inst.status, InstrumentStatus.ACTIVE)
        self.assertGreater(len(inst.seals), 0)

        # Break seal
        ok, msg = InstrumentLifecycleManager.report_broken_seal(
            instrument=inst,
            seal_id="SEAL-001",
            reason="Lead wire snapped during platform cleaning",
            reported_by="Store Manager",
        )
        self.assertTrue(ok)
        self.assertEqual(inst.status, InstrumentStatus.REPAIR_REQUIRED)

        # Seal state updated
        broken_seal = next(s for s in inst.seals if s.seal_id == "SEAL-001")
        self.assertEqual(broken_seal.status, SealStatus.BROKEN)
        self.assertIsNotNone(broken_seal.broken_date)

    def test_04_job_state_machine_valid_progression(self):
        """Verify sequential progression through all statutory job verification gates."""
        job = TestJob(
            job_id="JOB-SEQ-001",
            instrument_id="INST-RETAIL-001",
            job_type=JobType.RE_VERIFICATION,
            status=JobStatus.DRAFT,
        )

        # 1. DRAFT -> VALIDATED
        JobStateMachine.transition(job, JobStatus.VALIDATED, user_id="INSP-1", reason="Metrology validated")
        self.assertEqual(job.status, JobStatus.VALIDATED)

        # 2. VALIDATED -> PLAN_GENERATED
        JobStateMachine.transition(job, JobStatus.PLAN_GENERATED, user_id="INSP-1", reason="Test plan attached")
        self.assertEqual(job.status, JobStatus.PLAN_GENERATED)

        # 3. PLAN_GENERATED -> ASSIGNED
        JobStateMachine.transition(job, JobStatus.ASSIGNED, user_id="ADMIN", reason="Inspector assigned")
        self.assertEqual(job.status, JobStatus.ASSIGNED)

        # 4. ASSIGNED -> IN_PROGRESS
        JobStateMachine.transition(job, JobStatus.IN_PROGRESS, user_id="INSP-1", reason="Testing begun")
        self.assertEqual(job.status, JobStatus.IN_PROGRESS)

        # 5. IN_PROGRESS -> TESTS_COMPLETED
        JobStateMachine.transition(job, JobStatus.TESTS_COMPLETED, user_id="INSP-1", reason="All loads tested")
        self.assertEqual(job.status, JobStatus.TESTS_COMPLETED)

        # 6. TESTS_COMPLETED -> SUBMITTED_FOR_REVIEW
        JobStateMachine.transition(job, JobStatus.SUBMITTED_FOR_REVIEW, user_id="INSP-1", reason="Submitted")
        self.assertEqual(job.status, JobStatus.SUBMITTED_FOR_REVIEW)

        # 7. SUBMITTED_FOR_REVIEW -> APPROVED
        JobStateMachine.transition(job, JobStatus.APPROVED, user_id="REVIEWER", reason="All observations verified")
        self.assertEqual(job.status, JobStatus.APPROVED)

        # 8. APPROVED -> CERTIFIED
        JobStateMachine.transition(job, JobStatus.CERTIFIED, user_id="DIRECTOR", reason="Certificate issued")
        self.assertEqual(job.status, JobStatus.CERTIFIED)
        self.assertIsNotNone(job.completed_at)

        # 8 state transition records created
        self.assertEqual(len(job.state_history), 8)

    def test_05_job_state_machine_illegal_transition(self):
        """Verify that skipping lifecycle states raises JobStateTransitionError."""
        job = TestJob(
            job_id="JOB-JUMP-001",
            instrument_id="INST-RETAIL-001",
            status=JobStatus.DRAFT,
        )

        with self.assertRaises(JobStateTransitionError):
            JobStateMachine.transition(job, JobStatus.CERTIFIED, reason="Illegal jump from DRAFT to CERTIFIED")

    def test_06_certification_updates_instrument_state(self):
        """
        Verify that when a test job is certified, TestJobService:
        1. Transitions job to CERTIFIED.
        2. Sets instrument status to ACTIVE.
        3. Updates last_verification_date, certificate number, and next_re_verification_due.
        """
        payload = {
            "job_id": "JOB-CERT-01",
            "instrument_id": "INST-RETAIL-001",
            "job_type": "RE_VERIFICATION",
        }
        self.service.create_job(payload)

        # Move to APPROVED
        job = self.jobs.get("JOB-CERT-01")
        JobStateMachine.transition(job, JobStatus.IN_PROGRESS)
        JobStateMachine.transition(job, JobStatus.TESTS_COMPLETED)
        JobStateMachine.transition(job, JobStatus.SUBMITTED_FOR_REVIEW)
        JobStateMachine.transition(job, JobStatus.APPROVED)
        self.jobs.save(job)

        # Transition to CERTIFIED via service
        cert_metadata = {
            "certificate_number": "KA-VER-2026-9999",
            "inspecting_officer": "Insp. V. Sharma",
            "stamping_authority": "Government Approved Test Centre",
            "fee_charged_inr": 500.0,
        }
        res = self.service.transition_job_status(
            job_id="JOB-CERT-01",
            to_status="CERTIFIED",
            user_id="OFFICER-1",
            reason="Full compliance achieved; stamping seal applied.",
            metadata=cert_metadata,
        )
        self.assertTrue(res["success"])

        # Check Instrument state
        inst = self.instruments.get("INST-RETAIL-001")
        self.assertEqual(inst.status, InstrumentStatus.ACTIVE)
        self.assertEqual(inst.last_verification_certificate, "KA-VER-2026-9999")
        self.assertIsNotNone(inst.last_verification_date)
        self.assertIsNotNone(inst.next_re_verification_due)

    def test_07_full_twelve_event_lifecycle_progression(self):
        """
        Verify sequential progression across all 12 Legal Metrology lifecycle events:
        1. Registration
        2. Model approval association
        3. Initial verification
        4. In-service use
        5. Periodic re-verification
        6. Repair
        7. Post-repair re-verification
        8. Dismantling
        9. Relocation
        10. Reinstallation
        11. Post-relocation/reinstallation verification
        12. Retirement
        """
        inst = Instrument(
            instrument_id="INST-PROG-001",
            serial_number="SN-PROG-001",
            manufacturer="Essae-Teraoka",
            model_name="DS-215",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
            instrument_type=InstrumentType.ELECTRONIC_COUNTER_SCALE,
            status=InstrumentStatus.REGISTERED,
        )

        # 1. Registration event
        ev1 = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.REGISTRATION,
            new_status=InstrumentStatus.REGISTERED,
            actor="Manufacturer / Dealer",
            event_date="2026-01-01",
            notes="Instrument physically manufactured and registered in system",
        )
        self.assertEqual(inst.status, InstrumentStatus.REGISTERED)
        self.assertEqual(inst.registered_date, "2026-01-01")

        # 2. Model approval association
        ev2 = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.MODEL_APPROVAL_ASSOCIATION,
            new_status=InstrumentStatus.READY,
            actor="Regulatory Compliance Officer",
            notes="Associated with Model Approval IND/09/2026/101",
        )
        self.assertEqual(inst.status, InstrumentStatus.READY)

        # 3. Initial verification
        ev3a = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.INITIAL_VERIFICATION,
            new_status=InstrumentStatus.IN_VERIFICATION,
            actor="Legal Metrology Inspector",
            notes="Initial verification under way",
        )
        ev3b = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.INITIAL_VERIFICATION,
            new_status=InstrumentStatus.VERIFIED,
            actor="Legal Metrology Inspector",
            notes="Initial verification passed, lead seal affixed",
        )
        self.assertEqual(inst.status, InstrumentStatus.VERIFIED)

        # 4. In-service use
        ev4 = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.IN_SERVICE_USE,
            new_status=InstrumentStatus.IN_SERVICE,
            actor="Retail Store Owner",
            notes="Deployed at billing counter for commercial trade",
        )
        self.assertEqual(inst.status, InstrumentStatus.IN_SERVICE)

        # 5. Periodic re-verification
        ev5a = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.PERIODIC_RE_VERIFICATION,
            new_status=InstrumentStatus.RE_VERIFICATION_DUE,
            actor="Automated Scheduler",
            notes="12-month re-verification deadline approached",
        )
        ev5b = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.PERIODIC_RE_VERIFICATION,
            new_status=InstrumentStatus.IN_VERIFICATION,
            actor="Legal Metrology Officer",
            notes="Periodic testing commenced",
        )
        ev5c = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.PERIODIC_RE_VERIFICATION,
            new_status=InstrumentStatus.VERIFIED,
            actor="Legal Metrology Officer",
            notes="Periodic testing certified",
        )
        ev5d = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.IN_SERVICE_USE,
            new_status=InstrumentStatus.IN_SERVICE,
            actor="Legal Metrology Officer",
            notes="Returned to commercial use",
        )
        self.assertEqual(inst.status, InstrumentStatus.IN_SERVICE)

        # 6. Repair
        ev6 = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.REPAIR,
            new_status=InstrumentStatus.REPAIR,
            actor="Licensed Repairer",
            event_date="2026-06-15",
            notes="Load cell cable replaced",
        )
        self.assertEqual(inst.status, InstrumentStatus.REPAIR)
        self.assertEqual(inst.repair_date, "2026-06-15")

        # 7. Post-repair re-verification
        ev7a = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.POST_REPAIR_VERIFICATION,
            new_status=InstrumentStatus.POST_REPAIR_VERIFICATION,
            actor="Licensed Repairer",
            notes="Repair finished, awaiting verification",
        )
        ev7b = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.POST_REPAIR_VERIFICATION,
            new_status=InstrumentStatus.VERIFIED,
            actor="Legal Metrology Officer",
            notes="Post-repair verification passed",
        )
        ev7c = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.IN_SERVICE_USE,
            new_status=InstrumentStatus.IN_SERVICE,
            actor="Legal Metrology Officer",
            notes="Restored to service",
        )
        self.assertEqual(inst.status, InstrumentStatus.IN_SERVICE)

        # 8. Dismantling
        ev8 = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.DISMANTLING,
            new_status=InstrumentStatus.DISMANTLED,
            actor="Authorized Technician",
            event_date="2026-08-01",
            notes="Dismantled for premise shifting",
        )
        self.assertEqual(inst.status, InstrumentStatus.DISMANTLED)
        self.assertEqual(inst.dismantled_date, "2026-08-01")

        # 9. Relocation
        ev9 = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.RELOCATION,
            new_status=InstrumentStatus.RELOCATED,
            actor="Authorized Logistics",
            notes="Transported to new branch location",
        )
        self.assertEqual(inst.status, InstrumentStatus.RELOCATED)

        # 10. Reinstallation
        ev10 = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.REINSTALLATION,
            new_status=InstrumentStatus.REINSTALLED,
            actor="Authorized Technician",
            event_date="2026-08-10",
            notes="Reinstalled on level anti-vibration bench at new branch",
        )
        self.assertEqual(inst.status, InstrumentStatus.REINSTALLED)
        self.assertEqual(inst.reinstalled_date, "2026-08-10")

        # 11. Post-relocation/reinstallation verification
        ev11a = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.POST_RELOCATION_VERIFICATION,
            new_status=InstrumentStatus.VERIFICATION_REQUIRED,
            actor="Compliance Officer",
            notes="Statutory requirement: must be reverified after relocation",
        )
        ev11b = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.POST_RELOCATION_VERIFICATION,
            new_status=InstrumentStatus.IN_VERIFICATION,
            actor="Local Legal Metrology Officer",
            notes="In-situ reverification testing",
        )
        ev11c = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.POST_RELOCATION_VERIFICATION,
            new_status=InstrumentStatus.VERIFIED,
            actor="Local Legal Metrology Officer",
            notes="Passed in-situ verification, new seal affixed",
        )
        ev11d = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.IN_SERVICE_USE,
            new_status=InstrumentStatus.IN_SERVICE,
            actor="Local Legal Metrology Officer",
            notes="Restored to commercial service",
        )
        self.assertEqual(inst.status, InstrumentStatus.IN_SERVICE)

        # 12. Retirement
        ev12 = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.RETIREMENT,
            new_status=InstrumentStatus.RETIRED,
            actor="Owner / Legal Metrology Officer",
            event_date="2035-12-31",
            notes="Permanent retirement after 10 years in trade",
        )
        self.assertEqual(inst.status, InstrumentStatus.RETIRED)
        self.assertEqual(inst.retired_date, "2035-12-31")

        # Total events recorded in immutable audit log
        history = InstrumentLifecycleManager.get_lifecycle_history(inst)
        self.assertEqual(len(history), 21)
        self.assertEqual(len(inst.lifecycle_events), 21)

    def test_08_invalid_lifecycle_state_transitions(self):
        """Verify that illegal and non-sensible lifecycle state jumps are rejected."""
        inst = Instrument(
            instrument_id="INST-ILLEGAL-01",
            serial_number="SN-ILL-01",
            manufacturer="Generic",
            model_name="M1",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
            instrument_type=InstrumentType.ELECTRONIC_COUNTER_SCALE,
            status=InstrumentStatus.REGISTERED,
        )

        # 1. REGISTERED -> IN_SERVICE directly (must verify first)
        can_reg_to_ins, reason = InstrumentLifecycleStateMachine.can_transition(
            InstrumentStatus.REGISTERED, InstrumentStatus.IN_SERVICE
        )
        self.assertFalse(can_reg_to_ins)
        with self.assertRaises(InstrumentLifecycleTransitionError):
            InstrumentLifecycleManager.record_lifecycle_event(
                instrument=inst,
                event_type=LifecycleEventType.IN_SERVICE_USE,
                new_status=InstrumentStatus.IN_SERVICE,
            )

        # 2. DISMANTLED -> IN_SERVICE directly (must reinstall and re-verify first)
        inst.status = InstrumentStatus.DISMANTLED
        can_dism_to_ins, _ = InstrumentLifecycleStateMachine.can_transition(
            InstrumentStatus.DISMANTLED, InstrumentStatus.IN_SERVICE
        )
        self.assertFalse(can_dism_to_ins)
        with self.assertRaises(InstrumentLifecycleTransitionError):
            InstrumentLifecycleManager.record_lifecycle_event(
                instrument=inst,
                event_type=LifecycleEventType.IN_SERVICE_USE,
                new_status=InstrumentStatus.IN_SERVICE,
            )

        # 3. RETIRED is terminal -> any transition must fail
        inst.status = InstrumentStatus.RETIRED
        for target in [InstrumentStatus.IN_SERVICE, InstrumentStatus.IN_VERIFICATION, InstrumentStatus.READY, InstrumentStatus.REPAIR]:
            can_ret, ret_reason = InstrumentLifecycleStateMachine.can_transition(
                InstrumentStatus.RETIRED, target
            )
            self.assertFalse(can_ret)
            self.assertIn("Terminal state", ret_reason)
            with self.assertRaises(InstrumentLifecycleTransitionError):
                InstrumentLifecycleManager.record_lifecycle_event(
                    instrument=inst,
                    event_type=LifecycleEventType.IN_SERVICE_USE,
                    new_status=target,
                )

    def test_09_lifecycle_history_immutability_and_serialization(self):
        """Verify immutable event recording and complete JSON round-trip serialization."""
        inst = Instrument(
            instrument_id="INST-IMMUT-01",
            serial_number="SN-IMMUT-01",
            manufacturer="Essae",
            model_name="DS-215",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
            instrument_type=InstrumentType.ELECTRONIC_COUNTER_SCALE,
            status=InstrumentStatus.REGISTERED,
        )

        ev = InstrumentLifecycleManager.record_lifecycle_event(
            instrument=inst,
            event_type=LifecycleEventType.REGISTRATION,
            new_status=InstrumentStatus.REGISTERED,
            actor="Officer Verma",
            event_date="2026-02-01",
            related_job_id="JOB-INIT-01",
            notes="Factory initial entry",
            metadata={"batch_number": "B-2026-01"},
        )

        self.assertEqual(len(inst.lifecycle_events), 1)
        self.assertEqual(inst.lifecycle_events[0].actor, "Officer Verma")
        self.assertEqual(inst.lifecycle_events[0].related_job_id, "JOB-INIT-01")
        self.assertEqual(inst.lifecycle_events[0].metadata["batch_number"], "B-2026-01")

        # Verify get_lifecycle_history returns a distinct copy list
        history = InstrumentLifecycleManager.get_lifecycle_history(inst)
        self.assertEqual(len(history), 1)
        history.clear()
        self.assertEqual(len(inst.lifecycle_events), 1)  # Internal list unmodified

        # Round-trip serialization
        inst_dict = inst.to_dict()
        self.assertIn("lifecycle_events", inst_dict)
        self.assertEqual(len(inst_dict["lifecycle_events"]), 1)
        self.assertEqual(inst_dict["lifecycle_events"][0]["event_type"], "REGISTRATION")

        restored = Instrument.from_dict(inst_dict)
        self.assertEqual(len(restored.lifecycle_events), 1)
        restored_ev = restored.lifecycle_events[0]
        self.assertEqual(restored_ev.event_id, ev.event_id)
        self.assertEqual(restored_ev.event_type, LifecycleEventType.REGISTRATION)
        self.assertEqual(restored_ev.actor, "Officer Verma")
        self.assertEqual(restored_ev.metadata["batch_number"], "B-2026-01")

    def test_10_instrument_service_lifecycle_management(self):
        """Verify InstrumentService recording of lifecycle transitions and query endpoints."""
        inst_service = InstrumentService(registry=InstrumentRegistry())
        payload = {
            "instrument_id": "INST-SVC-LC-01",
            "serial_number": "SN-SVC-LC-01",
            "manufacturer": "Essae-Teraoka Ltd.",
            "model_name": "DS-215",
            "accuracy_class": "CLASS_III",
            "max_capacity": 30.0,
            "min_capacity": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "instrument_type": "ELECTRONIC_COUNTER_SCALE",
            "model_approval_number": "IND/09/2024/001",
        }
        res_create = inst_service.create_instrument(payload)
        self.assertTrue(res_create["success"])

        # Instrument auto-records registration and model approval
        hist_res = inst_service.get_instrument_lifecycle_history("INST-SVC-LC-01")
        self.assertTrue(hist_res["success"])
        self.assertGreaterEqual(hist_res["count"], 2)

        # Record valid transition via service: READY -> IN_VERIFICATION
        res_trans = inst_service.record_lifecycle_event(
            instrument_id="INST-SVC-LC-01",
            event_type=LifecycleEventType.INITIAL_VERIFICATION,
            new_status=InstrumentStatus.IN_VERIFICATION,
            actor="Inspector Sharma",
            notes="Initial stamping started",
        )
        self.assertTrue(res_trans["success"])
        self.assertEqual(res_trans["instrument_status"], "IN_VERIFICATION")

        # Record invalid transition via service: IN_VERIFICATION -> DISMANTLED is not allowed
        res_inv = inst_service.record_lifecycle_event(
            instrument_id="INST-SVC-LC-01",
            event_type=LifecycleEventType.DISMANTLING,
            new_status=InstrumentStatus.DISMANTLED,
            actor="Inspector Sharma",
            notes="Illegal skip to dismantled during active testing",
        )
        self.assertFalse(res_inv["success"])
        self.assertEqual(res_inv["status_code"], 400)
        self.assertIn("Invalid instrument state transition", res_inv["message"])

        # History should have 3 successful events recorded
        final_hist = inst_service.get_instrument_lifecycle_history("INST-SVC-LC-01")
        self.assertEqual(final_hist["count"], 3)


if __name__ == "__main__":
    unittest.main()
