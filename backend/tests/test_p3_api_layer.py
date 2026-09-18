"""
MetrIQ Person 3 Test Suite — Complete API Layer Testing
======================================================
Validates all RESTful endpoints and high-level facades requested for Person 3:
1. Instruments:      POST, GET, GET /{id}, PUT/PATCH /{id}
2. Model Approvals:  POST, GET, GET /{approval_id}, PUT/PATCH /{approval_id}
3. Test Jobs:        POST /test-jobs, GET /test-jobs, GET /{id}, PUT/PATCH /{id},
                     POST /{id}/validate, POST /{id}/generate-plan
4. Lifecycle:        GET /{id}/lifecycle, POST /{id}/lifecycle-events
5. Verification:     GET /instruments/due-for-verification,
                     POST /instruments/{id}/verification-job,
                     POST /jobs/{id}/complete-verification
6. Person3API.dispatch testing for Person 1 integration
7. Proper HTTP status codes, consistent error envelopes, no leakage of internal details
"""

import os
import sys
import unittest
import uuid
from datetime import datetime, timezone

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.api.p3_api import Person3API
from app.api.instruments_router import (
    register_instrument,
    list_instruments,
    get_instrument_details,
    update_instrument,
    delete_instrument,
    register_model_approval,
    list_model_approvals,
    get_model_approval,
    update_model_approval,
    get_instrument_lifecycle_history,
    record_instrument_lifecycle_event,
    identify_instruments_requiring_verification,
    create_instrument_verification_job,
    complete_verification_job_api,
    HTTPException as InstrumentsHTTPException,
)
from app.api.jobs_router import (
    create_test_job,
    list_jobs,
    get_job_details,
    update_test_job,
    validate_test_job_api,
    generate_job_test_plan_api,
    get_job_test_plan,
    transition_job_status,
    assign_job_inspector,
    HTTPException as JobsHTTPException,
)


class TestP3APILayer(unittest.TestCase):
    """Thorough tests for Person 3 API endpoints and Person3API facade."""

    def setUp(self):
        self.uid = uuid.uuid4().hex[:6].upper()
        self.serial = f"APITEST-SN-{self.uid}"
        self.inst_payload = {
            "serial_number": self.serial,
            "model_number": "EAGLE-3000",
            "model_name": "Eagle Trade Platform",
            "manufacturer": "Eagle Metrology India Pvt Ltd",
            "instrument_type": "BENCH_SCALE",
            "accuracy_class": "III",
            "Max": 30.0,
            "max_capacity": 30.0,
            "Min": 0.2,
            "min_capacity": 0.2,
            "e": 0.01,
            "d": 0.01,
            "unit": "kg",
            "usage_type": "COMMERCIAL",
            "customer": {
                "name": "Reliance Fresh Supermarket",
                "city": "Pune",
                "state": "Maharashtra",
            },
            "customer_location": {
                "address": "Baner Road",
                "city": "Pune",
                "state": "Maharashtra",
                "postal_code": "411045",
            },
        }

    # =========================================================================
    # 1. INSTRUMENTS API
    # =========================================================================

    def test_01_instruments_post_and_get(self):
        """POST /instruments creates record; GET /instruments & GET /instruments/{id} retrieve it."""
        # 1. POST /instruments via router
        res = register_instrument(payload=self.inst_payload)
        self.assertTrue(res["success"])
        inst_id = res["data"]["instrument_id"]
        self.assertTrue(inst_id.startswith("INST-"))

        # 2. GET /instruments
        list_res = list_instruments(search=self.serial)
        self.assertTrue(list_res["success"])
        self.assertGreaterEqual(list_res["count"], 1)

        # 3. GET /instruments/{id}
        detail_res = get_instrument_details(instrument_id=inst_id)
        self.assertTrue(detail_res["success"])
        self.assertEqual(detail_res["data"]["serial_number"], self.serial)

        # 4. GET invalid ID returns 404
        with self.assertRaises(InstrumentsHTTPException) as ctx:
            get_instrument_details(instrument_id="NON_EXISTENT_ID_9999")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_02_instruments_put_and_patch(self):
        """PUT/PATCH /instruments/{instrument_id} updates record with metrological re-validation."""
        create_res = register_instrument(payload=self.inst_payload)
        inst_id = create_res["data"]["instrument_id"]

        # Partial update (PATCH-style): update customer notes
        patch_res = update_instrument(
            instrument_id=inst_id,
            payload={"notes": "Updated via PATCH endpoint"},
        )
        self.assertTrue(patch_res["success"])
        self.assertEqual(patch_res["data"]["notes"], "Updated via PATCH endpoint")

        # Invalid metrology update should be rejected with 422
        with self.assertRaises(InstrumentsHTTPException) as ctx:
            update_instrument(
                instrument_id=inst_id,
                payload={"Max": 100.0, "Min": 150.0},  # Min > Max
            )
        self.assertIn(ctx.exception.status_code, (400, 422))

    # =========================================================================
    # 2. MODEL APPROVAL API
    # =========================================================================

    def test_03_model_approval_endpoints(self):
        """POST, GET, GET /{id}, PUT/PATCH /model-approvals/{id}."""
        app_ref = f"APP-TEST-{self.uid}"
        ma_payload = {
            "application_reference": app_ref,
            "model_number": f"MOD-{self.uid}",
            "model_name": "Precision Platform Scale",
            "manufacturer": "Bharat Weigher Ltd",
            "accuracy_class": "III",
            "Max": 60.0,
            "max_capacity": 60.0,
            "Min": 0.2,
            "min_capacity": 0.2,
            "e": 0.02,
            "d": 0.02,
            "unit": "kg",
            "status": "DRAFT",
        }

        # 1. POST /model-approvals
        create_res = register_model_approval(payload=ma_payload)
        self.assertTrue(create_res["success"])

        # 2. GET /model-approvals
        list_res = list_model_approvals(search=app_ref)
        self.assertTrue(list_res["success"])
        self.assertGreaterEqual(list_res["count"], 1)

        # 3. GET /model-approvals/{approval_id}
        get_res = get_model_approval(reference=app_ref)
        self.assertTrue(get_res["success"])
        self.assertEqual(get_res["data"]["application_reference"], app_ref)

        # 4. PUT/PATCH /model-approvals/{id}
        update_res = update_model_approval(
            reference=app_ref,
            payload={"notes": "Updated model notes for SIH"},
        )
        self.assertTrue(update_res["success"])

        # 5. Non-existent returns 404
        with self.assertRaises(InstrumentsHTTPException) as ctx:
            get_model_approval(reference="NON_EXISTENT_MA_REF")
        self.assertEqual(ctx.exception.status_code, 404)

    # =========================================================================
    # 3. TEST JOBS API
    # =========================================================================

    def test_04_test_jobs_lifecycle_and_updates(self):
        """POST /test-jobs, GET /test-jobs, GET /{id}, PUT/PATCH /{id}."""
        inst_res = register_instrument(payload=self.inst_payload)
        inst_id = inst_res["data"]["instrument_id"]

        # 1. POST /test-jobs
        job_payload = {
            "instrument_id": inst_id,
            "job_type": "RE_VERIFICATION",
            "priority": "HIGH",
            "notes": "Annual statutory inspection",
        }
        job_res = create_test_job(payload=job_payload)
        self.assertTrue(job_res["success"])
        job_id = job_res["job_id"]
        self.assertTrue(job_id.startswith("JOB-"))

        # 2. GET /test-jobs
        list_res = list_jobs(instrument_id=inst_id)
        self.assertTrue(list_res["success"])
        self.assertGreaterEqual(list_res["count"], 1)

        # 3. GET /test-jobs/{id}
        detail_res = get_job_details(job_id=job_id)
        self.assertTrue(detail_res["success"])
        self.assertEqual(detail_res["data"]["job_id"], job_id)

        # 4. PUT/PATCH /test-jobs/{id}
        update_res = update_test_job(
            job_id=job_id,
            payload={"notes": "Updated scheduled time", "priority": "URGENT"},
        )
        self.assertTrue(update_res["success"])
        self.assertEqual(update_res["data"]["priority"], "URGENT")
        self.assertEqual(update_res["data"]["notes"], "Updated scheduled time")

    def test_05_test_job_validate_and_generate_plan(self):
        """POST /test-jobs/{id}/validate and POST /test-jobs/{id}/generate-plan."""
        inst_res = register_instrument(payload=self.inst_payload)
        inst_id = inst_res["data"]["instrument_id"]

        job_res = create_test_job(payload={"instrument_id": inst_id, "job_type": "RE_VERIFICATION"})
        job_id = job_res["job_id"]

        # 1. Validate Job: POST /test-jobs/{job_id}/validate
        val_res = validate_test_job_api(job_id=job_id, payload={"user_id": "INSPECTOR_007"})
        self.assertTrue(val_res["success"])
        self.assertTrue(val_res["data"]["valid"])
        self.assertIn(val_res["data"]["status"], ("VALIDATED", "TEST_PLAN_GENERATED"))

        # 2. Generate Plan: POST /test-jobs/{job_id}/generate-plan
        plan_res = generate_job_test_plan_api(job_id=job_id, payload={"force_regenerate": True})
        self.assertTrue(plan_res["success"])
        self.assertIsNotNone(plan_res["data"])
        self.assertIn("tests", plan_res["data"])
        self.assertIn("applicable_tests", plan_res["data"])

        # 3. Retrieve Plan for Person 4: GET /test-jobs/{job_id}/test-plan
        p4_plan = get_job_test_plan(job_id=job_id)
        self.assertTrue(p4_plan["success"])
        self.assertEqual(p4_plan["job_id"], job_id)
        self.assertIn("tests", p4_plan["data"])

    # =========================================================================
    # 4. LIFECYCLE API
    # =========================================================================

    def test_06_lifecycle_history_and_events(self):
        """GET /instruments/{id}/lifecycle and POST /instruments/{id}/lifecycle-events."""
        inst_res = register_instrument(payload=self.inst_payload)
        inst_id = inst_res["data"]["instrument_id"]

        # 1. GET /instruments/{id}/lifecycle
        hist_res = get_instrument_lifecycle_history(instrument_id=inst_id)
        self.assertTrue(hist_res["success"])
        self.assertGreaterEqual(len(hist_res["data"]), 1)  # Initial REGISTRATION event exists

        # 2. POST /instruments/{id}/lifecycle-events: valid event
        event_res = record_instrument_lifecycle_event(
            instrument_id=inst_id,
            payload={
                "event_type": "DISMANTLING",
                "new_status": "DISMANTLED",
                "actor": "LEGAL_OFFICER_MH",
                "notes": "Dismantled for premise shifting",
            },
        )
        self.assertTrue(event_res["success"])
        self.assertEqual(event_res["data"]["status"], "DISMANTLED")

        # 3. POST invalid transition throws 400
        with self.assertRaises(InstrumentsHTTPException) as ctx:
            record_instrument_lifecycle_event(
                instrument_id=inst_id,
                payload={
                    "event_type": "IN_SERVICE_USE",
                    "new_status": "IN_SERVICE",  # Illegal from DISMANTLED without reinstallation/verification
                },
            )
        self.assertEqual(ctx.exception.status_code, 400)

    # =========================================================================
    # 5. VERIFICATION SCHEDULING & COMPLETION API
    # =========================================================================

    def test_07_verification_scheduling_and_completion(self):
        """GET /instruments/due-for-verification, POST .../verification-job, POST .../complete-verification."""
        inst_res = register_instrument(payload=self.inst_payload)
        inst_id = inst_res["data"]["instrument_id"]

        # 1. GET /instruments/due-for-verification
        due_res = identify_instruments_requiring_verification()
        self.assertTrue("summary" in due_res or "counts" in due_res)
        self.assertIn("instruments", due_res)

        # 2. POST /instruments/{id}/verification-job
        vjob_res = create_instrument_verification_job(
            instrument_id=inst_id,
            payload={
                "job_type": "RE_VERIFICATION",
                "reason": "PERIODIC_EXPIRY",
                "priority": "HIGH",
            },
        )
        self.assertTrue(vjob_res["success"])
        job_id = vjob_res["job_id"]

        # 3. POST /jobs/{id}/complete-verification
        comp_res = complete_verification_job_api(
            job_id=job_id,
            payload={
                "outcome": "PASSED",
                "certificate_number": f"CERT-SIH-{self.uid}",
                "inspecting_officer": "Insp. Deshmukh",
                "stamping_authority": "Legal Metrology Dept, Maharashtra",
            },
        )
        self.assertTrue(comp_res["success"])
        self.assertEqual(comp_res["data"]["verification_status"], "VERIFIED")
        self.assertEqual(comp_res["data"]["status"], "IN_SERVICE")
        self.assertIsNotNone(comp_res["data"]["next_verification_date"])

    # =========================================================================
    # 6. Person3API Facade & Dispatch Method
    # =========================================================================

    def test_08_person3_api_dispatch_facade(self):
        """Person3API.dispatch routes HTTP-like requests for Person 1 integration."""
        # 1. POST /instruments via dispatch
        p_serial = f"DISPATCH-SN-{self.uid}"
        self.inst_payload["serial_number"] = p_serial
        resp = Person3API.dispatch("POST", "/instruments", body=self.inst_payload)
        self.assertTrue(resp["success"])
        self.assertEqual(resp["status_code"], 201)
        p_inst_id = resp["data"]["instrument_id"]

        # 2. GET /instruments/{id} via dispatch
        resp_get = Person3API.dispatch("GET", f"/instruments/{p_inst_id}")
        self.assertTrue(resp_get["success"])
        self.assertEqual(resp_get["status_code"], 200)

        # 3. PATCH /instruments/{id} via dispatch
        resp_patch = Person3API.dispatch("PATCH", f"/instruments/{p_inst_id}", body={"notes": "Updated via dispatch"})
        self.assertTrue(resp_patch["success"])
        self.assertEqual(resp_patch["data"]["notes"], "Updated via dispatch")

        # 4. POST /test-jobs via dispatch
        resp_job = Person3API.dispatch("POST", "/test-jobs", body={"instrument_id": p_inst_id, "job_type": "RE_VERIFICATION"})
        self.assertTrue(resp_job["success"])
        self.assertEqual(resp_job["status_code"], 201)
        disp_job_id = resp_job["meta"]["job_id"]

        # 5. POST /test-jobs/{id}/validate via dispatch
        resp_val = Person3API.dispatch("POST", f"/test-jobs/{disp_job_id}/validate")
        self.assertTrue(resp_val["success"])
        self.assertEqual(resp_val["status_code"], 200)

        # 6. GET /test-jobs/{id}/test-plan via dispatch
        resp_tp = Person3API.dispatch("GET", f"/test-jobs/{disp_job_id}/test-plan")
        self.assertTrue(resp_tp["success"])
        self.assertEqual(resp_tp["status_code"], 200)

        # 7. GET /instruments/due-for-verification via dispatch
        resp_due = Person3API.dispatch("GET", "/instruments/due-for-verification")
        self.assertTrue(resp_due["success"])
        self.assertEqual(resp_due["status_code"], 200)

        # 8. Unhandled route returns 404
        resp_404 = Person3API.dispatch("GET", "/unknown/route")
        self.assertFalse(resp_404["success"])
        self.assertEqual(resp_404["status_code"], 404)
        self.assertEqual(resp_404["error"]["code"], "ROUTE_NOT_FOUND")

    # =========================================================================
    # 7. Error Handling & Validation Envelopes
    # =========================================================================

    def test_09_error_envelopes_and_validation(self):
        """Ensures consistent error envelopes with proper status codes and no leaking internals."""
        # 1. Missing required fields on POST /instruments -> 422
        resp = Person3API.dispatch("POST", "/instruments", body={})
        self.assertFalse(resp["success"])
        self.assertEqual(resp["status_code"], 422)
        self.assertEqual(resp["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("details", resp["error"])

        # 2. Non-existent instrument on GET /instruments/{id} -> 404
        resp_404 = Person3API.dispatch("GET", "/instruments/DOES_NOT_EXIST_XYZ")
        self.assertFalse(resp_404["success"])
        self.assertEqual(resp_404["status_code"], 404)
        self.assertEqual(resp_404["error"]["code"], "INSTRUMENT_NOT_FOUND")

        # 3. Method not allowed -> 405
        resp_405 = Person3API.dispatch("DELETE", "/instruments")
        self.assertFalse(resp_405["success"])
        self.assertEqual(resp_405["status_code"], 405)


if __name__ == "__main__":
    unittest.main()
