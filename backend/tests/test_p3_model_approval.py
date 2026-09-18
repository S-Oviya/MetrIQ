"""
MetrIQ Person 3 Test Suite — Model Approval (Pattern Approval)
==============================================================
Tests statutory Model Approval Certificate tracking, validity checks,
and metrological envelope verification under Model Approval Rules, 2011.
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
from app.instruments.model_approval import (
    MODEL_APPROVAL_REGISTRY,
    ModelApprovalCertificate,
    ModelApprovalRecord,
    ModelApprovalRegistry,
    ModelApprovalStatus,
    ModelApprovalStateTransitionError,
)
from app.instruments.service import InstrumentService


class TestP3ModelApproval(unittest.TestCase):
    """Tests Model Approval certificate registry and instrument envelope verification."""

    def setUp(self) -> None:
        self.registry = ModelApprovalRegistry()

    def test_01_seed_certificates_registered(self):
        """Verify standard statutory seed certificates exist in registry."""
        cert_retail = self.registry.get("IND/09/2024/001")
        self.assertIsNotNone(cert_retail)
        self.assertEqual(cert_retail.manufacturer, "Essae-Teraoka Ltd.")
        self.assertIn(AccuracyClass.CLASS_III, cert_retail.accuracy_classes)
        self.assertTrue(cert_retail.is_valid_on_date())

        cert_lab = self.registry.get("IND/09/2023/045")
        self.assertIsNotNone(cert_lab)
        self.assertEqual(cert_lab.manufacturer, "Sartorius India Pvt. Ltd.")
        self.assertIn(AccuracyClass.CLASS_II, cert_lab.accuracy_classes)

    def test_02_certificate_date_validity(self):
        """Verify certificate active period evaluations."""
        cert = ModelApprovalCertificate(
            approval_number="IND/TEST/2020/01",
            manufacturer="Test Mfr",
            model_name="Test Model",
            issuing_authority="Director of Legal Metrology",
            issue_date="2020-01-01",
            valid_from="2020-01-01",
            valid_until="2030-01-01",
            status=ModelApprovalStatus.VALID,
        )

        # Active date check
        self.assertTrue(cert.is_valid_on_date("2025-06-01"))
        # Pre-issue date check
        self.assertFalse(cert.is_valid_on_date("2019-12-31"))
        # Post-expiry date check
        self.assertFalse(cert.is_valid_on_date("2030-01-02"))

        # Status revoked check
        cert.status = ModelApprovalStatus.REVOKED
        self.assertFalse(cert.is_valid_on_date("2025-06-01"))

    def test_03_envelope_verification_pass(self):
        """Verify instrument matching all certificate specifications passes envelope test."""
        inst = Instrument(
            instrument_id="INST-OK-01",
            serial_number="SN-OK-01",
            manufacturer="Essae-Teraoka Ltd.",
            model_name="DS-215",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
            model_approval_number="IND/09/2024/001",
        )

        is_valid, cert, reasons = self.registry.verify_instrument(inst)
        self.assertTrue(is_valid)
        self.assertIsNotNone(cert)
        self.assertEqual(len(reasons), 0)

    def test_04_envelope_capacity_exceeded(self):
        """Verify instrument exceeding certificate maximum capacity is rejected."""
        # Certificate IND/09/2024/001 maximum approved capacity is 35 kg
        inst_heavy = Instrument(
            instrument_id="INST-TOO-HEAVY",
            serial_number="SN-HEAVY-01",
            manufacturer="Essae-Teraoka Ltd.",
            model_name="DS-215",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=50.0,  # Exceeds 35 kg envelope
            min_capacity=0.5,
            e=0.01,
            d=0.01,
            unit=MassUnit.KG,
            model_approval_number="IND/09/2024/001",
        )

        is_valid, cert, reasons = self.registry.verify_instrument(inst_heavy)
        self.assertFalse(is_valid)
        self.assertTrue(any("Capacity exceeds approved envelope" in r for r in reasons))

    def test_05_envelope_accuracy_class_mismatch(self):
        """Verify accuracy class mismatch between certificate and instrument is rejected."""
        # Certificate IND/09/2024/001 authorizes Class III; instrument declares Class II
        inst_wrong_class = Instrument(
            instrument_id="INST-WRONG-CLASS",
            serial_number="SN-WRONG-01",
            manufacturer="Essae-Teraoka Ltd.",
            model_name="DS-215",
            accuracy_class=AccuracyClass.CLASS_II,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
            model_approval_number="IND/09/2024/001",
        )

        is_valid, cert, reasons = self.registry.verify_instrument(inst_wrong_class)
        self.assertFalse(is_valid)
        self.assertTrue(any("Accuracy class mismatch" in r for r in reasons))

    def test_06_unregistered_model_approval_rejection_in_service(self):
        """Verify that InstrumentService rejects unregistered model numbers when enforced."""
        service = InstrumentService()
        payload = {
            "instrument_id": "INST-FAKE-MA",
            "serial_number": "SN-FAKE-01",
            "manufacturer": "Unknown Mfr",
            "model_name": "Unapproved Scale",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "model_approval_number": "IND/99/FAKE/999",  # Non-existent approval
        }

        res = service.create_instrument(payload, enforce_model_approval=True)
        self.assertFalse(res["success"])
        self.assertEqual(res["status_code"], 400)
        self.assertIn("not registered", res["message"])

    def test_07_create_valid_model_approval_record(self):
        """Verify creating a valid model approval record in DRAFT status."""
        data = {
            "application_reference": "APP-TEST-2026-001",
            "model_number": "DS-852",
            "model_name": "Essae DS-852 Retail Scale",
            "manufacturer": "Essae-Teraoka Ltd.",
            "instrument_type": "ELECTRONIC_COUNTER_SCALE",
            "accuracy_class": "III",
            "Max": 30.0,
            "Min": 0.1,
            "e": 0.01,
            "d": 0.01,
            "unit": "kg",
            "status": "DRAFT",
        }
        record = self.registry.create_record(data)
        self.assertIsNotNone(record)
        self.assertEqual(record.application_reference, "APP-TEST-2026-001")
        self.assertEqual(record.status, ModelApprovalStatus.DRAFT)
        self.assertEqual(record.max_capacity, 30.0)
        self.assertEqual(record.max_capacity_kg, 30.0)
        self.assertEqual(record.accuracy_class, AccuracyClass.CLASS_III)

        # Verify serialization roundtrip
        d = record.to_dict()
        self.assertEqual(d["application_reference"], "APP-TEST-2026-001")
        self.assertEqual(d["status"], "DRAFT")

    def test_08_missing_required_approval_information(self):
        """Verify validation failure when required model approval fields are omitted or invalid."""
        # 1. Missing application reference
        with self.assertRaises(ValueError) as ctx:
            self.registry.create_record({
                "application_reference": "",
                "model_number": "M-1",
                "manufacturer": "Mfr",
                "accuracy_class": "III",
                "Max": 15.0,
                "Min": 0.1,
                "e": 0.005,
                "d": 0.005,
            })
        self.assertIn("application reference is required", str(ctx.exception))

        # 2. Missing manufacturer
        with self.assertRaises(ValueError) as ctx:
            self.registry.create_record({
                "application_reference": "APP-FAIL-01",
                "model_number": "M-1",
                "manufacturer": "",
                "accuracy_class": "III",
                "Max": 15.0,
                "Min": 0.1,
                "e": 0.005,
                "d": 0.005,
            })
        self.assertIn("Manufacturer name is required", str(ctx.exception))

        # 3. Non-positive capacity
        with self.assertRaises(ValueError) as ctx:
            self.registry.create_record({
                "application_reference": "APP-FAIL-02",
                "model_number": "M-1",
                "manufacturer": "Mfr",
                "accuracy_class": "III",
                "Max": -15.0,
                "Min": 0.1,
                "e": 0.005,
                "d": 0.005,
            })
        self.assertIn("Maximum capacity (Max) must be greater than zero", str(ctx.exception))

        # 4. Min capacity exceeding Max
        with self.assertRaises(ValueError) as ctx:
            self.registry.create_record({
                "application_reference": "APP-FAIL-03",
                "model_number": "M-1",
                "manufacturer": "Mfr",
                "accuracy_class": "III",
                "Max": 15.0,
                "Min": 25.0,
                "e": 0.005,
                "d": 0.005,
            })
        self.assertIn("Minimum capacity (Min) cannot exceed maximum capacity (Max)", str(ctx.exception))

    def test_09_regulatory_validation_via_person2(self):
        """Verify that Person 2's validate_instrument_api is consumed for metrological rules."""
        # Step sequence violation: e = 0.003 is NOT in {1, 2, 5} x 10^k
        bad_e_data = {
            "application_reference": "APP-REG-FAIL-01",
            "model_number": "BAD-E-SCALE",
            "manufacturer": "Bad Scale Co.",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.003,  # Invalid step sequence
            "d": 0.003,
            "status": "SUBMITTED",
        }
        with self.assertRaises(ValueError) as ctx:
            self.registry.create_record(bad_e_data)
        self.assertTrue(
            "violates" in str(ctx.exception).lower() or "not in {1, 2, 5}" in str(ctx.exception) or "rule" in str(ctx.exception).lower()
        )

    def test_10_invalid_state_transitions_prevented(self):
        """Verify strict lifecycle state transitions prevent illegal jumps."""
        # 1. Create a DRAFT record
        data = {
            "application_reference": "APP-TRANS-01",
            "model_number": "TRANS-SCALE",
            "manufacturer": "Mfr",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "status": "DRAFT",
        }
        self.registry.create_record(data)

        # 2. DRAFT directly to APPROVED is illegal (must be SUBMITTED and UNDER_TESTING first)
        with self.assertRaises(ModelApprovalStateTransitionError):
            self.registry.transition_status("APP-TRANS-01", ModelApprovalStatus.APPROVED)

        # 3. DRAFT directly to UNDER_TESTING is illegal (must be SUBMITTED first)
        with self.assertRaises(ModelApprovalStateTransitionError):
            self.registry.transition_status("APP-TRANS-01", ModelApprovalStatus.UNDER_TESTING)

        # 4. Transition DRAFT -> REJECTED is legal
        rejected = self.registry.transition_status(
            "APP-TRANS-01",
            ModelApprovalStatus.REJECTED,
            rejection_reason="Defective technical documentation",
        )
        self.assertEqual(rejected.status, ModelApprovalStatus.REJECTED)

        # 5. REJECTED to APPROVED is illegal (REJECTED is terminal)
        with self.assertRaises(ModelApprovalStateTransitionError):
            self.registry.transition_status("APP-TRANS-01", ModelApprovalStatus.APPROVED)

    def test_11_valid_lifecycle_state_transitions(self):
        """Verify complete legal lifecycle: DRAFT -> SUBMITTED -> UNDER_TESTING -> APPROVED -> EXPIRED."""
        data = {
            "application_reference": "APP-HAPPY-01",
            "model_number": "HP-SCALE",
            "manufacturer": "Happy Scale Mfr",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "status": "DRAFT",
        }
        self.registry.create_record(data)

        # 1. DRAFT -> SUBMITTED
        sub = self.registry.transition_status("APP-HAPPY-01", ModelApprovalStatus.SUBMITTED)
        self.assertEqual(sub.status, ModelApprovalStatus.SUBMITTED)

        # 2. SUBMITTED -> UNDER_TESTING (missing testing laboratory fails)
        with self.assertRaises(ValueError) as ctx:
            self.registry.transition_status("APP-HAPPY-01", ModelApprovalStatus.UNDER_TESTING)
        self.assertIn("testing laboratory is required", str(ctx.exception))

        # SUBMITTED -> UNDER_TESTING with laboratory succeeds
        testing = self.registry.transition_status(
            "APP-HAPPY-01",
            ModelApprovalStatus.UNDER_TESTING,
            testing_laboratory="CSIR-National Physical Laboratory (NPL), New Delhi",
            testing_laboratory_reference="NPL/2026/TEST/991",
        )
        self.assertEqual(testing.status, ModelApprovalStatus.UNDER_TESTING)

        # 3. UNDER_TESTING -> APPROVED (missing approval credentials fails)
        with self.assertRaises(ValueError) as ctx:
            self.registry.transition_status("APP-HAPPY-01", ModelApprovalStatus.APPROVED)
        self.assertIn("certificate number is required", str(ctx.exception))

        # UNDER_TESTING -> APPROVED with full statutory credentials succeeds
        approved = self.registry.transition_status(
            "APP-HAPPY-01",
            ModelApprovalStatus.APPROVED,
            approval_number="IND/09/2026/777",
            approval_date="2026-03-01",
            approval_mark="IND-LM-2026-777",
            valid_from="2026-03-01",
            valid_until="2036-02-28",
        )
        self.assertEqual(approved.status, ModelApprovalStatus.APPROVED)
        self.assertEqual(approved.approval_number, "IND/09/2026/777")
        self.assertTrue(approved.is_valid_on_date("2026-05-01"))

        # 4. APPROVED -> EXPIRED
        expired = self.registry.transition_status("APP-HAPPY-01", ModelApprovalStatus.EXPIRED)
        self.assertEqual(expired.status, ModelApprovalStatus.EXPIRED)
        self.assertFalse(expired.is_valid_on_date())

        # 5. EXPIRED -> SUPERSEDED
        super_rec = self.registry.transition_status("APP-HAPPY-01", ModelApprovalStatus.SUPERSEDED)
        self.assertEqual(super_rec.status, ModelApprovalStatus.SUPERSEDED)

    def test_12_instrument_to_approval_association(self):
        """Verify associating a model approval with one or more physical instruments."""
        # Create an approved model
        data = {
            "application_reference": "APP-ASSOC-01",
            "approval_number": "IND/09/2026/ASSOC",
            "model_number": "ASSOC-SCALE",
            "manufacturer": "Assoc Scales Ltd.",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "approval_date": "2026-01-01",
            "approval_mark": "IND-LM-2026-ASSOC",
            "status": "APPROVED",
        }
        self.registry.create_record(data)

        # 1. Link first instrument
        rec1 = self.registry.link_instrument("APP-ASSOC-01", "INST-RETAIL-101")
        self.assertIn("INST-RETAIL-101", rec1.associated_instrument_ids)

        # 2. Link second instrument
        rec2 = self.registry.link_instrument("IND/09/2026/ASSOC", "INST-RETAIL-102")
        self.assertIn("INST-RETAIL-102", rec2.associated_instrument_ids)
        self.assertEqual(len(rec2.associated_instrument_ids), 2)

        # 3. Retrieve associated instruments
        inst_list = self.registry.get_associated_instruments("IND/09/2026/ASSOC")
        self.assertEqual(inst_list, ["INST-RETAIL-101", "INST-RETAIL-102"])

        # 4. Idempotence: linking the same instrument again does not duplicate
        rec3 = self.registry.link_instrument("APP-ASSOC-01", "INST-RETAIL-101")
        self.assertEqual(len(rec3.associated_instrument_ids), 2)

    def test_13_duplicate_approval_references_rejected(self):
        """Verify that duplicate application references and approval numbers are rejected."""
        data_1 = {
            "application_reference": "APP-UNIQUE-REF",
            "approval_number": "IND/09/2026/UNIQ1",
            "model_number": "UNIQ-1",
            "manufacturer": "Mfr",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "approval_date": "2026-01-01",
            "approval_mark": "IND-LM-UNIQ-1",
            "status": "APPROVED",
        }
        self.registry.create_record(data_1)

        # Attempt duplicate application reference
        dup_app = {
            "application_reference": "APP-UNIQUE-REF",
            "model_number": "UNIQ-2",
            "manufacturer": "Mfr",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "status": "DRAFT",
        }
        with self.assertRaises(ValueError) as ctx:
            self.registry.create_record(dup_app)
        self.assertIn("already exists", str(ctx.exception))

        # Attempt duplicate approval number
        dup_num = {
            "application_reference": "APP-OTHER-REF",
            "approval_number": "IND/09/2026/UNIQ1",  # Same as data_1
            "model_number": "UNIQ-3",
            "manufacturer": "Mfr",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "approval_date": "2026-01-01",
            "approval_mark": "IND-LM-UNIQ-1",
            "status": "APPROVED",
        }
        with self.assertRaises(ValueError) as ctx:
            self.registry.create_record(dup_num)
        self.assertIn("already issued", str(ctx.exception))

    def test_14_search_and_filter_model_approvals(self):
        """Verify multi-criteria listing and text search for model approvals."""
        # Create test records
        self.registry.create_record({
            "application_reference": "APP-FILTER-01",
            "model_number": "FLT-PRECISION",
            "manufacturer": "Precision India Labs",
            "accuracy_class": "II",
            "Max": 5000.0,
            "Min": 5.0,
            "e": 0.1,
            "d": 0.1,
            "unit": "g",
            "status": "UNDER_TESTING",
            "testing_laboratory": "RRSL Bangalore",
        })

        # Filter by status
        under_test = self.registry.list_all(status="UNDER_TESTING")
        self.assertTrue(any(r.application_reference == "APP-FILTER-01" for r in under_test))

        # Filter by manufacturer
        prec_mfr = self.registry.list_all(manufacturer="Precision India")
        self.assertTrue(all("precision india" in r.manufacturer.lower() for r in prec_mfr))

        # Search keyword
        search_res = self.registry.list_all(search="RRSL Bangalore")
        self.assertTrue(any(r.application_reference == "APP-FILTER-01" for r in search_res))

    def test_15_service_layer_model_approval_integration(self):
        """Verify InstrumentService coordinates model approval creation, updates, and linking."""
        service = InstrumentService(registry=self.registry)

        # 1. Service create
        res_create = service.create_model_approval({
            "application_reference": "APP-SRV-01",
            "model_number": "SRV-SCALE",
            "manufacturer": "Service Scale Ltd.",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "status": "DRAFT",
        })
        self.assertTrue(res_create["success"])
        self.assertEqual(res_create["status_code"], 201)

        # 2. Service update
        res_update = service.update_model_approval("APP-SRV-01", {"notes": "Inspected by Person 3"})
        self.assertTrue(res_update["success"])
        self.assertEqual(res_update["data"]["notes"], "Inspected by Person 3")

        # 3. Service transition
        res_trans = service.transition_model_approval("APP-SRV-01", "SUBMITTED")
        self.assertTrue(res_trans["success"])
        self.assertEqual(res_trans["data"]["status"], "SUBMITTED")

        # 4. Service link instrument
        res_link = service.link_model_approval_instrument("APP-SRV-01", "INST-SRV-99")
        self.assertTrue(res_link["success"])
        self.assertIn("INST-SRV-99", res_link["associated_instruments"])


if __name__ == "__main__":
    unittest.main()

