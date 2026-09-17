"""
MetrIQ Person 3 Test Suite — Verification & Re-verification Scheduling
======================================================================
Tests statutory verification scheduling, deadline tracking, due/overdue
evaluation, post-repair & post-relocation triggers, unverified profile isolation,
state jurisdiction resolution, and post-job status synchronization.
"""

import os
import sys
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.regulatory.models import AccuracyClass, JobType, MassUnit
from app.regulatory.profile import PROFILE_REGISTRY, ProfileStatus
from app.instruments.models import (
    CustomerLocation,
    Instrument,
    InstrumentStatus,
    InstrumentType,
    PhysicalSeal,
    SealStatus,
    SealType,
    VerificationReason,
    VerificationStatus,
)
from app.instruments.registry import InstrumentRegistry
from app.instruments.scheduling import VerificationScheduler
from app.instruments.service import InstrumentService
from app.jobs.models import JobPriority, JobStatus, TestJob
from app.jobs.repository import TestJobRepository
from app.jobs.service import TestJobService


class TestP3Scheduling(unittest.TestCase):
    """Unit and integration test suite for Verification & Re-verification Scheduling."""

    def setUp(self) -> None:
        self.instruments = InstrumentRegistry()
        self.instruments._instruments.clear()
        self.instruments._serial_index.clear()
        self.jobs = TestJobRepository()
        self.jobs._jobs.clear()
        self.job_service = TestJobService(
            job_repository=self.jobs,
            instrument_registry=self.instruments,
        )
        self.scheduler = VerificationScheduler(
            instrument_registry=self.instruments,
            job_repository=self.jobs,
            job_service=self.job_service,
        )
        self.service = InstrumentService(
            registry=self.instruments,
            scheduler=self.scheduler,
        )

    def test_01_future_due_date(self):
        """
        Verify that an instrument with a future due date (> 30 days away):
        1. Remains in VERIFIED and ACTIVE status.
        2. Is NOT flagged as due.
        3. Is NOT listed as requiring periodic verification.
        """
        inst = Instrument(
            instrument_id="INST-FUT-01",
            serial_number="SN-FUT-01",
            manufacturer="Essae-Teraoka",
            model_name="DS-215",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
            instrument_type=InstrumentType.ELECTRONIC_COUNTER_SCALE,
            status=InstrumentStatus.ACTIVE,
            verification_status=VerificationStatus.VERIFIED,
            last_verification_date="2026-03-01",
            next_re_verification_due="2027-03-01",  # ~5.5 months in future
        )
        self.instruments.register(inst)

        is_due, msg = self.scheduler.flag_verification_due(inst, as_of_date="2026-09-17")
        self.assertFalse(is_due)
        self.assertEqual(inst.verification_status, VerificationStatus.VERIFIED)
        self.assertEqual(inst.status, InstrumentStatus.ACTIVE)
        self.assertIn("in the future", msg)

        # Check identify query
        req = self.scheduler.identify_instruments_requiring_verification(as_of_date="2026-09-17")
        self.assertEqual(req["summary"]["periodic_due"], 0)
        self.assertEqual(req["summary"]["periodic_overdue"], 0)

    def test_02_due_today(self):
        """
        Verify that an instrument whose next verification date matches as_of_date:
        1. Is flagged as due (is_due=True).
        2. Status transitions to DUE and RE_VERIFICATION_DUE.
        3. scheduling_metadata records due_today=True and days_until_due=0.
        4. identify_instruments_requiring_verification includes it under periodic_due.
        """
        inst = Instrument(
            instrument_id="INST-DUE-TODAY",
            serial_number="SN-DUE-01",
            manufacturer="Avery India",
            model_name="Counter Scale",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=30.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
            instrument_type=InstrumentType.ELECTRONIC_COUNTER_SCALE,
            status=InstrumentStatus.ACTIVE,
            verification_status=VerificationStatus.VERIFIED,
            last_verification_date="2025-09-17",
            next_re_verification_due="2026-09-17",  # Today
        )
        self.instruments.register(inst)

        is_due, msg = self.scheduler.flag_verification_due(inst, as_of_date="2026-09-17")
        self.assertTrue(is_due)
        self.assertEqual(inst.verification_status, VerificationStatus.DUE)
        self.assertEqual(inst.status, InstrumentStatus.RE_VERIFICATION_DUE)
        self.assertTrue(inst.scheduling_metadata.get("due_today"))
        self.assertEqual(inst.scheduling_metadata.get("days_until_due"), 0)
        self.assertIn("due today", msg.lower())

        # Check identify query
        req = self.scheduler.identify_instruments_requiring_verification(as_of_date="2026-09-17")
        self.assertEqual(req["summary"]["periodic_due"], 1)
        item = req["instruments"][0]
        self.assertEqual(item["instrument_id"], "INST-DUE-TODAY")
        self.assertEqual(item["verification_reason"], VerificationReason.PERIODIC_EXPIRY.value)

    def test_03_overdue(self):
        """
        Verify that an instrument past its next verification date:
        1. Is flagged as overdue with calculated days_overdue.
        2. Status transitions to OVERDUE and RE_VERIFICATION_DUE.
        3. identify_instruments_requiring_verification lists it with urgency=HIGH.
        """
        inst = Instrument(
            instrument_id="INST-OVERDUE-01",
            serial_number="SN-OVD-01",
            manufacturer="Essae",
            model_name="DS-215",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
            instrument_type=InstrumentType.ELECTRONIC_COUNTER_SCALE,
            status=InstrumentStatus.ACTIVE,
            verification_status=VerificationStatus.VERIFIED,
            last_verification_date="2025-07-01",
            next_re_verification_due="2026-07-01",  # Expired ~78 days ago relative to 2026-09-17
        )
        self.instruments.register(inst)

        is_ovd, msg = self.scheduler.flag_overdue(inst, as_of_date="2026-09-17")
        self.assertTrue(is_ovd)
        self.assertEqual(inst.verification_status, VerificationStatus.OVERDUE)
        self.assertEqual(inst.status, InstrumentStatus.RE_VERIFICATION_DUE)
        self.assertGreater(inst.scheduling_metadata["days_overdue"], 70)
        self.assertIn("OVERDUE", msg)

        # Check identify query
        req = self.scheduler.identify_instruments_requiring_verification(as_of_date="2026-09-17")
        self.assertEqual(req["summary"]["periodic_overdue"], 1)
        item = req["instruments"][0]
        self.assertEqual(item["urgency"], "HIGH")
        self.assertEqual(item["verification_reason"], VerificationReason.PERIODIC_EXPIRY.value)

    def test_04_post_repair_verification(self):
        """
        Verify statutory post-repair verification handling:
        1. Breaking a seal transitions instrument to REPAIR_REQUIRED.
        2. identify_instruments_requiring_verification flags it as POST_REPAIR with urgency=HIGH.
        3. create_verification_job provisions a POST_REPAIR job and updates instrument status to UNDER_INSPECTION.
        """
        inst = Instrument(
            instrument_id="INST-RETAIL-001",
            serial_number="SN-RET-01",
            manufacturer="Essae",
            model_name="DS-215",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
            instrument_type=InstrumentType.ELECTRONIC_COUNTER_SCALE,
            status=InstrumentStatus.ACTIVE,
            verification_status=VerificationStatus.VERIFIED,
            seals=[
                PhysicalSeal(
                    seal_id="SEAL-01",
                    seal_type=SealType.LEAD_AND_WIRE,
                    seal_number="LMD-SEAL-101",
                    location="Calibration Port",
                    applied_date="2026-01-01",
                    applied_by="Officer Sharma",
                    status=SealStatus.INTACT,
                )
            ],
        )
        self.instruments.register(inst)

        # Break seal under Section 24
        inst.status = InstrumentStatus.REPAIR_REQUIRED
        inst.seals[0].status = SealStatus.BROKEN
        inst.repair_date = "2026-09-10"
        self.instruments.update(inst)

        # Identify requiring verification
        req = self.scheduler.identify_instruments_requiring_verification(as_of_date="2026-09-17")
        repair_items = [i for i in req["instruments"] if i["instrument_id"] == "INST-RETAIL-001"]
        self.assertEqual(len(repair_items), 1)
        self.assertEqual(repair_items[0]["verification_reason"], VerificationReason.POST_REPAIR.value)
        self.assertEqual(repair_items[0]["recommended_job_type"], JobType.POST_REPAIR.value)
        self.assertEqual(repair_items[0]["urgency"], "HIGH")

        # Provision post-repair verification job
        job_res = self.scheduler.create_verification_job(
            instrument_id="INST-RETAIL-001",
            job_type=JobType.POST_REPAIR,
            reason=VerificationReason.POST_REPAIR,
            scheduled_date="2026-09-18",
            user_id="OFFICER-REPAIR",
        )
        self.assertTrue(job_res["success"])
        self.assertEqual(job_res["priority"], "HIGH")
        self.assertEqual(job_res["verification_status"], "UNDER_INSPECTION")

        # Verify instrument linked active job
        updated_inst = self.instruments.get("INST-RETAIL-001")
        self.assertEqual(updated_inst.active_verification_job_id, job_res["job_id"])
        self.assertEqual(updated_inst.verification_status, VerificationStatus.UNDER_INSPECTION)

    def test_05_post_relocation_verification(self):
        """
        Verify post-relocation and reinstallation statutory verification:
        1. An instrument with status RELOCATED or REINSTALLED requires in-situ verification.
        2. identify_instruments_requiring_verification flags it as POST_RELOCATION.
        3. create_verification_job provisions a POST_RELOCATION job.
        """
        inst = Instrument(
            instrument_id="INST-RELOC-01",
            serial_number="SN-RELOC-01",
            manufacturer="Avery",
            model_name="Bench Scale",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=50.0,
            min_capacity=0.2,
            e=0.01,
            d=0.01,
            unit=MassUnit.KG,
            instrument_type=InstrumentType.BENCH_SCALE,
            status=InstrumentStatus.REINSTALLED,
            reinstalled_date="2026-09-15",
            last_verification_date="2026-01-01",
        )
        self.instruments.register(inst)

        req = self.scheduler.identify_instruments_requiring_verification(as_of_date="2026-09-17")
        reloc_items = [i for i in req["instruments"] if i["instrument_id"] == "INST-RELOC-01"]
        self.assertEqual(len(reloc_items), 1)
        self.assertEqual(reloc_items[0]["verification_reason"], VerificationReason.POST_REINSTALLATION.value)
        self.assertEqual(reloc_items[0]["recommended_job_type"], JobType.POST_RELOCATION.value)
        self.assertEqual(reloc_items[0]["urgency"], "HIGH")

        # Provision verification job
        job_res = self.scheduler.create_verification_job(
            instrument_id="INST-RELOC-01",
            job_type=JobType.POST_RELOCATION,
            reason=VerificationReason.POST_RELOCATION,
            scheduled_date="2026-09-20",
        )
        self.assertTrue(job_res["success"])
        self.assertEqual(job_res["job_type"], "POST_RELOCATION")

    def test_06_missing_interval_and_manual_review(self):
        """
        Verify that uncertain or unverified regulatory profiles trigger MANUAL_REVIEW:
        1. When calling calculate_and_store_next_verification_date with IN_LM_2026_GSR568E_DRAFT
           (which has ProfileStatus.MANUAL_REVIEW and is_authoritative=False), the system
           does NOT guess or invent a legal period.
        2. Flags manual_review_required=True and verification_status=MANUAL_REVIEW_REQUIRED.
        3. identify_instruments_requiring_verification categorizes it under manual_review.
        """
        inst = Instrument(
            instrument_id="INST-UNVERIF-01",
            serial_number="SN-UNV-01",
            manufacturer="Generic",
            model_name="Draft Model",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
            instrument_type=InstrumentType.ELECTRONIC_COUNTER_SCALE,
        )
        self.instruments.register(inst)

        # Attempt to calculate with unverified 2026 draft profile
        res = self.scheduler.calculate_and_store_next_verification_date(
            instrument=inst,
            profile_id="IN_LM_2026_GSR568E_DRAFT",
        )
        self.assertFalse(res["success"])
        self.assertTrue(res["manual_review_required"])
        self.assertEqual(inst.verification_status, VerificationStatus.MANUAL_REVIEW_REQUIRED)
        self.assertTrue(inst.manual_review_required)
        self.assertIn("not authoritative law", inst.manual_review_reason)

        # Check identify query includes manual review
        req = self.scheduler.identify_instruments_requiring_verification(as_of_date="2026-09-17")
        self.assertGreaterEqual(req["summary"]["manual_review"], 1)
        mr_items = [i for i in req["instruments"] if i["instrument_id"] == "INST-UNVERIF-01"]
        self.assertEqual(len(mr_items), 1)
        self.assertEqual(mr_items[0]["verification_reason"], VerificationReason.MANUAL_REVIEW.value)

        # Test non-existent profile ID also triggers manual review
        res_non = self.scheduler.calculate_and_store_next_verification_date(
            instrument=inst,
            profile_id="NON_EXISTENT_PROFILE_999",
        )
        self.assertFalse(res_non["success"])
        self.assertTrue(res_non["manual_review_required"])

    def test_07_state_location_specific_scheduling(self):
        """
        Verify state jurisdiction resolution and state filtering:
        1. An instrument located in Maharashtra automatically resolves the STATE_MAHARASHTRA_2026 profile.
        2. identify_instruments_requiring_verification(state="MAHARASHTRA") filters appropriately.
        """
        inst_mh = Instrument(
            instrument_id="INST-MH-PUNE-01",
            serial_number="SN-MH-01",
            manufacturer="Essae-Teraoka",
            model_name="DS-215",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=30.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
            instrument_type=InstrumentType.ELECTRONIC_COUNTER_SCALE,
            location=CustomerLocation(
                customer_name="Pune Sugar Mills Ltd.",
                city="Pune",
                state="MAHARASHTRA",
            ),
            last_verification_date="2026-01-15",
        )
        self.instruments.register(inst_mh)

        # Calculate next verification date without explicit profile_id -> auto-resolves Maharashtra profile
        res_sched = self.scheduler.calculate_and_store_next_verification_date(inst_mh)
        self.assertTrue(res_sched["success"])
        self.assertEqual(res_sched["profile_id"], "STATE_MAHARASHTRA_2026")
        self.assertEqual(inst_mh.next_verification_date, "2027-01-15")

        # Test state filtering in identify query
        req_mh = self.scheduler.identify_instruments_requiring_verification(state="MAHARASHTRA")
        for item in req_mh["instruments"]:
            self.assertEqual(item["state"].upper(), "MAHARASHTRA")

    def test_08_post_job_completion_and_rescheduling(self):
        """
        Verify status updates and automatic re-scheduling upon job completion:
        1. Create verification job.
        2. Complete job with PASSED outcome.
        3. Verify instrument is returned to IN_SERVICE and VERIFIED.
        4. Verify next_verification_date is automatically calculated and stored for next cycle.
        5. Verify lifecycle event is recorded.
        6. Test REJECTED outcome sets status to REPAIR_REQUIRED.
        """
        inst = Instrument(
            instrument_id="INST-JOB-COMP-01",
            serial_number="SN-JCOMP-01",
            manufacturer="Essae-Teraoka",
            model_name="DS-215",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
            instrument_type=InstrumentType.ELECTRONIC_COUNTER_SCALE,
            status=InstrumentStatus.READY,
            verification_status=VerificationStatus.UNVERIFIED,
        )
        self.instruments.register(inst)

        # 1. Create Job
        job_res = self.scheduler.create_verification_job(
            instrument_id="INST-JOB-COMP-01",
            job_type=JobType.INITIAL_VERIFICATION,
            reason=VerificationReason.INITIAL_STAMPING,
            user_id="OFFICER-INIT",
        )
        job_id = job_res["job_id"]
        self.assertEqual(inst.verification_status, VerificationStatus.UNDER_INSPECTION)

        # 2. Complete Job: PASSED
        comp_res = self.scheduler.update_verification_status_after_job(
            job_id=job_id,
            outcome="PASSED",
            certificate_number="IND-KA-2026-5555",
            verification_date="2026-09-17",
            inspecting_officer="Insp. K. Rao",
            stamping_authority="Bangalore Legal Metrology Div",
        )
        self.assertTrue(comp_res["success"])
        self.assertEqual(comp_res["outcome"], "PASSED")
        self.assertEqual(comp_res["verification_status"], "VERIFIED")
        self.assertEqual(comp_res["operational_status"], "IN_SERVICE")
        self.assertEqual(comp_res["last_verification_date"], "2026-09-17")
        self.assertEqual(comp_res["next_verification_date"], "2027-09-17")  # 12 months later

        # Check instrument state in registry
        saved = self.instruments.get("INST-JOB-COMP-01")
        self.assertEqual(saved.status, InstrumentStatus.IN_SERVICE)
        self.assertIsNone(saved.active_verification_job_id)
        self.assertEqual(saved.last_verification_job_id, job_id)
        self.assertEqual(saved.last_verification_certificate, "IND-KA-2026-5555")

        # 3. Complete another job: REJECTED
        inst_rej = Instrument(
            instrument_id="INST-REJ-01",
            serial_number="SN-REJ-01",
            manufacturer="Essae",
            model_name="DS-215",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
            instrument_type=InstrumentType.ELECTRONIC_COUNTER_SCALE,
        )
        self.instruments.register(inst_rej)

        job_rej = self.scheduler.create_verification_job(
            instrument_id="INST-REJ-01",
            job_type=JobType.RE_VERIFICATION,
            reason=VerificationReason.PERIODIC_EXPIRY,
        )
        rej_res = self.scheduler.update_verification_status_after_job(
            job_id=job_rej["job_id"],
            outcome="REJECTED",
            inspecting_officer="Insp. K. Rao",
        )
        self.assertTrue(rej_res["success"])
        self.assertEqual(rej_res["outcome"], "REJECTED")
        self.assertEqual(rej_res["verification_status"], "REJECTED")
        self.assertEqual(rej_res["operational_status"], "REPAIR_REQUIRED")

    def test_09_scheduling_via_service_facade(self):
        """Verify scheduling methods through the InstrumentService facade."""
        inst = Instrument(
            instrument_id="INST-FACADE-01",
            serial_number="SN-FAC-01",
            manufacturer="Essae-Teraoka",
            model_name="DS-215",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
            instrument_type=InstrumentType.ELECTRONIC_COUNTER_SCALE,
            last_verification_date="2026-09-01",
        )
        self.instruments.register(inst)

        # Schedule
        sched_res = self.service.schedule_verification("INST-FACADE-01")
        self.assertTrue(sched_res["success"])
        self.assertEqual(inst.next_verification_date, "2027-09-01")

        # Flag due (1 year in future -> not due)
        due_res = self.service.flag_verification_due("INST-FACADE-01", as_of_date="2026-09-17")
        self.assertFalse(due_res["is_due"])

        # Flag due when checking 1 year later (2027-08-20 -> within 30 days of 2027-09-01)
        due_later = self.service.flag_verification_due("INST-FACADE-01", as_of_date="2027-08-20")
        self.assertTrue(due_later["is_due"])
        self.assertEqual(due_later["verification_status"], "DUE")

        # Flag overdue when checking 2027-09-10
        ovd_later = self.service.flag_overdue("INST-FACADE-01", as_of_date="2027-09-10")
        self.assertTrue(ovd_later["is_overdue"])
        self.assertEqual(ovd_later["verification_status"], "OVERDUE")


if __name__ == "__main__":
    unittest.main()
