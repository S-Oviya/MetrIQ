"""
MetrIQ Person 3 Test Suite — FastAPI REST Endpoints Integration
===============================================================
Tests HTTP REST endpoints for Instrument Registry, Model Approvals,
and Test Job workflows using FastAPI TestClient.
"""

import os
import sys
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from typing import Any, Dict, Optional

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.router import api_router
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

from app.api.instruments_router import (
    register_instrument,
    list_instruments,
    get_instrument_details,
    get_instrument_by_serial,
    update_instrument,
    delete_instrument,
    pre_validate_instrument,
    apply_seal,
    report_broken_seal,
    register_model_approval,
    list_model_approvals,
    get_model_approval,
    update_model_approval,
    transition_model_approval,
    link_instrument_to_model_approval,
    get_model_approval_instruments,
    verify_instrument_against_model,
    record_instrument_lifecycle_event,
    get_instrument_lifecycle_history,
    identify_instruments_requiring_verification,
    schedule_instrument_verification,
    create_instrument_verification_job,
    complete_verification_job_api,
    HTTPException,
)
from app.api.jobs_router import (
    create_test_job,
    list_jobs,
    get_job_details,
    get_job_test_plan,
    transition_job_status,
    assign_job_inspector,
    get_jobs_for_instrument,
    evaluate_job_location_routing,
    HTTPException as JobsHTTPException,
)


class MockResponse:
    def __init__(self, status_code: int, data: Any):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


class MockClient:
    def post(self, path: str, json: Optional[Dict[str, Any]] = None):
        json = json or {}
        try:
            if path == "/instruments":
                res = register_instrument(payload=json)
                return MockResponse(201, res)
            elif path == "/instruments/validate-feasibility":
                res = pre_validate_instrument(payload=json)
                return MockResponse(200, res)
            elif path == "/model-approvals":
                res = register_model_approval(payload=json)
                return MockResponse(201, res)
            elif path == "/model-approvals/verify-instrument":
                res = verify_instrument_against_model(instrument_payload=json)
                return MockResponse(200, res)
            elif path.startswith("/model-approvals/") and path.endswith("/transition"):
                ref = "/".join(path.split("/")[2:-1])
                res = transition_model_approval(reference=ref, payload=json)
                return MockResponse(200, res)
            elif path.startswith("/model-approvals/") and path.endswith("/link-instrument"):
                ref = "/".join(path.split("/")[2:-1])
                res = link_instrument_to_model_approval(reference=ref, payload=json)
                return MockResponse(200, res)
            elif path.startswith("/instruments/") and path.endswith("/seals"):
                inst_id = path.split("/")[2]
                res = apply_seal(instrument_id=inst_id, seal_payload=json)
                return MockResponse(200, res)
            elif path.startswith("/instruments/") and path.endswith("/seals/report-broken"):
                inst_id = path.split("/")[2]
                res = report_broken_seal(
                    instrument_id=inst_id,
                    seal_id=json.get("seal_id", ""),
                    reason=json.get("reason", ""),
                    reported_by=json.get("reported_by", ""),
                )
                return MockResponse(200, res)
            elif path.startswith("/instruments/") and path.endswith("/lifecycle-events"):
                inst_id = path.split("/")[2]
                res = record_instrument_lifecycle_event(instrument_id=inst_id, payload=json)
                return MockResponse(200, res)
            elif path == "/jobs":
                res = create_test_job(payload=json)
                return MockResponse(201, res)
            elif path.startswith("/jobs/") and path.endswith("/transition"):
                job_id = path.split("/")[2]
                res = transition_job_status(
                    job_id=job_id,
                    to_status=json.get("to_status", ""),
                    user_id=json.get("user_id", "SYSTEM"),
                    reason=json.get("reason", ""),
                    metadata=json.get("metadata"),
                )
                return MockResponse(200, res)
            elif path.startswith("/jobs/") and path.endswith("/assign"):
                job_id = path.split("/")[2]
                res = assign_job_inspector(
                    job_id=job_id,
                    inspector_id=json.get("inspector_id", ""),
                    inspector_name=json.get("inspector_name", ""),
                    testing_centre_id=json.get("testing_centre_id"),
                    testing_centre_name=json.get("testing_centre_name"),
                    scheduled_date=json.get("scheduled_date"),
                    assigned_by=json.get("assigned_by", "SYSTEM"),
                )
                return MockResponse(200, res)
            elif path.startswith("/instruments/") and path.endswith("/schedule-verification"):
                inst_id = path.split("/")[2]
                res = schedule_instrument_verification(instrument_id=inst_id, payload=json)
                return MockResponse(200, res)
            elif path.startswith("/instruments/") and path.endswith("/create-verification-job"):
                inst_id = path.split("/")[2]
                res = create_instrument_verification_job(instrument_id=inst_id, payload=json)
                return MockResponse(201, res)
            elif path.startswith("/jobs/") and path.endswith("/complete-verification"):
                job_id = path.split("/")[2]
                res = complete_verification_job_api(job_id=job_id, payload=json)
                return MockResponse(200, res)
            elif path == "/jobs/evaluate-location-routing":
                res = evaluate_job_location_routing(payload=json)
                return MockResponse(200, res)
            return MockResponse(404, {"detail": f"Route not found: {path}"})
        except (HTTPException, JobsHTTPException) as e:
            if isinstance(e.detail, dict):
                payload = dict(e.detail)
                if "detail" not in payload:
                    payload["detail"] = payload.get("message", str(payload))
                return MockResponse(e.status_code, payload)
            return MockResponse(e.status_code, {"detail": e.detail})

    def get(self, path: str, params: Optional[Dict[str, Any]] = None):
        try:
            if path == "/instruments":
                params = params or {}
                res = list_instruments(
                    status=params.get("status"),
                    accuracy_class=params.get("accuracy_class"),
                    instrument_type=params.get("instrument_type"),
                    usage_type=params.get("usage_type"),
                    verification_status=params.get("verification_status"),
                    approval_status=params.get("approval_status"),
                    gatc_code=params.get("gatc_code"),
                    manufacturer=params.get("manufacturer"),
                    customer=params.get("customer"),
                    search=params.get("search"),
                )
                return MockResponse(200, res)
            elif path.startswith("/instruments/by-serial/"):
                serial = path.split("/")[3]
                res = get_instrument_by_serial(serial_number=serial)
                return MockResponse(200, res)
            elif path == "/model-approvals":
                params = params or {}
                res = list_model_approvals(
                    manufacturer=params.get("manufacturer"),
                    accuracy_class=params.get("accuracy_class"),
                    status=params.get("status"),
                    instrument_type=params.get("instrument_type"),
                    search=params.get("search"),
                    valid_only=params.get("valid_only", False),
                )
                return MockResponse(200, res)
            elif path.startswith("/model-approvals/") and path.endswith("/instruments"):
                ref = "/".join(path.split("/")[2:-1])
                res = get_model_approval_instruments(reference=ref)
                return MockResponse(200, res)
            elif path.startswith("/model-approvals/"):
                approval_no = "/".join(path.split("/")[2:])
                res = get_model_approval(reference=approval_no)
                return MockResponse(200, res)
            elif path == "/jobs":
                params = params or {}
                res = list_jobs(
                    status=params.get("status"),
                    job_type=params.get("job_type"),
                    instrument_id=params.get("instrument_id"),
                    inspector_id=params.get("inspector_id"),
                    search=params.get("search"),
                )
                return MockResponse(200, res)
            elif path.startswith("/jobs/") and path.endswith("/test-plan"):
                job_id = path.split("/")[2]
                res = get_job_test_plan(job_id=job_id)
                return MockResponse(200, res)
            elif path.startswith("/jobs/instrument/"):
                inst_id = path.split("/")[3]
                res = get_jobs_for_instrument(instrument_id=inst_id)
                return MockResponse(200, res)
            elif path.startswith("/jobs/"):
                job_id = path.split("/")[2]
                res = get_job_details(job_id=job_id)
                return MockResponse(200, res)
            elif path.startswith("/instruments/") and path.endswith("/lifecycle-history"):
                inst_id = path.split("/")[2]
                res = get_instrument_lifecycle_history(instrument_id=inst_id)
                return MockResponse(200, res)
            elif path == "/instruments/requiring-verification":
                params = params or {}
                res = identify_instruments_requiring_verification(
                    as_of_date=params.get("as_of_date"),
                    state=params.get("state"),
                    reminder_window_days=int(params.get("reminder_window_days", 30)),
                    include_manual_review=params.get("include_manual_review", True),
                )
                return MockResponse(200, res)
            elif path.startswith("/instruments/"):
                inst_id = path.split("/")[2]
                res = get_instrument_details(instrument_id=inst_id)
                return MockResponse(200, res)
            return MockResponse(404, {"detail": f"Route not found: {path}"})
        except (HTTPException, JobsHTTPException) as e:
            detail_val = e.detail if isinstance(e.detail, dict) else {"detail": e.detail}
            return MockResponse(e.status_code, detail_val)

    def put(self, path: str, json: Optional[Dict[str, Any]] = None):
        json = json or {}
        try:
            if path.startswith("/instruments/"):
                inst_id = path.split("/")[2]
                res = update_instrument(instrument_id=inst_id, payload=json)
                return MockResponse(200, res)
            elif path.startswith("/model-approvals/"):
                ref = "/".join(path.split("/")[2:])
                res = update_model_approval(reference=ref, payload=json)
                return MockResponse(200, res)
            return MockResponse(404, {"detail": f"Route not found: {path}"})
        except HTTPException as e:
            return MockResponse(e.status_code, {"detail": e.detail})

    def delete(self, path: str):
        try:
            if path.startswith("/instruments/"):
                inst_id = path.split("/")[2]
                res = delete_instrument(instrument_id=inst_id)
                return MockResponse(200, res)
            return MockResponse(404, {"detail": f"Route not found: {path}"})
        except HTTPException as e:
            return MockResponse(e.status_code, {"detail": e.detail})


class TestP3API(unittest.TestCase):
    """Integration tests for Person 3 FastAPI endpoints."""

    def setUp(self) -> None:
        if HAS_FASTAPI:
            self.app = FastAPI(title="MetrIQ Test Suite")
            self.app.include_router(api_router)
            self.client = TestClient(self.app)
        else:
            self.client = MockClient()

    def test_01_post_instrument_success(self):
        """Verify POST /instruments with valid metrology returns 201 Created."""
        payload = {
            "instrument_id": "INST-API-001",
            "serial_number": "SN-API-001",
            "manufacturer": "Essae-Teraoka Ltd.",
            "model_name": "API Retail Counter",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "model_approval_number": "IND/09/2024/001",
        }
        resp = self.client.post("/instruments", json=payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["instrument_id"], "INST-API-001")

    def test_02_post_instrument_invalid_metrology_rejected(self):
        """Verify POST /instruments with invalid step sequence returns 422."""
        invalid_payload = {
            "instrument_id": "INST-API-BAD",
            "serial_number": "SN-API-BAD",
            "manufacturer": "Bad Mfr",
            "model_name": "Bad Scale",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.003, # 3 is invalid step sequence
            "d": 0.003,
            "unit": "kg",
        }
        resp = self.client.post("/instruments", json=invalid_payload)
        self.assertEqual(resp.status_code, 422)
        data = resp.json()
        self.assertIn("detail", data)

    def test_03_get_instruments_list_and_details(self):
        """Verify GET /instruments and GET /instruments/{id}."""
        list_resp = self.client.get("/instruments")
        self.assertEqual(list_resp.status_code, 200)
        list_data = list_resp.json()
        self.assertTrue(list_data["success"])
        self.assertGreater(list_data["count"], 0)

        # Get existing seed instrument
        detail_resp = self.client.get("/instruments/INST-RETAIL-001")
        self.assertEqual(detail_resp.status_code, 200)
        detail_data = detail_resp.json()
        self.assertEqual(detail_data["data"]["instrument_id"], "INST-RETAIL-001")

    def test_04_post_validate_feasibility(self):
        """Verify POST /instruments/validate-feasibility calls Person 2 without saving."""
        check_payload = {
            "accuracy_class": "III",
            "Max": 30.0,
            "Min": 0.2,
            "e": 0.01,
            "d": 0.01,
            "unit": "kg",
        }
        resp = self.client.post("/instruments/validate-feasibility", json=check_payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["data"]["valid"])

    def test_05_model_approval_endpoints(self):
        """Verify model approval registration, listing, and instrument verification."""
        # List approvals
        list_resp = self.client.get("/model-approvals")
        self.assertEqual(list_resp.status_code, 200)
        self.assertGreater(list_resp.json()["count"], 0)

        # Get specific certificate
        cert_resp = self.client.get("/model-approvals/IND/09/2024/001")
        self.assertEqual(cert_resp.status_code, 200)
        self.assertEqual(cert_resp.json()["data"]["approval_number"], "IND/09/2024/001")

        # Verify instrument envelope
        inst_payload = {
            "instrument_id": "INST-MA-CHECK",
            "serial_number": "SN-MA-CHECK",
            "manufacturer": "Essae-Teraoka Ltd.",
            "model_name": "DS-215",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "model_approval_number": "IND/09/2024/001",
        }
        verify_resp = self.client.post("/model-approvals/verify-instrument", json=inst_payload)
        self.assertEqual(verify_resp.status_code, 200)
        self.assertTrue(verify_resp.json()["compliant"])

    def test_06_test_job_lifecycle_via_api(self):
        """
        Verify complete Test Job lifecycle via REST endpoints:
        POST /jobs -> GET /jobs/{id} -> GET /jobs/{id}/test-plan -> POST /jobs/{id}/assign -> POST /jobs/{id}/transition
        """
        # 1. Create Job
        create_payload = {
            "job_id": "JOB-API-001",
            "instrument_id": "INST-RETAIL-001",
            "job_type": "RE_VERIFICATION",
            "priority": "HIGH",
        }
        res_create = self.client.post("/jobs", json=create_payload)
        self.assertEqual(res_create.status_code, 201)
        job_data = res_create.json()
        self.assertTrue(job_data["success"])
        self.assertTrue(job_data["has_test_plan"])

        # 2. Retrieve Job Details
        res_get = self.client.get("/jobs/JOB-API-001")
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.json()["data"]["job_id"], "JOB-API-001")

        # 3. Person 4 retrieves test plan
        res_plan = self.client.get("/jobs/JOB-API-001/test-plan")
        self.assertEqual(res_plan.status_code, 200)
        plan_data = res_plan.json()
        self.assertIn("tests", plan_data["data"])

        # 4. Assign Inspector
        res_assign = self.client.post(
            "/jobs/JOB-API-001/assign",
            json={
                "inspector_id": "INSP-API-99",
                "inspector_name": "Insp. Priya Sharma",
                "testing_centre_id": "GATC-001",
            },
        )
        self.assertEqual(res_assign.status_code, 200)
        self.assertEqual(res_assign.json()["data"]["status"], "ASSIGNED")

        # 5. Transition to IN_PROGRESS
        res_trans = self.client.post(
            "/jobs/JOB-API-001/transition",
            json={
                "to_status": "IN_PROGRESS",
                "user_id": "INSP-API-99",
                "reason": "Started weighing performance test",
            },
        )
        self.assertEqual(res_trans.status_code, 200)
        self.assertEqual(res_trans.json()["data"]["status"], "IN_PROGRESS")

    def test_07_get_instrument_by_serial_success_and_not_found(self):
        """Verify GET /instruments/by-serial/{serial_number} returns 200 or 404."""
        # 1. Successful lookup of existing seed instrument
        resp_ok = self.client.get("/instruments/by-serial/ESSAE-2024-9981")
        self.assertEqual(resp_ok.status_code, 200)
        data = resp_ok.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["instrument_id"], "INST-RETAIL-001")
        self.assertEqual(data["data"]["serial_number"], "ESSAE-2024-9981")

        # 2. 404 for non-existent serial
        resp_404 = self.client.get("/instruments/by-serial/NON-EXISTENT-SN-999")
        self.assertEqual(resp_404.status_code, 404)

    def test_08_post_instrument_chronological_dates_validation(self):
        """Verify POST /instruments rejects chronologically impossible lifecycle dates with 422."""
        # Case A: Installed date before Manufactured date
        invalid_dates_payload = {
            "instrument_id": "INST-API-CHRONO-1",
            "serial_number": "SN-API-CHRONO-1",
            "manufacturer": "Essae-Teraoka Ltd.",
            "model_name": "DS-215",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "manufactured_date": "2024-06-01",
            "installed_date": "2023-01-01",  # Impossible: installed before manufactured
        }
        resp_a = self.client.post("/instruments", json=invalid_dates_payload)
        self.assertEqual(resp_a.status_code, 422)

        # Case B: Repair date before Installed date
        invalid_repair_payload = {
            "instrument_id": "INST-API-CHRONO-2",
            "serial_number": "SN-API-CHRONO-2",
            "manufacturer": "Essae-Teraoka Ltd.",
            "model_name": "DS-215",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "manufactured_date": "2023-01-01",
            "installed_date": "2023-06-01",
            "repair_date": "2022-01-01",  # Impossible: repaired before installed
        }
        resp_b = self.client.post("/instruments", json=invalid_repair_payload)
        self.assertEqual(resp_b.status_code, 422)

    def test_09_instruments_query_filters_and_search(self):
        """Verify GET /instruments filters by GATC code, usage type, and search keyword."""
        # Filter by GATC
        resp_gatc = self.client.get("/instruments", params={"gatc_code": "GATC-BLR-01"})
        self.assertEqual(resp_gatc.status_code, 200)
        items_gatc = resp_gatc.json()["data"]
        self.assertTrue(all(item.get("gatc_code") == "GATC-BLR-01" for item in items_gatc))

        # Filter by usage type
        resp_usage = self.client.get("/instruments", params={"usage_type": "COMMERCIAL_TRADE"})
        self.assertEqual(resp_usage.status_code, 200)
        items_usage = resp_usage.json()["data"]
        self.assertTrue(all(item.get("usage_type") == "COMMERCIAL_TRADE" for item in items_usage))

        # Search keyword
        resp_search = self.client.get("/instruments", params={"search": "DS-215"})
        self.assertEqual(resp_search.status_code, 200)
        self.assertGreaterEqual(resp_search.json()["count"], 1)

    def test_10_update_and_delete_instrument_api(self):
        """Verify updating and deleting an instrument via REST API."""
        # 1. Create temporary instrument
        inst_payload = {
            "instrument_id": "INST-API-DEL",
            "serial_number": "SN-API-DEL",
            "manufacturer": "Essae-Teraoka Ltd.",
            "model_name": "DS-215",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "model_approval_number": "IND/09/2024/001",
        }
        resp_create = self.client.post("/instruments", json=inst_payload)
        self.assertEqual(resp_create.status_code, 201)

        # 2. Update instrument
        resp_update = self.client.put(
            "/instruments/INST-API-DEL",
            json={"description": "Updated retail scale via API"},
        )
        self.assertEqual(resp_update.status_code, 200)
        self.assertEqual(resp_update.json()["data"]["description"], "Updated retail scale via API")

        # 3. Lookup by serial succeeds
        resp_find = self.client.get("/instruments/by-serial/SN-API-DEL")
        self.assertEqual(resp_find.status_code, 200)

        # 4. Delete instrument
        resp_del = self.client.delete("/instruments/INST-API-DEL")
        self.assertEqual(resp_del.status_code, 200)

        # 5. Lookup by serial now returns 404
        resp_after_del = self.client.get("/instruments/by-serial/SN-API-DEL")
        self.assertEqual(resp_after_del.status_code, 404)

    def test_11_model_approval_api_lifecycle_and_association(self):
        """
        Verify complete Model Approval REST API workflows:
        POST (DRAFT) -> GET -> PUT -> POST transition (SUBMITTED -> UNDER_TESTING -> APPROVED) -> POST link-instrument -> GET instruments
        """
        app_payload = {
            "application_reference": "APP-API-FLOW-01",
            "model_number": "MDL-API-100",
            "model_name": "API Industrial Scale",
            "manufacturer": "MetrIQ Systems India",
            "instrument_type": "BENCH_SCALE",
            "accuracy_class": "III",
            "Max": 50.0,
            "Min": 0.4,
            "e": 0.02,
            "d": 0.02,
            "unit": "kg",
            "status": "DRAFT",
        }
        # 1. Create DRAFT
        resp = self.client.post("/model-approvals", json=app_payload)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["data"]["status"], "DRAFT")

        # 2. Retrieve by reference
        resp_get = self.client.get("/model-approvals/APP-API-FLOW-01")
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(resp_get.json()["data"]["model_number"], "MDL-API-100")

        # 3. Update metadata
        resp_put = self.client.put(
            "/model-approvals/APP-API-FLOW-01",
            json={"testing_laboratory": "National Physical Laboratory (NPL), New Delhi"},
        )
        self.assertEqual(resp_put.status_code, 200)

        # 4. Transition: DRAFT -> SUBMITTED
        resp_sub = self.client.post(
            "/model-approvals/APP-API-FLOW-01/transition",
            json={"to_status": "SUBMITTED"},
        )
        self.assertEqual(resp_sub.status_code, 200)
        self.assertEqual(resp_sub.json()["data"]["status"], "SUBMITTED")

        # 5. Transition: SUBMITTED -> UNDER_TESTING
        resp_test = self.client.post(
            "/model-approvals/APP-API-FLOW-01/transition",
            json={"to_status": "UNDER_TESTING"},
        )
        self.assertEqual(resp_test.status_code, 200)
        self.assertEqual(resp_test.json()["data"]["status"], "UNDER_TESTING")

        # 6. Transition: UNDER_TESTING -> APPROVED
        resp_app = self.client.post(
            "/model-approvals/APP-API-FLOW-01/transition",
            json={
                "to_status": "APPROVED",
                "approval_number": "IND/09/2026/999",
                "approval_date": "2026-03-01",
                "approval_mark": "IND-M-2026-999",
            },
        )
        self.assertEqual(resp_app.status_code, 200)
        self.assertEqual(resp_app.json()["data"]["status"], "APPROVED")

        # 7. Link instrument
        resp_link = self.client.post(
            "/model-approvals/APP-API-FLOW-01/link-instrument",
            json={"instrument_id": "INST-LINKED-001"},
        )
        self.assertEqual(resp_link.status_code, 200)
        self.assertIn("INST-LINKED-001", resp_link.json()["data"]["associated_instrument_ids"])

        # 8. Query associated instruments
        resp_insts = self.client.get("/model-approvals/APP-API-FLOW-01/instruments")
        self.assertEqual(resp_insts.status_code, 200)
        self.assertIn("INST-LINKED-001", resp_insts.json()["data"])

    def test_lifecycle_events_api(self):
        """Test recording lifecycle events and retrieving immutable history via REST API."""
        inst_payload = {
            "instrument_id": "INST-LC-API-001",
            "serial_number": "SN-LC-API-001",
            "manufacturer": "Essae-Teraoka",
            "model_name": "DS-215",
            "accuracy_class": "CLASS_III",
            "max_capacity": 30.0,
            "min_capacity": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "instrument_type": "ELECTRONIC_COUNTER_SCALE",
        }
        res_reg = self.client.post("/instruments", json=inst_payload)
        self.assertEqual(res_reg.status_code, 201)

        # 1. Transition to IN_VERIFICATION
        ev1 = {
            "event_type": "INITIAL_VERIFICATION",
            "new_status": "IN_VERIFICATION",
            "actor": "Inspector Rajesh",
            "notes": "Commencing initial verification tests",
        }
        res_ev1 = self.client.post("/instruments/INST-LC-API-001/lifecycle-events", json=ev1)
        self.assertEqual(res_ev1.status_code, 200)
        self.assertEqual(res_ev1.json()["instrument_status"], "IN_VERIFICATION")

        # 2. Transition to VERIFIED
        ev2 = {
            "event_type": "INITIAL_VERIFICATION",
            "new_status": "VERIFIED",
            "actor": "Inspector Rajesh",
            "notes": "Tests passed, stamp applied",
        }
        res_ev2 = self.client.post("/instruments/INST-LC-API-001/lifecycle-events", json=ev2)
        self.assertEqual(res_ev2.status_code, 200)
        self.assertEqual(res_ev2.json()["instrument_status"], "VERIFIED")

        # 3. Transition to IN_SERVICE
        ev3 = {
            "event_type": "IN_SERVICE_USE",
            "new_status": "IN_SERVICE",
            "actor": "Owner",
            "notes": "Placed in retail service",
        }
        res_ev3 = self.client.post("/instruments/INST-LC-API-001/lifecycle-events", json=ev3)
        self.assertEqual(res_ev3.status_code, 200)
        self.assertEqual(res_ev3.json()["instrument_status"], "IN_SERVICE")

        # 4. Dismantle
        ev4 = {
            "event_type": "DISMANTLING",
            "new_status": "DISMANTLED",
            "actor": "Field Tech",
            "notes": "Dismantled for premise relocation",
        }
        res_ev4 = self.client.post("/instruments/INST-LC-API-001/lifecycle-events", json=ev4)
        self.assertEqual(res_ev4.status_code, 200)
        self.assertEqual(res_ev4.json()["instrument_status"], "DISMANTLED")

        # 5. Attempt illegal jump: DISMANTLED -> IN_SERVICE (must fail)
        illegal_ev = {
            "event_type": "IN_SERVICE_USE",
            "new_status": "IN_SERVICE",
            "actor": "Field Tech",
            "notes": "Attempting to skip reinstallation and verification",
        }
        res_illegal = self.client.post("/instruments/INST-LC-API-001/lifecycle-events", json=illegal_ev)
        self.assertEqual(res_illegal.status_code, 400)

        # 6. Retrieve lifecycle history
        res_hist = self.client.get("/instruments/INST-LC-API-001/lifecycle-history")
        self.assertEqual(res_hist.status_code, 200)
        hist_data = res_hist.json()
        self.assertEqual(hist_data["instrument_id"], "INST-LC-API-001")
        # History contains: REGISTRATION, (MODEL_APPROVAL if applied), INITIAL_VERIFICATION x2, IN_SERVICE_USE, DISMANTLING
        self.assertGreaterEqual(hist_data["count"], 5)
        event_types = [e["event_type"] for e in hist_data["data"]]
        self.assertIn("REGISTRATION", event_types)
        self.assertIn("DISMANTLING", event_types)

    def test_scheduling_endpoints_api(self):
        """Test verification scheduling, queries, job creation, and completion via REST API."""
        # 1. Register instrument
        inst_payload = {
            "instrument_id": "INST-SCHED-API-001",
            "serial_number": "SN-SCHED-API-001",
            "manufacturer": "Avery Weigh-Tronix",
            "model_name": "E-1000",
            "accuracy_class": "CLASS_III",
            "max_capacity": 50.0,
            "min_capacity": 0.2,
            "e": 0.01,
            "d": 0.01,
            "unit": "kg",
            "instrument_type": "ELECTRONIC_BENCH_SCALE",
            "state": "Maharashtra",
        }
        res_reg = self.client.post("/instruments", json=inst_payload)
        self.assertEqual(res_reg.status_code, 201)

        # 2. Schedule verification (last date: 2025-06-01)
        sched_payload = {
            "last_verification_date": "2025-06-01",
            "verification_reason": "PERIODIC_EXPIRY",
            "profile_id": "IN_LM_2011_ACTIVE",
        }
        res_sched = self.client.post("/instruments/INST-SCHED-API-001/schedule-verification", json=sched_payload)
        self.assertEqual(res_sched.status_code, 200)
        sched_data = res_sched.json()
        self.assertEqual(sched_data["next_verification_date"], "2026-06-01")

        # 3. Query instruments requiring verification as of 2026-05-15 (within 30 days of 2026-06-01)
        res_due = self.client.get("/instruments/requiring-verification", params={"as_of_date": "2026-05-15", "reminder_window_days": 30})
        self.assertEqual(res_due.status_code, 200)
        due_data = res_due.json()
        due_ids = [item["instrument_id"] for item in due_data["items"]]
        self.assertIn("INST-SCHED-API-001", due_ids)

        # 4. Create verification test job
        job_payload = {
            "job_type": "RE_VERIFICATION",
            "scheduled_date": "2026-05-20",
            "notes": "Annual statutory reverification test",
            "created_by": "Officer Kulkarni",
        }
        res_job = self.client.post("/instruments/INST-SCHED-API-001/create-verification-job", json=job_payload)
        self.assertEqual(res_job.status_code, 201)
        job_res = res_job.json()
        job_id = job_res["job_id"]
        self.assertTrue(job_id.startswith("JOB-"))
        self.assertEqual(job_res["instrument_status"], "IN_VERIFICATION")

        # 5. Complete verification job
        comp_payload = {
            "job_outcome": "PASSED",
            "verification_certificate_number": "VC/MH/2026/789",
            "completed_by": "Inspector Rajesh",
            "notes": "Passed all tests within MPE",
        }
        res_comp = self.client.post(f"/jobs/{job_id}/complete-verification", json=comp_payload)
        self.assertEqual(res_comp.status_code, 200)
        comp_data = res_comp.json()
        self.assertEqual(comp_data["instrument_status"], "IN_SERVICE")
        self.assertEqual(comp_data["verification_status"], "VERIFIED")
        self.assertEqual(comp_data["verification_certificate_number"], "VC/MH/2026/789")
        # Next verification scheduled forward from completion date (e.g. +12 months)
        self.assertIsNotNone(comp_data["next_verification_date"])

    def test_location_and_routing_api(self):
        """Test verification location and GATC routing evaluation and job creation via REST API."""
        # 1. Register Class III 20kg scale
        res_inst1 = self.client.post("/instruments", json={
            "instrument_id": "INST-ROUTE-API-001",
            "serial_number": "SN-ROUTE-001",
            "manufacturer": "Essae-Teraoka",
            "model_name": "DS-852",
            "accuracy_class": "CLASS_III",
            "max_capacity": 20.0,
            "min_capacity": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "instrument_type": "ELECTRONIC_COUNTER_SCALE",
            "state": "Maharashtra",
            "district": "Pune",
        })
        self.assertEqual(res_inst1.status_code, 201)

        # 2. Register Class II 500g gold scale
        res_inst2 = self.client.post("/instruments", json={
            "instrument_id": "INST-ROUTE-API-002",
            "serial_number": "SN-ROUTE-002",
            "manufacturer": "Sartorius",
            "model_name": "Entris-II",
            "accuracy_class": "CLASS_II",
            "max_capacity": 500.0,
            "min_capacity": 0.5,
            "e": 0.01,
            "d": 0.001,
            "unit": "g",
            "instrument_type": "PRECISION_LABORATORY_BALANCE",
            "state": "Maharashtra",
            "district": "Mumbai",
        })
        self.assertEqual(res_inst2.status_code, 201)

        # 3. Evaluate location & routing for Class III <= 150 kg -> GATC
        res_eval1 = self.client.post("/jobs/evaluate-location-routing", json={
            "instrument_id": "INST-ROUTE-API-001",
            "job_type": "RE_VERIFICATION",
        })
        self.assertEqual(res_eval1.status_code, 200)
        eval1_data = res_eval1.json()["data"]
        self.assertEqual(eval1_data["routing_decision"], "GATC")
        self.assertEqual(eval1_data["verification_location_type"], "GATC_CENTRE")
        self.assertTrue(eval1_data["routing_result"]["eligible_for_gatc"])

        # 4. Evaluate location & routing for Class II -> State Legal Metrology Officer
        res_eval2 = self.client.post("/jobs/evaluate-location-routing", json={
            "instrument_id": "INST-ROUTE-API-002",
            "job_type": "RE_VERIFICATION",
        })
        self.assertEqual(res_eval2.status_code, 200)
        eval2_data = res_eval2.json()["data"]
        self.assertEqual(eval2_data["routing_decision"], "STATE_LEGAL_METROLOGY_OFFICER")
        self.assertFalse(eval2_data["routing_result"]["eligible_for_gatc"])
        self.assertIsNone(eval2_data["gatc_reference"])

        # 5. Create job for Class III with GATC metadata
        res_job1 = self.client.post("/jobs", json={
            "instrument_id": "INST-ROUTE-API-001",
            "job_type": "RE_VERIFICATION",
            "verification_location_type": "GATC_CENTRE",
            "gatc_reference": "GATC-MH-012",
            "testing_centre_name": "Pune Metrology GATC",
        })
        self.assertEqual(res_job1.status_code, 201)
        job1_data = res_job1.json()["data"]
        self.assertEqual(job1_data["verification_location_type"], "GATC_CENTRE")
        self.assertEqual(job1_data["laboratory"], "Pune Metrology GATC")
        self.assertEqual(job1_data["gatc_reference"], "GATC-MH-012")
        self.assertEqual(job1_data["routing_decision"], "GATC")

        # 6. Attempt to force GATC location on Class II scale with strict validation -> Must return 422
        res_job2_illegal = self.client.post("/jobs", json={
            "instrument_id": "INST-ROUTE-API-002",
            "job_type": "RE_VERIFICATION",
            "verification_location_type": "GATC_CENTRE",
            "strict_gatc_validation": True,
        })
        self.assertEqual(res_job2_illegal.status_code, 422)


if __name__ == "__main__":
    unittest.main()


