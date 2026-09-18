"""
MetrIQ Person 3 Test Suite — Verification Location & Statutory GATC Routing Integration
======================================================================================
Tests the clean pipeline:
    RegulatoryRoutingService (Consumes Person 2 GATC rules)
                ↓
    JobLocationService (Resolves locations, testing centres, installation premises)
                ↓
    TestJobService / TestJob Entity (Stores all statutory location & routing metadata)

Verifies:
1. Class III up to 150 kg -> Eligible for GATC, routes to GATC_CENTRE.
2. Class III above 150 kg -> NOT eligible for GATC, routes to STATE_LEGAL_METROLOGY_OFFICER (ON_SITE_INSTALLATION).
3. Class IIII -> Eligible for GATC across commercial capacities.
4. Class II -> NOT eligible for GATC (must be verified by State Legal Metrology Officer).
5. Statutory GATC violation rejection when assigning GATC to ineligible instruments.
6. Model Approval routing to CENTRAL_DIRECTORATE (CENTRAL_LABORATORY / CSIR-NPL).
7. Installation location inheritance from instrument.location.
8. Statutory rule citations and regulatory profile versioning.
9. Manual review flag triggers for unverified/draft profiles.
10. Full TestJob serialization round-trip preserving all 9 location/routing fields.
"""

import os
import sys
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.instruments.models import (
    AccuracyClass,
    Instrument,
    InstrumentLocation,
    MassUnit,
    VerificationReason,
    VerificationStatus,
)
from app.instruments.registry import InstrumentRegistry
from app.jobs.models import (
    JobStatus,
    JobType,
    StatutoryRoutingInfo,
    TestJob,
    VerificationLocationType,
)
from app.jobs.repository import TestJobRepository
from app.jobs.location_service import (
    JobLocationRoutingResult,
    JobLocationService,
    RegulatoryRoutingResult,
    RegulatoryRoutingService,
)
from app.jobs.service import TestJobService


class TestP3LocationRoutingIntegration(unittest.TestCase):
    """Verifies statutory location and GATC routing integration in Person 3."""

    def setUp(self):
        self.instruments = InstrumentRegistry()
        self.instruments._instruments.clear()
        self.instruments._serial_index.clear()

        self.jobs = TestJobRepository()
        self.jobs._jobs.clear()
        self.jobs._instrument_index.clear()

        self.routing_service = RegulatoryRoutingService()
        self.location_service = JobLocationService(routing_service=self.routing_service)
        self.job_service = TestJobService(
            job_repository=self.jobs,
            instrument_registry=self.instruments,
            location_service=self.location_service,
        )

    # -------------------------------------------------------------------------
    # Helper to register an instrument
    # -------------------------------------------------------------------------
    def _create_instrument(
        self,
        instrument_id: str,
        accuracy_class: AccuracyClass,
        max_capacity: float,
        unit: MassUnit = MassUnit.KG,
        min_capacity: float = 0.1,
        e: float = 0.005,
        d: float = 0.005,
        state: str = "Maharashtra",
        district: str = "Pune",
        customer_name: str = "Deccan Logistics Pvt Ltd",
    ) -> Instrument:
        loc = InstrumentLocation(
            customer_name=customer_name,
            site_name="Central Warehouse",
            address="Gate 4, MIDC Bhosari",
            district=district,
            state=state,
            pincode="411026",
        )
        inst = Instrument(
            instrument_id=instrument_id,
            serial_number=f"SN-{instrument_id}",
            manufacturer="Essae-Teraoka",
            model_name="DS-852",
            accuracy_class=accuracy_class,
            max_capacity=max_capacity,
            min_capacity=min_capacity,
            e=e,
            d=d,
            unit=unit,
            location=loc,
        )
        self.instruments.register(inst)
        return inst

    # =========================================================================
    # Test 1: Class III <= 150 kg (Eligible for GATC)
    # =========================================================================
    def test_01_class_iii_up_to_150kg_gatc_eligible(self):
        """
        Statutory Rule: Class III with Max <= 150 kg is fully authorized for
        GATC verification under the First Schedule of GATC Rules, 2013.
        P3 must consume P2's decision and route to GATC_CENTRE.
        """
        # 1. Metrology: 30 kg Class III retail bench scale
        inst = self._create_instrument(
            instrument_id="INST-CL3-30KG",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=30.0,
            unit=MassUnit.KG,
        )

        # 2. Evaluate statutory routing via RegulatoryRoutingService
        routing = self.routing_service.evaluate_routing(inst, job_type=JobType.RE_VERIFICATION)
        self.assertTrue(routing.eligible_for_gatc, "Class III <= 150 kg must be GATC eligible per P2")
        self.assertEqual(routing.target_authority, "GATC")
        self.assertEqual(routing.authority_name, "Government Approved Test Centre (GATC)")
        self.assertFalse(routing.manual_review_flag)
        self.assertIn("Government Approved Test Centre", routing.regulatory_rule_reference)

        # 3. Resolve location and routing via JobLocationService
        loc_res = self.location_service.resolve_job_location_and_routing(
            instrument=inst,
            job_type=JobType.RE_VERIFICATION,
            gatc_reference="GATC-MH-PUNE-01",
            testing_centre_name="Maharashtra Metrology GATC Lab",
        )
        self.assertEqual(loc_res.verification_location_type, VerificationLocationType.GATC_CENTRE.value)
        self.assertEqual(loc_res.gatc_reference, "GATC-MH-PUNE-01")
        self.assertEqual(loc_res.laboratory, "Maharashtra Metrology GATC Lab")
        self.assertEqual(loc_res.routing_decision, "GATC")

        # 4. Verify boundary case: Exactly 150 kg Class III
        inst_150 = self._create_instrument(
            instrument_id="INST-CL3-150KG",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=150.0,
            unit=MassUnit.KG,
        )
        routing_150 = self.routing_service.evaluate_routing(inst_150)
        self.assertTrue(routing_150.eligible_for_gatc, "Exact 150 kg boundary is GATC eligible")
        self.assertEqual(routing_150.target_authority, "GATC")

    # =========================================================================
    # Test 2: Class III > 150 kg (Exceeds GATC threshold -> State Officer)
    # =========================================================================
    def test_02_class_iii_above_150kg_state_officer_routed(self):
        """
        Statutory Rule: Class III with Max > 150 kg (e.g. 300 kg platform or
        50,000 kg weighbridge) exceeds GATC jurisdiction and must be verified
        directly by the State Legal Metrology Officer (on-site).
        """
        # 1. 300 kg platform scale
        inst_300 = self._create_instrument(
            instrument_id="INST-CL3-300KG",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=300.0,
            unit=MassUnit.KG,
        )
        routing_300 = self.routing_service.evaluate_routing(inst_300)
        self.assertFalse(routing_300.eligible_for_gatc, "Class III > 150 kg cannot be routed to GATC")
        self.assertEqual(routing_300.target_authority, "STATE_LEGAL_METROLOGY_OFFICER")

        # 2. 50,000 kg weighbridge
        inst_wb = self._create_instrument(
            instrument_id="INST-WB-50T",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=50000.0,
            unit=MassUnit.KG,
        )
        loc_wb = self.location_service.resolve_job_location_and_routing(
            instrument=inst_wb,
            job_type=JobType.RE_VERIFICATION,
        )
        self.assertEqual(loc_wb.routing_decision, "STATE_LEGAL_METROLOGY_OFFICER")
        self.assertEqual(loc_wb.verification_location_type, VerificationLocationType.ON_SITE_INSTALLATION.value)
        self.assertIsNone(loc_wb.gatc_reference, "GATC reference must be None for State Officer routing")
        self.assertIn("State Legal Metrology", loc_wb.test_centre)

    # =========================================================================
    # Test 3: Class IIII (Eligible for GATC)
    # =========================================================================
    def test_03_class_iiii_gatc_eligible(self):
        """
        Statutory Rule: Class IIII (Ordinary Accuracy) instruments across standard
        commercial capacities are authorized for GATC verification under the First Schedule.
        """
        inst_cl4 = self._create_instrument(
            instrument_id="INST-CL4-500KG",
            accuracy_class=AccuracyClass.CLASS_IIII,
            max_capacity=500.0,
            unit=MassUnit.KG,
            e=0.1,
            d=0.1,
        )
        routing_cl4 = self.routing_service.evaluate_routing(inst_cl4)
        self.assertTrue(routing_cl4.eligible_for_gatc, "Class IIII must be GATC eligible per P2")
        self.assertEqual(routing_cl4.target_authority, "GATC")

        loc_cl4 = self.location_service.resolve_job_location_and_routing(inst_cl4)
        self.assertEqual(loc_cl4.routing_decision, "GATC")
        self.assertEqual(loc_cl4.verification_location_type, VerificationLocationType.GATC_CENTRE.value)
        self.assertIsNotNone(loc_cl4.gatc_reference)

    # =========================================================================
    # Test 4: Class II (High Accuracy -> NEVER GATC Eligible)
    # =========================================================================
    def test_04_class_ii_strictly_state_officer_not_gatc(self):
        """
        Statutory Rule: Class II (High Accuracy) instruments (e.g. jewellery/bullion
        balances) are NOT authorized for GATC verification under the First Schedule.
        Statutory verification must be performed directly by the State Legal Metrology Officer.
        P3 must NEVER assume Class II is GATC eligible.
        """
        inst_cl2 = self._create_instrument(
            instrument_id="INST-CL2-600G",
            accuracy_class=AccuracyClass.CLASS_II,
            max_capacity=600.0,
            unit=MassUnit.G,
            min_capacity=0.5,
            e=0.01,
            d=0.001,
        )
        routing_cl2 = self.routing_service.evaluate_routing(inst_cl2)
        self.assertFalse(routing_cl2.eligible_for_gatc, "Class II must NEVER be eligible for GATC")
        self.assertEqual(routing_cl2.target_authority, "STATE_LEGAL_METROLOGY_OFFICER")
        self.assertIn("Class II (High Accuracy) instruments", routing_cl2.reason)

        loc_cl2 = self.location_service.resolve_job_location_and_routing(inst_cl2)
        self.assertEqual(loc_cl2.routing_decision, "STATE_LEGAL_METROLOGY_OFFICER")
        self.assertIsNone(loc_cl2.gatc_reference)
        self.assertIn("State Legal Metrology", loc_cl2.test_centre)

    # =========================================================================
    # Test 5: Rejection of Illegal GATC Assignments
    # =========================================================================
    def test_05_rejection_of_illegal_gatc_assignment(self):
        """
        Verifies that attempting to force or assign a GATC location for an ineligible
        instrument (Class II or Class III > 150 kg) is strictly rejected.
        """
        inst_cl2 = self._create_instrument(
            instrument_id="INST-CL2-ILLEGAL",
            accuracy_class=AccuracyClass.CLASS_II,
            max_capacity=1000.0,
            unit=MassUnit.G,
        )

        # 1. Direct validation check via JobLocationService
        valid, err_msg = self.location_service.validate_location_assignment(
            instrument=inst_cl2,
            location_type=VerificationLocationType.GATC_CENTRE,
        )
        self.assertFalse(valid)
        self.assertIn("Statutory Routing Violation", err_msg)

        # 2. Strict resolve raises ValueError
        with self.assertRaises(ValueError) as ctx:
            self.location_service.resolve_job_location_and_routing(
                instrument=inst_cl2,
                preferred_location_type="GATC_CENTRE",
                strict_gatc_validation=True,
            )
        self.assertIn("NOT eligible for GATC", str(ctx.exception))

        # 3. TestJobService.create_job returns HTTP 422
        job_payload = {
            "instrument_id": "INST-CL2-ILLEGAL",
            "job_type": "RE_VERIFICATION",
            "verification_location_type": "GATC_CENTRE",
            "strict_gatc_validation": True,
        }
        res = self.job_service.create_job(job_payload)
        self.assertFalse(res["success"])
        self.assertEqual(res["status_code"], 422)
        self.assertIn("NOT eligible for GATC", res["message"])

    # =========================================================================
    # Test 6: Model Approval Routing to Central Directorate
    # =========================================================================
    def test_06_model_approval_routing_to_central_directorate(self):
        """
        Statutory Rule: Model Approval is under Section 22 of Legal Metrology Act, 2009
        and is routed exclusively to the Central Directorate / CSIR-NPL / RRSL.
        """
        inst = self._create_instrument(
            instrument_id="INST-MODEL-APP",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
        )
        routing = self.routing_service.evaluate_routing(inst, job_type=JobType.MODEL_APPROVAL)
        self.assertFalse(routing.eligible_for_gatc)
        self.assertEqual(routing.target_authority, "CENTRAL_DIRECTORATE")
        self.assertIn("CSIR-NPL", routing.authority_name)

        loc = self.location_service.resolve_job_location_and_routing(
            instrument=inst,
            job_type=JobType.MODEL_APPROVAL,
        )
        self.assertEqual(loc.routing_decision, "CENTRAL_DIRECTORATE")
        self.assertEqual(loc.verification_location_type, VerificationLocationType.CENTRAL_LABORATORY.value)
        self.assertIsNone(loc.gatc_reference)

    # =========================================================================
    # Test 7: Installation Location & Reason Inheritance
    # =========================================================================
    def test_07_installation_location_and_reason_inheritance(self):
        """
        Verifies that TestJob inherits customer installation location and
        statutory verification reasons accurately.
        """
        inst = self._create_instrument(
            instrument_id="INST-LOC-TEST",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=50.0,
            customer_name="Tata Steel Processing Yard",
        )
        inst.verification_reason = VerificationReason.POST_REPAIR.value

        job_payload = {
            "instrument_id": "INST-LOC-TEST",
            "job_type": "POST_REPAIR",
        }
        res = self.job_service.create_job(job_payload)
        self.assertTrue(res["success"])

        job_data = res["data"]
        # Check installation location
        inst_loc = job_data["installation_location"]
        self.assertIsNotNone(inst_loc)
        self.assertEqual(inst_loc["customer_name"], "Tata Steel Processing Yard")
        self.assertEqual(inst_loc["district"], "Pune")
        self.assertEqual(inst_loc["state"], "Maharashtra")

        # Check reason
        self.assertEqual(job_data["reason_for_verification"], "POST_REPAIR")

    # =========================================================================
    # Test 8: Draft / Unverified Profile Manual Review Trigger
    # =========================================================================
    def test_08_draft_profile_triggers_manual_review(self):
        """
        Verifies that draft or unverified profiles (e.g. IN_LM_2026_GSR568E_DRAFT)
        trigger manual_review_flag = True without crashing the location service.
        """
        inst = self._create_instrument(
            instrument_id="INST-DRAFT-PROF",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=30.0,
        )
        routing = self.routing_service.evaluate_routing(
            instrument=inst,
            profile_id="IN_LM_2026_GSR568E_DRAFT",
        )
        self.assertTrue(routing.manual_review_flag)
        self.assertIsNotNone(routing.manual_review_reason)
        self.assertIn("requires legal confirmation", routing.manual_review_reason)

        loc = self.location_service.resolve_job_location_and_routing(
            instrument=inst,
            profile_id="IN_LM_2026_GSR568E_DRAFT",
        )
        self.assertTrue(loc.manual_review_flag)

    # =========================================================================
    # Test 9: Complete TestJob Entity 9-Field Storage & Serialization
    # =========================================================================
    def test_09_test_job_stores_all_required_fields_and_roundtrips(self):
        """
        Verifies that TestJob stores:
        1. verification location type
        2. laboratory / test centre
        3. GATC reference / code where applicable
        4. installation location
        5. reason for verification
        6. routing decision
        7. regulatory rule reference
        8. regulatory profile / version
        9. manual-review flag
        and successfully serializes/deserializes with to_dict() and from_dict().
        """
        inst = self._create_instrument(
            instrument_id="INST-FULL-FIELD",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=60.0,
        )

        res = self.job_service.create_job({
            "instrument_id": "INST-FULL-FIELD",
            "job_type": "RE_VERIFICATION",
            "reason": "PERIODIC_EXPIRY",
            "verification_location_type": "GATC_CENTRE",
            "gatc_reference": "GATC/MH/2026/042",
            "testing_centre_name": "Apex Precision GATC Testing Centre",
        })
        self.assertTrue(res["success"])
        job_dict = res["data"]

        # 1. Verification location type
        self.assertEqual(job_dict["verification_location_type"], "GATC_CENTRE")
        # 2. Laboratory / test centre
        self.assertEqual(job_dict["laboratory"], "Apex Precision GATC Testing Centre")
        self.assertEqual(job_dict["test_centre"], "Apex Precision GATC Testing Centre")
        # 3. GATC reference / code
        self.assertEqual(job_dict["gatc_reference"], "GATC/MH/2026/042")
        self.assertEqual(job_dict["gatc_code"], "GATC/MH/2026/042")
        # 4. Installation location
        self.assertIsNotNone(job_dict["installation_location"])
        self.assertEqual(job_dict["installation_location"]["state"], "Maharashtra")
        # 5. Reason for verification
        self.assertEqual(job_dict["reason_for_verification"], "PERIODIC_EXPIRY")
        # 6. Routing decision
        self.assertEqual(job_dict["routing_decision"], "GATC")
        # 7. Regulatory rule reference
        self.assertIn("Government Approved Test Centre", job_dict["regulatory_rule_reference"])
        # 8. Regulatory profile / version
        self.assertEqual(job_dict["regulatory_profile"], "IN_LM_2011_ACTIVE")
        self.assertEqual(job_dict["regulatory_profile_id"], "IN_LM_2011_ACTIVE")
        self.assertIsNotNone(job_dict["regulatory_version"])
        # 9. Manual review flag
        self.assertFalse(job_dict["manual_review_flag"])

        # Test from_dict roundtrip
        reconstructed_job = TestJob.from_dict(job_dict)
        self.assertEqual(reconstructed_job.verification_location_type, "GATC_CENTRE")
        self.assertEqual(reconstructed_job.laboratory, "Apex Precision GATC Testing Centre")
        self.assertEqual(reconstructed_job.gatc_reference, "GATC/MH/2026/042")
        self.assertEqual(reconstructed_job.routing_decision, "GATC")
        self.assertEqual(reconstructed_job.reason_for_verification, "PERIODIC_EXPIRY")
        self.assertEqual(reconstructed_job.regulatory_profile, "IN_LM_2011_ACTIVE")

    # =========================================================================
    # Test 10: Inspector Assignment with Location Update
    # =========================================================================
    def test_10_assign_inspector_with_location_validation(self):
        """
        Verifies assign_inspector validates location types and updates GATC reference.
        """
        inst = self._create_instrument(
            instrument_id="INST-ASSIGN-TEST",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=100.0,
        )
        res_job = self.job_service.create_job({"instrument_id": "INST-ASSIGN-TEST"})
        job_id = res_job["data"]["job_id"]

        # Valid assignment to GATC centre
        res_assign = self.job_service.assign_inspector(
            job_id=job_id,
            inspector_id="INSP-007",
            inspector_name="Shri V. S. Kulkarni",
            testing_centre_id="GATC-PUNE-01",
            testing_centre_name="Pune District GATC Lab",
            verification_location_type="GATC_CENTRE",
            gatc_reference="GATC/MH/01",
        )
        self.assertTrue(res_assign["success"])
        assigned_data = res_assign["data"]
        self.assertEqual(assigned_data["assigned_inspector_id"], "INSP-007")
        self.assertEqual(assigned_data["verification_location_type"], "GATC_CENTRE")
        self.assertEqual(assigned_data["gatc_reference"], "GATC/MH/01")


if __name__ == "__main__":
    unittest.main()
