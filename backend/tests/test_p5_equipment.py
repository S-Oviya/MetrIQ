"""
MetrIQ P5 Test Suite — Equipment & Test Standards Tracking
==========================================================
Person 5: Workflow + Evidence Engineer

Comprehensive tests covering:
1. Equipment CRUD, validation, and calibration validity
2. Test Standards / Reference Weights CRUD, validation, and calibration validity
3. Test Job association with calibration validity enforcement
4. REST API endpoints via FastAPI TestClient
"""

from datetime import date, datetime, timedelta, timezone
import os
import sys
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.jobs.models import JobStatus, TestJob
from app.jobs.repository import TEST_JOB_REPOSITORY
from app.equipment.models import Equipment, EquipmentStatus, TestStandard
from app.equipment.repository import (
    DuplicateSerialNumberError,
    EQUIPMENT_REPOSITORY,
    EquipmentRepository,
)
from app.equipment.service import (
    CalibrationExpiredError,
    EquipmentNotFoundError,
    EquipmentService,
    EquipmentValidationError,
    StandardNotFoundError,
)
from app.workflow.service import JobNotFoundError

# FastAPI TestClient
try:
    from fastapi.testclient import TestClient
    from app.main import app
    HAS_TEST_CLIENT = True
except ImportError:
    HAS_TEST_CLIENT = False


class TestP5EquipmentDomain(unittest.TestCase):
    """Unit tests for Equipment and Test Standards domain models, repository, and service."""

    def setUp(self) -> None:
        self.repo = EquipmentRepository()
        self.jobs = TEST_JOB_REPOSITORY
        self.service = EquipmentService(equipment_repository=self.repo, job_repository=self.jobs)

        # Dates helpers
        self.today = datetime.now(timezone.utc).date()
        self.future_date = (self.today + timedelta(days=365)).isoformat()
        self.past_date = (self.today - timedelta(days=30)).isoformat()
        self.long_past_date = (self.today - timedelta(days=400)).isoformat()

    # =========================================================================
    # Equipment Tests
    # =========================================================================

    def test_01_create_valid_equipment(self):
        """Verify registering a valid active equipment item."""
        payload = {
            "name": "Digital Precision Thermometer",
            "type": "THERMOMETER",
            "serial_number": "SN-TH-001",
            "manufacturer": "Fluke",
            "model": "1524",
            "calibration_certificate": "CAL-FLK-2026-001",
            "calibration_date": self.past_date,
            "calibration_due_date": self.future_date,
            "status": "ACTIVE",
            "notes": "Primary temperature probe for NAWI testing",
        }
        item = self.service.create_equipment(payload)
        self.assertIsNotNone(item.id)
        self.assertEqual(item.name, "Digital Precision Thermometer")
        self.assertEqual(item.serial_number, "SN-TH-001")
        self.assertEqual(item.status, EquipmentStatus.ACTIVE)
        usable, err_code, _ = item.is_usable()
        self.assertTrue(usable)
        self.assertIsNone(err_code)

    def test_02_retrieve_and_list_equipment(self):
        """Verify retrieving equipment by ID, serial, and filtering."""
        payload = {
            "name": "Digital Barometer",
            "type": "BAROMETER",
            "serial_number": "SN-BARO-001",
            "manufacturer": "Vaisala",
            "model": "PTB330",
            "calibration_certificate": "CAL-VAI-2026",
            "calibration_date": self.past_date,
            "calibration_due_date": self.future_date,
            "status": "ACTIVE",
        }
        created = self.service.create_equipment(payload)

        # By ID
        fetched = self.service.get_equipment(created.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "Digital Barometer")

        # By serial
        by_serial = self.repo.get_equipment_by_serial("SN-BARO-001")
        self.assertIsNotNone(by_serial)
        self.assertEqual(by_serial.id, created.id)

        # Listing with search
        results = self.service.list_equipment(search="PTB330")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, created.id)

    def test_03_update_equipment(self):
        """Verify updating equipment fields and changing status."""
        payload = {
            "name": "Hygrometer",
            "type": "HYGROMETER",
            "serial_number": "SN-HYG-001",
            "manufacturer": "Testo",
            "model": "608-H1",
            "calibration_certificate": "CAL-HYG-01",
            "calibration_date": self.past_date,
            "calibration_due_date": self.future_date,
        }
        eq = self.service.create_equipment(payload)

        updated = self.service.update_equipment(eq.id, {"notes": "Recalibrated sensor"})
        self.assertEqual(updated.notes, "Recalibrated sensor")

        status_changed = self.service.change_equipment_status(eq.id, "OUT_OF_SERVICE", reason="Sensor drift")
        self.assertEqual(status_changed.status, EquipmentStatus.OUT_OF_SERVICE)

    def test_04_invalid_equipment_data(self):
        """Verify validation errors on missing fields and invalid dates."""
        # Missing required field
        with self.assertRaises(EquipmentValidationError) as ctx:
            self.service.create_equipment({"name": "No Serial"})
        self.assertIn("required", str(ctx.exception).lower())

        # Due date earlier than calibration date
        with self.assertRaises(EquipmentValidationError) as ctx:
            self.service.create_equipment({
                "name": "Bad Dates",
                "type": "OTHER",
                "serial_number": "SN-BAD-01",
                "manufacturer": "Mfr",
                "model": "Mod",
                "calibration_certificate": "CERT",
                "calibration_date": "2026-06-01",
                "calibration_due_date": "2026-01-01",
            })
        self.assertIn("earlier", str(ctx.exception).lower())

    def test_05_duplicate_serial_number_rejected(self):
        """Verify uniqueness enforcement on equipment serial number."""
        payload = {
            "name": "Standard Scale",
            "type": "STANDARD",
            "serial_number": "SN-DUP-01",
            "manufacturer": "Mfr",
            "model": "Mod",
            "calibration_certificate": "CERT",
            "calibration_date": self.past_date,
            "calibration_due_date": self.future_date,
        }
        self.service.create_equipment(payload)
        with self.assertRaises(DuplicateSerialNumberError):
            self.service.create_equipment(payload)

    def test_06_expired_calibration_equipment(self):
        """Verify that equipment with past due date is marked unusable with CALIBRATION_EXPIRED."""
        eq = Equipment(
            id="EQ-EXP-01",
            name="Old Thermometer",
            type="THERMOMETER",
            serial_number="SN-OLD-01",
            manufacturer="Generic",
            model="T1",
            calibration_certificate="OLD-CERT",
            calibration_date=self.long_past_date,
            calibration_due_date=self.past_date,  # expired 30 days ago
            status=EquipmentStatus.ACTIVE,
        )
        usable, err_code, reason = eq.is_usable()
        self.assertFalse(usable)
        self.assertEqual(err_code, "CALIBRATION_EXPIRED")
        self.assertIn("expired", reason.lower())

    def test_07_out_of_service_equipment(self):
        """Verify that equipment marked OUT_OF_SERVICE is not usable."""
        eq = Equipment(
            id="EQ-OOS-01",
            name="Broken Barometer",
            type="BAROMETER",
            serial_number="SN-OOS-01",
            manufacturer="Generic",
            model="B1",
            calibration_certificate="CERT",
            calibration_date=self.past_date,
            calibration_due_date=self.future_date,
            status=EquipmentStatus.OUT_OF_SERVICE,
        )
        usable, err_code, reason = eq.is_usable()
        self.assertFalse(usable)
        self.assertEqual(err_code, "EQUIPMENT_OUT_OF_SERVICE")

    # =========================================================================
    # Test Standards / Reference Weights Tests
    # =========================================================================

    def test_10_create_valid_test_standard(self):
        """Verify registering a valid reference test weight."""
        payload = {
            "nominal_value": 20.0,
            "unit": "kg",
            "accuracy_class": "F1",
            "serial_number": "SN-WT-20KG-01",
            "certificate_number": "NPL-CAL-2026-20KG",
            "calibration_date": self.past_date,
            "expiry_date": self.future_date,
            "status": "ACTIVE",
        }
        std = self.service.create_test_standard(payload)
        self.assertIsNotNone(std.id)
        self.assertEqual(std.nominal_value, 20.0)
        self.assertEqual(std.unit, "kg")
        self.assertEqual(std.accuracy_class, "F1")
        self.assertEqual(std.status, EquipmentStatus.ACTIVE)
        usable, err_code, _ = std.is_usable()
        self.assertTrue(usable)
        self.assertIsNone(err_code)

    def test_11_retrieve_and_list_test_standards(self):
        """Verify retrieving test standards by ID and filtering by class/unit."""
        payload = {
            "nominal_value": 500.0,
            "unit": "g",
            "accuracy_class": "E2",
            "serial_number": "SN-WT-500G-01",
            "certificate_number": "RRSL-CAL-500G",
            "calibration_date": self.past_date,
            "expiry_date": self.future_date,
        }
        created = self.service.create_test_standard(payload)

        fetched = self.service.get_test_standard(created.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.nominal_value, 500.0)

        # Filter by accuracy class
        class_e2 = self.service.list_test_standards(accuracy_class="E2")
        self.assertEqual(len(class_e2), 1)
        self.assertEqual(class_e2[0].id, created.id)

    def test_12_update_test_standard(self):
        """Verify updating test standard nominal value and certificate."""
        payload = {
            "nominal_value": 10.0,
            "unit": "kg",
            "accuracy_class": "M1",
            "serial_number": "SN-WT-10KG-01",
            "certificate_number": "CERT-10KG",
            "calibration_date": self.past_date,
            "expiry_date": self.future_date,
        }
        std = self.service.create_test_standard(payload)
        updated = self.service.update_test_standard(std.id, {"certificate_number": "NEW-CERT-10KG"})
        self.assertEqual(updated.certificate_number, "NEW-CERT-10KG")

        status_changed = self.service.change_test_standard_status(std.id, "OUT_OF_SERVICE")
        self.assertEqual(status_changed.status, EquipmentStatus.OUT_OF_SERVICE)

    def test_13_invalid_test_standard_data(self):
        """Verify validation errors for bad nominal values, invalid units, and bad dates."""
        # Non-positive nominal value
        with self.assertRaises(EquipmentValidationError) as ctx:
            self.service.create_test_standard({
                "nominal_value": -5.0,
                "unit": "kg",
                "accuracy_class": "M1",
                "serial_number": "SN-NEG-01",
                "certificate_number": "CERT",
                "calibration_date": self.past_date,
                "expiry_date": self.future_date,
            })
        self.assertIn("positive", str(ctx.exception).lower())

        # Invalid unit
        with self.assertRaises(EquipmentValidationError) as ctx:
            self.service.create_test_standard({
                "nominal_value": 10.0,
                "unit": "pounds",
                "accuracy_class": "M1",
                "serial_number": "SN-LBS-01",
                "certificate_number": "CERT",
                "calibration_date": self.past_date,
                "expiry_date": self.future_date,
            })
        self.assertIn("unit", str(ctx.exception).lower())

        # Duplicate serial number
        payload = {
            "nominal_value": 1.0,
            "unit": "kg",
            "accuracy_class": "F2",
            "serial_number": "SN-WT-DUP-01",
            "certificate_number": "CERT",
            "calibration_date": self.past_date,
            "expiry_date": self.future_date,
        }
        self.service.create_test_standard(payload)
        with self.assertRaises(DuplicateSerialNumberError):
            self.service.create_test_standard(payload)

    def test_14_expired_test_standard(self):
        """Verify that a test standard with an expired calibration date is unusable."""
        std = TestStandard(
            id="STD-EXP-01",
            nominal_value=5.0,
            unit="kg",
            accuracy_class="M1",
            serial_number="SN-WT-EXP-01",
            certificate_number="EXP-CERT",
            calibration_date=self.long_past_date,
            expiry_date=self.past_date,  # expired 30 days ago
            status=EquipmentStatus.ACTIVE,
        )
        usable, err_code, reason = std.is_usable()
        self.assertFalse(usable)
        self.assertEqual(err_code, "CALIBRATION_EXPIRED")
        self.assertIn("expired", reason.lower())

    def test_15_out_of_service_test_standard(self):
        """Verify that a test standard marked OUT_OF_SERVICE is not usable."""
        std = TestStandard(
            id="STD-OOS-01",
            nominal_value=1.0,
            unit="kg",
            accuracy_class="M1",
            serial_number="SN-WT-OOS-01",
            certificate_number="CERT",
            calibration_date=self.past_date,
            expiry_date=self.future_date,
            status=EquipmentStatus.OUT_OF_SERVICE,
        )
        usable, err_code, reason = std.is_usable()
        self.assertFalse(usable)
        self.assertEqual(err_code, "STANDARD_OUT_OF_SERVICE")

    # =========================================================================
    # Job Association & Calibration Validity Enforcement
    # =========================================================================

    def test_20_associate_valid_equipment_with_job(self):
        """Verify associating a valid, calibrated equipment item with a job."""
        job = TestJob(job_id="JOB-EQ-01", instrument_id="INST-01", status=JobStatus.IN_PROGRESS)
        self.jobs.save(job)

        eq = self.service.create_equipment({
            "name": "Valid Barometer",
            "type": "BAROMETER",
            "serial_number": "SN-ASSOC-01",
            "manufacturer": "Vaisala",
            "model": "PTB",
            "calibration_certificate": "CERT-VAI",
            "calibration_date": self.past_date,
            "calibration_due_date": self.future_date,
            "status": "ACTIVE",
        })

        updated_job = self.service.associate_equipment_with_job(job.job_id, eq.id)
        self.assertIn(eq.id, updated_job.equipment_ids)
        self.assertIn(eq.id, updated_job.to_dict()["equipment_ids"])

        # Fetch associated list
        items = self.service.get_job_equipment(job.job_id)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, eq.id)

    def test_21_associate_valid_test_standard_with_job(self):
        """Verify associating a valid, calibrated test standard with a job."""
        job = TestJob(job_id="JOB-STD-01", instrument_id="INST-01", status=JobStatus.IN_PROGRESS)
        self.jobs.save(job)

        std = self.service.create_test_standard({
            "nominal_value": 20.0,
            "unit": "kg",
            "accuracy_class": "F1",
            "serial_number": "SN-STD-ASSOC-01",
            "certificate_number": "CERT-STD-20",
            "calibration_date": self.past_date,
            "expiry_date": self.future_date,
            "status": "ACTIVE",
        })

        updated_job = self.service.associate_test_standard_with_job(job.job_id, std.id)
        self.assertIn(std.id, updated_job.test_standard_ids)

        standards = self.service.get_job_test_standards(job.job_id)
        self.assertEqual(len(standards), 1)
        self.assertEqual(standards[0].id, std.id)

    def test_22_reject_expired_equipment_association(self):
        """Verify that attempting to associate expired equipment raises CalibrationExpiredError."""
        job = TestJob(job_id="JOB-REJ-01", instrument_id="INST-01", status=JobStatus.IN_PROGRESS)
        self.jobs.save(job)

        expired_eq = Equipment(
            id="EQ-EXP-ASSOC",
            name="Expired Thermometer",
            type="THERMOMETER",
            serial_number="SN-EXP-ASSOC",
            manufacturer="Fluke",
            model="1524",
            calibration_certificate="EXP-CERT",
            calibration_date=self.long_past_date,
            calibration_due_date=self.past_date,  # expired
            status=EquipmentStatus.ACTIVE,
        )
        self.repo.save_equipment(expired_eq)

        with self.assertRaises(CalibrationExpiredError) as ctx:
            self.service.associate_equipment_with_job(job.job_id, expired_eq.id)
        self.assertEqual(ctx.exception.error_code, "CALIBRATION_EXPIRED")
        self.assertEqual(ctx.exception.item_id, expired_eq.id)
        self.assertEqual(ctx.exception.serial_number, expired_eq.serial_number)

        # Verify not added to job
        self.assertNotIn(expired_eq.id, self.jobs.get(job.job_id).equipment_ids)

    def test_23_reject_expired_test_standard_association(self):
        """Verify that attempting to associate expired test standard raises CalibrationExpiredError."""
        job = TestJob(job_id="JOB-REJ-02", instrument_id="INST-01", status=JobStatus.IN_PROGRESS)
        self.jobs.save(job)

        expired_std = TestStandard(
            id="STD-EXP-ASSOC",
            nominal_value=10.0,
            unit="kg",
            accuracy_class="M1",
            serial_number="SN-STD-EXP-ASSOC",
            certificate_number="EXP-CERT",
            calibration_date=self.long_past_date,
            expiry_date=self.past_date,  # expired
            status=EquipmentStatus.ACTIVE,
        )
        self.repo.save_standard(expired_std)

        with self.assertRaises(CalibrationExpiredError) as ctx:
            self.service.associate_test_standard_with_job(job.job_id, expired_std.id)
        self.assertEqual(ctx.exception.error_code, "CALIBRATION_EXPIRED")
        self.assertEqual(ctx.exception.item_id, expired_std.id)
        self.assertEqual(ctx.exception.serial_number, expired_std.serial_number)

        # Verify not added to job
        self.assertNotIn(expired_std.id, self.jobs.get(job.job_id).test_standard_ids)

    def test_24_reject_out_of_service_equipment_association(self):
        """Verify that associating OUT_OF_SERVICE equipment is rejected."""
        job = TestJob(job_id="JOB-REJ-03", instrument_id="INST-01", status=JobStatus.IN_PROGRESS)
        self.jobs.save(job)

        oos_eq = Equipment(
            id="EQ-OOS-ASSOC",
            name="OOS Hygrometer",
            type="HYGROMETER",
            serial_number="SN-OOS-ASSOC",
            manufacturer="Testo",
            model="608",
            calibration_certificate="CERT",
            calibration_date=self.past_date,
            calibration_due_date=self.future_date,
            status=EquipmentStatus.OUT_OF_SERVICE,
        )
        self.repo.save_equipment(oos_eq)

        with self.assertRaises(CalibrationExpiredError) as ctx:
            self.service.associate_equipment_with_job(job.job_id, oos_eq.id)
        self.assertEqual(ctx.exception.error_code, "EQUIPMENT_OUT_OF_SERVICE")

    def test_25_reject_out_of_service_standard_association(self):
        """Verify that associating OUT_OF_SERVICE test standard is rejected."""
        job = TestJob(job_id="JOB-REJ-04", instrument_id="INST-01", status=JobStatus.IN_PROGRESS)
        self.jobs.save(job)

        oos_std = TestStandard(
            id="STD-OOS-ASSOC",
            nominal_value=5.0,
            unit="kg",
            accuracy_class="F1",
            serial_number="SN-OOS-STD",
            certificate_number="CERT",
            calibration_date=self.past_date,
            expiry_date=self.future_date,
            status=EquipmentStatus.OUT_OF_SERVICE,
        )
        self.repo.save_standard(oos_std)

        with self.assertRaises(CalibrationExpiredError) as ctx:
            self.service.associate_test_standard_with_job(job.job_id, oos_std.id)
        self.assertEqual(ctx.exception.error_code, "STANDARD_OUT_OF_SERVICE")


class TestP5EquipmentAPI(unittest.TestCase):
    """Integration tests for Equipment & Test Standards REST APIs."""

    @classmethod
    def setUpClass(cls) -> None:
        if not HAS_TEST_CLIENT:
            raise unittest.SkipTest("FastAPI TestClient not available")
        cls.client = TestClient(app)

    def setUp(self) -> None:
        self.today = datetime.now(timezone.utc).date()
        self.future_date = (self.today + timedelta(days=365)).isoformat()
        self.past_date = (self.today - timedelta(days=30)).isoformat()

        # Ensure a clean job exists
        self.job = TestJob(
            job_id="API-JOB-EQ-01",
            instrument_id="INST-API-01",
            status=JobStatus.IN_PROGRESS,
            created_by="API_TESTER",
        )
        TEST_JOB_REPOSITORY.save(self.job)

    def test_30_api_equipment_crud(self):
        """Test POST, GET, PUT, and PATCH for equipment via REST endpoints."""
        # 1. Create equipment
        res = self.client.post(
            "/equipment",
            json={
                "name": "API Thermometer",
                "type": "THERMOMETER",
                "serial_number": "SN-API-TH-01",
                "manufacturer": "Fluke",
                "model": "1524",
                "calibration_certificate": "CAL-API-01",
                "calibration_date": self.past_date,
                "calibration_due_date": self.future_date,
                "status": "ACTIVE",
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        eq_id = data["data"]["id"]

        # 2. Get equipment
        get_res = self.client.get(f"/equipment/{eq_id}")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["data"]["serial_number"], "SN-API-TH-01")

        # 3. Update equipment
        put_res = self.client.put(f"/equipment/{eq_id}", json={"notes": "Updated via API"})
        self.assertEqual(put_res.status_code, 200)
        self.assertEqual(put_res.json()["data"]["notes"], "Updated via API")

        # 4. Patch status
        patch_res = self.client.patch(f"/equipment/{eq_id}/status", json={"status": "OUT_OF_SERVICE"})
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.json()["data"]["status"], "OUT_OF_SERVICE")

    def test_31_api_test_standards_crud(self):
        """Test POST, GET, PUT, and PATCH for test standards via REST endpoints."""
        # 1. Create standard
        res = self.client.post(
            "/test-standards",
            json={
                "nominal_value": 20.0,
                "unit": "kg",
                "accuracy_class": "F1",
                "serial_number": "SN-API-WT-01",
                "certificate_number": "CAL-WT-API-01",
                "calibration_date": self.past_date,
                "expiry_date": self.future_date,
                "status": "ACTIVE",
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        std_id = data["data"]["id"]

        # 2. Get standard
        get_res = self.client.get(f"/test-standards/{std_id}")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["data"]["nominal_value"], 20.0)

        # 3. Update standard
        put_res = self.client.put(f"/test-standards/{std_id}", json={"certificate_number": "UPDATED-CERT"})
        self.assertEqual(put_res.status_code, 200)
        self.assertEqual(put_res.json()["data"]["certificate_number"], "UPDATED-CERT")

        # 4. Patch status
        patch_res = self.client.patch(f"/test-standards/{std_id}/status", json={"status": "EXPIRED"})
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.json()["data"]["status"], "EXPIRED")

    def test_32_api_associate_equipment_and_standards_with_job(self):
        """Test job association and calibration validity check over REST API."""
        # Create valid equipment
        eq_res = self.client.post(
            "/equipment",
            json={
                "name": "API Barometer",
                "type": "BAROMETER",
                "serial_number": "SN-API-BARO-VALID",
                "manufacturer": "Vaisala",
                "model": "PTB",
                "calibration_certificate": "CAL-01",
                "calibration_date": self.past_date,
                "calibration_due_date": self.future_date,
            },
        )
        eq_id = eq_res.json()["data"]["id"]

        # Associate valid equipment with job
        assoc_eq_res = self.client.post(
            f"/jobs/{self.job.job_id}/equipment",
            json={"equipment_id": eq_id},
        )
        self.assertEqual(assoc_eq_res.status_code, 200)
        self.assertIn(eq_id, assoc_eq_res.json()["equipment_ids"])

        # Fetch job equipment
        list_eq_res = self.client.get(f"/jobs/{self.job.job_id}/equipment")
        self.assertEqual(list_eq_res.status_code, 200)
        self.assertEqual(len(list_eq_res.json()["data"]), 1)

        # Create valid standard
        std_res = self.client.post(
            "/test-standards",
            json={
                "nominal_value": 10.0,
                "unit": "kg",
                "accuracy_class": "M1",
                "serial_number": "SN-API-STD-VALID",
                "certificate_number": "CAL-STD-01",
                "calibration_date": self.past_date,
                "expiry_date": self.future_date,
            },
        )
        std_id = std_res.json()["data"]["id"]

        # Associate valid standard with job
        assoc_std_res = self.client.post(
            f"/jobs/{self.job.job_id}/test-standards",
            json={"test_standard_id": std_id},
        )
        self.assertEqual(assoc_std_res.status_code, 200)
        self.assertIn(std_id, assoc_std_res.json()["test_standard_ids"])

    def test_33_api_reject_expired_association(self):
        """Test REST API returns 400 with CALIBRATION_EXPIRED when associating expired items."""
        # Create expired equipment
        past_expired = (self.today - timedelta(days=60)).isoformat()
        eq_res = self.client.post(
            "/equipment",
            json={
                "name": "Expired Gauge",
                "type": "GAUGE",
                "serial_number": "SN-API-EXP-EQ",
                "manufacturer": "Mfr",
                "model": "Mod",
                "calibration_certificate": "OLD-CERT",
                "calibration_date": (self.today - timedelta(days=400)).isoformat(),
                "calibration_due_date": past_expired,
            },
        )
        expired_eq_id = eq_res.json()["data"]["id"]

        # Try to associate with job
        assoc_res = self.client.post(
            f"/jobs/{self.job.job_id}/equipment",
            json={"equipment_id": expired_eq_id},
        )
        self.assertEqual(assoc_res.status_code, 400)
        err_data = assoc_res.json()
        self.assertEqual(err_data["error"], "CALIBRATION_EXPIRED")
        self.assertEqual(err_data["item_id"], expired_eq_id)
        self.assertEqual(err_data["serial_number"], "SN-API-EXP-EQ")


if __name__ == "__main__":
    unittest.main()
