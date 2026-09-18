"""
MetrIQ Person 3 Test Suite — Instrument Registry & Metrological Integration
===========================================================================
Tests instrument data models, Person 2 regulatory validation consumption,
and InstrumentRegistry CRUD and search capabilities.
"""

import os
import sys
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.regulatory.models import AccuracyClass, MassUnit
from app.instruments.models import (
    ApprovalStatus,
    ConsumerImpact,
    CustomerLocation,
    GraduationType,
    IndicationType,
    Instrument,
    InstrumentStatus,
    InstrumentType,
    ManufacturerInfo,
    PhysicalSeal,
    RangeDefinition,
    SealStatus,
    SealType,
    SoftwareConfig,
    TareType,
    TransactionUsage,
    UsageType,
    VerificationStatus,
    ZeroSettingType,
)
from app.instruments.registry import InstrumentRegistry
from app.instruments.service import InstrumentService


class TestP3Instruments(unittest.TestCase):
    """Tests Instrument data models and registry CRUD operations."""

    def setUp(self) -> None:
        self.registry = InstrumentRegistry()
        self.service = InstrumentService(registry=self.registry)

    def test_01_instrument_model_creation_and_dict(self):
        """Verify complete instrument entity instantiation and serialization."""
        inst = Instrument(
            instrument_id="INST-TEST-001",
            serial_number="TEST-SN-1234",
            manufacturer="Precision India Weighing",
            model_name="PIW-3000 Bench",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=30.0,
            min_capacity=0.2,
            e=0.01,
            d=0.01,
            unit=MassUnit.KG,
            instrument_type=InstrumentType.BENCH_SCALE,
            status=InstrumentStatus.ACTIVE,
        )

        self.assertEqual(inst.n, 3000.0)
        d = inst.to_dict()
        self.assertEqual(d["instrument_id"], "INST-TEST-001")
        self.assertEqual(d["accuracy_class"], "III")
        self.assertEqual(d["max_capacity"], 30.0)
        self.assertEqual(d["n"], 3000.0)

        # Roundtrip from_dict
        reconstructed = Instrument.from_dict(d)
        self.assertEqual(reconstructed.instrument_id, inst.instrument_id)
        self.assertEqual(reconstructed.accuracy_class, AccuracyClass.CLASS_III)
        self.assertEqual(reconstructed.n, 3000.0)

    def test_02_create_instrument_success_with_p2_validation(self):
        """Verify successful instrument creation when Person 2 validates metrology."""
        payload = {
            "instrument_id": "INST-NEW-01",
            "serial_number": "SN-NEW-9988",
            "manufacturer": "Essae-Teraoka Ltd.",
            "model_name": "DS-215 Retail Counter",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "instrument_type": "ELECTRONIC_COUNTER_SCALE",
            "model_approval_number": "IND/09/2024/001",
        }

        res = self.service.create_instrument(payload)
        self.assertTrue(res["success"])
        self.assertEqual(res["status_code"], 201)
        self.assertIn("INST-NEW-01", res["data"]["instrument_id"])
        self.assertTrue(res["regulatory_validation"]["valid"])
        self.assertTrue(res["model_approval_check"]["verified"])

        # Check stored in registry
        stored = self.registry.get("INST-NEW-01")
        self.assertIsNotNone(stored)
        self.assertEqual(stored.serial_number, "SN-NEW-9988")

    def test_03_create_instrument_rejected_on_invalid_metrology(self):
        """
        Verify that Person 3 rejects instrument creation when Person 2
        flags statutory metrology errors (e.g. invalid step sequence e=4g).
        """
        invalid_payload = {
            "instrument_id": "INST-BAD-01",
            "serial_number": "SN-BAD-0001",
            "manufacturer": "Invalid Mfr",
            "model_name": "Bad Scale",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.004,  # Statutory violation: not in 1, 2, 5 sequence
            "d": 0.004,
            "unit": "kg",
        }

        res = self.service.create_instrument(invalid_payload)
        self.assertFalse(res["success"])
        self.assertEqual(res["status_code"], 422)
        self.assertIn("RULE_SCALE_INTERVAL_FORM", str(res["validation_errors"]))

        # Confirm not added to registry
        self.assertIsNone(self.registry.get("INST-BAD-01"))

    def test_04_duplicate_serial_number_prevention(self):
        """Verify unique serial number enforcement across instruments."""
        payload1 = {
            "instrument_id": "INST-DUP-01",
            "serial_number": "SN-UNIQUE-777",
            "manufacturer": "Mfr A",
            "model_name": "Model 1",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
        }
        res1 = self.service.create_instrument(payload1, enforce_model_approval=False)
        self.assertTrue(res1["success"])

        payload2 = {
            "instrument_id": "INST-DUP-02",
            "serial_number": "SN-UNIQUE-777",  # Duplicate serial
            "manufacturer": "Mfr B",
            "model_name": "Model 2",
            "accuracy_class": "III",
            "Max": 30.0,
            "Min": 0.2,
            "e": 0.01,
            "d": 0.01,
            "unit": "kg",
        }
        res2 = self.service.create_instrument(payload2, enforce_model_approval=False)
        self.assertFalse(res2["success"])
        self.assertEqual(res2["status_code"], 409)
        self.assertIn("already registered", res2["message"])

    def test_05_registry_search_and_filter(self):
        """Verify search and multi-attribute filtering in registry."""
        # Query existing seed instruments
        all_insts = self.registry.list_all()
        self.assertGreaterEqual(len(all_insts), 3)

        # Filter by class
        class_ii = self.registry.list_all(accuracy_class="II")
        self.assertTrue(all(inst.accuracy_class == AccuracyClass.CLASS_II for inst in class_ii))

        # Filter by manufacturer substring
        essae_scales = self.registry.list_all(manufacturer="Essae")
        self.assertTrue(all("essae" in inst.manufacturer.lower() for inst in essae_scales))

        # Free-text search across serial number
        by_sn = self.registry.list_all(search="9981")
        self.assertEqual(len(by_sn), 1)
        self.assertEqual(by_sn[0].instrument_id, "INST-RETAIL-001")

    def test_06_comprehensive_instrument_fields_roundtrip(self):
        """Verify full spectrum of identity, classification, legal, usage, verification, and lifecycle fields."""
        payload = {
            "instrument_id": "INST-FULL-001",
            "serial_number": "SN-FULL-9001",
            "manufacturer": "National Weighing Systems",
            "model_name": "NWS SuperCheck 5000",
            "model_number": "NWS-SC5000",
            "instrument_name": "SuperCheck Industrial Bench Scale",
            "description": "Heavy duty checkweigher for packaging plants.",
            "accuracy_class": "III",
            "Max": 50.0,
            "Min": 0.4,
            "e": 0.02,
            "d": 0.02,
            "unit": "kg",
            "instrument_type": "BENCH_SCALE",
            "graduation_type": "GRADUATED",
            "electronic_status": True,
            "software_controlled": True,
            "multi_range_status": False,
            "multi_interval_status": False,
            "model_approval_number": "IND/09/2024/001",
            "model_approval_date": "2024-03-01",
            "model_approval_mark": "IND-LM-2024-001",
            "approval_status": "APPROVED",
            "manufacturer_info": {
                "name": "National Weighing Systems Ltd.",
                "country_of_origin": "INDIA",
                "dealer_license_number": "DL-MH-2020-098",
                "importer_name": None,
                "address": "Andheri East, Mumbai",
            },
            "usage_type": "COMMERCIAL_TRADE",
            "transaction_usage": "COMMERCIAL_TRANSACTION",
            "consumer_impact": "HIGH_DIRECT_RETAIL",
            "location": {
                "customer_name": "Bharat Agro Logistics",
                "contact_person": "Sunil Verma",
                "phone": "+91-9820123456",
                "site_name": "Nagpur Central Warehouse",
                "department": "Grain Packaging Line 2",
                "installation_environment": "FACTORY_FLOOR",
                "city": "Nagpur",
                "state": "Maharashtra",
                "pincode": "440001",
            },
            "verification_status": "VERIFIED",
            "verification_officer": "Insp. A. Deshmukh",
            "stamp_mark": "STAMP-MH-2024-Q1",
            "gatc_code": "GATC-MH-001",
            "last_verification_date": "2024-03-10",
            "last_verification_certificate": "CERT-MH-2024-110",
            "next_verification_date": "2025-03-10",
            "re_verification_interval_months": 12,
            "manufactured_date": "2024-02-15",
            "registered_date": "2024-03-01",
            "installed_date": "2024-03-05",
            "repair_date": None,
            "dismantled_date": None,
            "reinstalled_date": None,
            "retired_date": None,
            "notes": "Commissioned and sealed on-site.",
        }

        res = self.service.create_instrument(payload, enforce_model_approval=False)
        self.assertTrue(res["success"])
        self.assertEqual(res["status_code"], 201)

        data = res["data"]
        self.assertEqual(data["model_number"], "NWS-SC5000")
        self.assertEqual(data["instrument_name"], "SuperCheck Industrial Bench Scale")
        self.assertEqual(data["graduation_type"], "GRADUATED")
        self.assertTrue(data["is_software_controlled"])
        self.assertEqual(data["approval_status"], "APPROVED")
        self.assertEqual(data["usage_type"], "COMMERCIAL_TRADE")
        self.assertEqual(data["transaction_usage"], "COMMERCIAL_TRANSACTION")
        self.assertEqual(data["consumer_impact"], "HIGH_DIRECT_RETAIL")
        self.assertEqual(data["verification_status"], "VERIFIED")
        self.assertEqual(data["gatc_code"], "GATC-MH-001")
        self.assertEqual(data["manufactured_date"], "2024-02-15")
        self.assertEqual(data["installed_date"], "2024-03-05")
        self.assertEqual(data["location"]["department"], "Grain Packaging Line 2")

    def test_07_retrieve_by_serial_and_id(self):
        """Verify retrieval by instrument ID and unique serial number."""
        inst = self.service.get_instrument("INST-RETAIL-001")
        self.assertIsNotNone(inst)
        self.assertEqual(inst["instrument_id"], "INST-RETAIL-001")

        by_sn = self.service.get_by_serial("ESSAE-2024-9981")
        self.assertIsNotNone(by_sn)
        self.assertEqual(by_sn["instrument_id"], "INST-RETAIL-001")

        # Non-existent ID / serial
        self.assertIsNone(self.service.get_instrument("NON-EXISTENT"))
        self.assertIsNone(self.service.get_by_serial("NON-EXISTENT-SN"))

    def test_08_update_instrument_and_metrology_revalidation(self):
        """Verify updating instrument details and enforcing P2 metrological re-validation."""
        # 1. Update valid metadata (location and usage)
        update_res = self.service.update_instrument(
            "INST-RETAIL-001",
            {
                "usage_type": "AGRICULTURAL",
                "notes": "Relocated to farmers market division",
            },
        )
        self.assertTrue(update_res["success"])
        self.assertEqual(update_res["data"]["usage_type"], "AGRICULTURAL")
        self.assertIn("farmers market", update_res["data"]["notes"])

        # 2. Update with invalid scale parameter (e=0.003 is illegal step sequence)
        bad_update = self.service.update_instrument(
            "INST-RETAIL-001",
            {"e": 0.003},
        )
        self.assertFalse(bad_update["success"])
        self.assertEqual(bad_update["status_code"], 422)
        self.assertIn("invalid", bad_update["message"].lower())

    def test_09_lifecycle_date_chronology_validation(self):
        """Verify that invalid chronological lifecycle dates are rejected before persistence."""
        # Installed date before manufacturing date
        bad_install_payload = {
            "instrument_id": "INST-BAD-DATE-1",
            "serial_number": "SN-BD-01",
            "manufacturer": "Test Mfr",
            "model_name": "Test Model",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "manufactured_date": "2024-06-01",
            "installed_date": "2024-05-01",  # Precedes manufactured date!
        }
        res = self.service.create_instrument(bad_install_payload, enforce_model_approval=False)
        self.assertFalse(res["success"])
        self.assertEqual(res["status_code"], 422)
        self.assertIn("Installation date", str(res["validation_errors"]))

        # Retired date before installed date
        bad_retire_payload = {
            "instrument_id": "INST-BAD-DATE-2",
            "serial_number": "SN-BD-02",
            "manufacturer": "Test Mfr",
            "model_name": "Test Model",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "installed_date": "2024-06-01",
            "retired_date": "2024-01-01",  # Precedes installed date!
        }
        res2 = self.service.create_instrument(bad_retire_payload, enforce_model_approval=False)
        self.assertFalse(res2["success"])
        self.assertEqual(res2["status_code"], 422)
        self.assertIn("Retirement date", str(res2["validation_errors"]))

    def test_10_advanced_search_and_filters(self):
        """Verify filtering by usage_type, instrument_type, verification_status, and deep search."""
        # Filter by usage type
        lab_instruments = self.service.list_instruments(usage_type="LABORATORY_RESEARCH")
        self.assertEqual(len(lab_instruments), 1)
        self.assertEqual(lab_instruments[0]["instrument_id"], "INST-LAB-002")

        # Filter by instrument type
        weighbridges = self.service.list_instruments(instrument_type="WEIGHBRIDGE")
        self.assertEqual(len(weighbridges), 1)
        self.assertEqual(weighbridges[0]["instrument_id"], "INST-WEIGHBRIDGE-003")

        # Filter by verification status
        verified_items = self.service.list_instruments(verification_status="VERIFIED")
        self.assertGreaterEqual(len(verified_items), 3)

        # Free-text search by model number
        by_model_num = self.service.list_instruments(search="BRIDGEMONT-60T")
        self.assertEqual(len(by_model_num), 1)
        self.assertEqual(by_model_num[0]["instrument_id"], "INST-WEIGHBRIDGE-003")

        # Free-text search by site name
        by_site = self.service.list_instruments(search="Peenya")
        self.assertEqual(len(by_site), 1)
        self.assertEqual(by_site[0]["instrument_id"], "INST-LAB-002")

    def test_11_delete_instrument_and_free_serial(self):
        """Verify instrument deletion removes record and frees the serial number index."""
        payload = {
            "instrument_id": "INST-TEMP-DEL",
            "serial_number": "SN-TEMP-DEL-999",
            "manufacturer": "Temp Mfr",
            "model_name": "Temp Scale",
            "accuracy_class": "III",
            "Max": 30.0,
            "Min": 0.2,
            "e": 0.01,
            "d": 0.01,
            "unit": "kg",
        }
        res = self.service.create_instrument(payload, enforce_model_approval=False)
        self.assertTrue(res["success"])

        # Confirm present
        self.assertIsNotNone(self.service.get_instrument("INST-TEMP-DEL"))
        self.assertIsNotNone(self.service.get_by_serial("SN-TEMP-DEL-999"))

        # Delete
        del_ok = self.service.delete_instrument("INST-TEMP-DEL")
        self.assertTrue(del_ok)
        self.assertIsNone(self.service.get_instrument("INST-TEMP-DEL"))
        self.assertIsNone(self.service.get_by_serial("SN-TEMP-DEL-999"))

        # Re-register same serial with new ID should now succeed
        payload["instrument_id"] = "INST-TEMP-DEL-2"
        res2 = self.service.create_instrument(payload, enforce_model_approval=False)
        self.assertTrue(res2["success"])


if __name__ == "__main__":
    unittest.main()
