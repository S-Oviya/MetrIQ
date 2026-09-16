"""
MetrIQ Unit Tests - Regulatory API Endpoints & Service Layer
============================================================
Validates the clean API layer exposed for Person 1 (Team Lead) integration:
1. POST /regulatory/validate-instrument
2. POST /regulatory/mpe
3. POST /regulatory/applicable-tests
4. POST /regulatory/test-plan
5. GET  /regulatory/profile
6. GET  /regulatory/rules/{rule_id}
7. RegulatoryAPI facade and dispatch routing
8. Error handling: 400 Bad Request, 404 Not Found, 405 Method Not Allowed, 422 Unprocessable Entity
"""

import os
import sys
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Verify Person 1 can import directly from app.regulatory without internal submodules
try:
    from app.regulatory import (
        validate_instrument_api,
        calculate_mpe_api,
        determine_applicable_tests_api,
        generate_test_plan_api,
        get_regulatory_profile_api,
        get_rule_or_source_api,
        RegulatoryAPI,
        success_response,
        error_response,
    )
except ImportError:
    from backend.app.regulatory import (
        validate_instrument_api,
        calculate_mpe_api,
        determine_applicable_tests_api,
        generate_test_plan_api,
        get_regulatory_profile_api,
        get_rule_or_source_api,
        RegulatoryAPI,
        success_response,
        error_response,
    )


class TestRegulatoryAPI(unittest.TestCase):
    """Test suite for the Regulatory Engine API Layer."""

    def setUp(self):
        self.compliant_instrument = {
            "job_id": "JOB-2026-API-001",
            "instrument_id": "INST-NAWI-API",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "calculated_n": 3000,
            "unit": "kg",
            "verification_type": "INITIAL",
            "electronic_status": True,
            "digital_analog": "DIGITAL",
            "zero_setting_device": True,
            "tare_device": True,
            "is_type_evaluation": False,
        }

    # =========================================================================
    # 1. POST /regulatory/validate-instrument
    # =========================================================================

    def test_validate_instrument_success_compliant(self):
        """Valid compliant instrument returns HTTP 200 with valid=True."""
        resp = validate_instrument_api(self.compliant_instrument)
        self.assertTrue(resp["success"])
        self.assertEqual(resp["status_code"], 200)
        data = resp["data"]
        self.assertTrue(data["valid"])
        self.assertEqual(data["accuracy_class"], "III")
        self.assertEqual(data["max_capacity"], 15.0)
        self.assertEqual(data["n"], 3000)
        self.assertEqual(len(data["errors"]), 0)

    def test_validate_instrument_metrological_failure(self):
        """Instrument exceeding statutory limits returns HTTP 200 with valid=False and detailed errors."""
        payload = dict(self.compliant_instrument)
        payload["Max"] = 100.0
        payload["e"] = 0.001  # n = 100,000 exceeds Class III limit of 10,000

        resp = validate_instrument_api(payload)
        self.assertTrue(resp["success"])
        self.assertEqual(resp["status_code"], 200)
        data = resp["data"]
        self.assertFalse(data["valid"])
        self.assertTrue(len(data["errors"]) > 0)
        error_rules = [e["rule_id"] for e in data["errors"]]
        self.assertIn("RULE_CLASS_III_N_MAX", error_rules)

    def test_validate_instrument_missing_required_fields(self):
        """Missing required fields returns HTTP 400 with structured error."""
        # Missing accuracy_class
        resp = validate_instrument_api({"Max": 15.0, "e": 0.005})
        self.assertFalse(resp["success"])
        self.assertEqual(resp["status_code"], 400)
        self.assertEqual(resp["error"]["code"], "MISSING_REQUIRED_FIELD")

        # Missing Max
        resp = validate_instrument_api({"accuracy_class": "III", "e": 0.005})
        self.assertFalse(resp["success"])
        self.assertEqual(resp["status_code"], 400)
        self.assertEqual(resp["error"]["code"], "MISSING_REQUIRED_FIELD")

        # Missing e
        resp = validate_instrument_api({"accuracy_class": "III", "Max": 15.0})
        self.assertFalse(resp["success"])
        self.assertEqual(resp["status_code"], 400)
        self.assertEqual(resp["error"]["code"], "MISSING_REQUIRED_FIELD")

    def test_validate_instrument_empty_payload(self):
        """Empty or null payload returns HTTP 400."""
        resp = validate_instrument_api({})
        self.assertFalse(resp["success"])
        self.assertEqual(resp["status_code"], 400)
        self.assertEqual(resp["error"]["code"], "INVALID_REQUEST_PAYLOAD")

    def test_validate_instrument_invalid_numeric_types(self):
        """Unparseable string values return HTTP 422."""
        payload = dict(self.compliant_instrument)
        payload["Max"] = "not_a_number"
        resp = validate_instrument_api(payload)
        self.assertFalse(resp["success"])
        self.assertEqual(resp["status_code"], 422)
        self.assertEqual(resp["error"]["code"], "INVALID_FIELD_FORMAT")

    # =========================================================================
    # 2. POST /regulatory/mpe
    # =========================================================================

    def test_calculate_mpe_success(self):
        """Calculates correct statutory MPE for load and e."""
        payload = {
            "accuracy_class": "III",
            "load": 2.5,
            "e": 0.005,
            "verification_type": "INITIAL",
            "unit": "kg",
        }
        resp = calculate_mpe_api(payload)
        self.assertTrue(resp["success"])
        self.assertEqual(resp["status_code"], 200)
        data = resp["data"]
        self.assertEqual(data["load"], 2.5)
        self.assertEqual(data["load_in_e"], 500.0)
        self.assertEqual(data["mpe_in_e"], 0.5)
        self.assertEqual(data["mpe_absolute"], 0.0025)
        self.assertIn("500", data["tolerance_band"])
        self.assertEqual(data["lower_limit_error"], -0.0025)
        self.assertEqual(data["upper_limit_error"], 0.0025)

    def test_calculate_mpe_with_observed_error(self):
        """Evaluates observed indication error against MPE bounds."""
        payload = {
            "accuracy_class": "III",
            "load": 2.5,
            "e": 0.005,
            "observed_error": 0.002,
        }
        resp = calculate_mpe_api(payload)
        self.assertTrue(resp["success"])
        data = resp["data"]
        self.assertTrue(data["is_pass"])
        self.assertEqual(data["observed_error"], 0.002)
        self.assertEqual(data["margin"], 0.0005)

    def test_calculate_mpe_subsequent_verification_doubling(self):
        """Subsequent verification doubles statutory MPE (2x Initial)."""
        payload = {
            "accuracy_class": "III",
            "load": 2.5,
            "e": 0.005,
            "verification_type": "SUBSEQUENT",
        }
        resp = calculate_mpe_api(payload)
        self.assertTrue(resp["success"])
        data = resp["data"]
        # Initial 0.5e -> Subsequent 1.0e = 0.005kg
        self.assertEqual(data["mpe_in_e"], 1.0)
        self.assertEqual(data["mpe_absolute"], 0.005)

    def test_calculate_mpe_missing_parameters(self):
        """Missing parameters return HTTP 400."""
        resp = calculate_mpe_api({"load": 2.5, "e": 0.005})
        self.assertFalse(resp["success"])
        self.assertEqual(resp["status_code"], 400)
        self.assertEqual(resp["error"]["code"], "MISSING_PARAMETER")

        resp = calculate_mpe_api({"accuracy_class": "III", "e": 0.005})
        self.assertFalse(resp["success"])
        self.assertEqual(resp["status_code"], 400)
        self.assertEqual(resp["error"]["code"], "MISSING_PARAMETER")

        resp = calculate_mpe_api({"accuracy_class": "III", "load": 2.5})
        self.assertFalse(resp["success"])
        self.assertEqual(resp["status_code"], 400)
        self.assertEqual(resp["error"]["code"], "MISSING_PARAMETER")

    def test_calculate_mpe_invalid_scale_interval(self):
        """Non-positive scale interval (e <= 0) returns HTTP 422."""
        payload = {"accuracy_class": "III", "load": 2.5, "e": -0.005}
        resp = calculate_mpe_api(payload)
        self.assertFalse(resp["success"])
        self.assertEqual(resp["status_code"], 422)
        self.assertEqual(resp["error"]["code"], "INVALID_SCALE_INTERVAL")

    # =========================================================================
    # 3. POST /regulatory/applicable-tests
    # =========================================================================

    def test_determine_applicable_tests_success(self):
        """Evaluates all 22 statutory tests and returns categorized lists and counts."""
        resp = determine_applicable_tests_api(self.compliant_instrument)
        self.assertTrue(resp["success"])
        self.assertEqual(resp["status_code"], 200)
        data = resp["data"]
        self.assertIn("applicable_tests", data)
        self.assertIn("not_applicable_tests", data)
        self.assertIn("manual_review_tests", data)
        self.assertGreater(data["applicable_count"], 0)
        self.assertGreater(data["not_applicable_count"], 0)
        self.assertEqual(data["total_tests_evaluated"], 22)

    def test_determine_applicable_tests_invalid_payload(self):
        """Non-dictionary payload returns HTTP 400."""
        resp = determine_applicable_tests_api(None)
        self.assertFalse(resp["success"])
        self.assertEqual(resp["status_code"], 400)
        self.assertEqual(resp["error"]["code"], "INVALID_REQUEST_PAYLOAD")

    # =========================================================================
    # 4. POST /regulatory/test-plan
    # =========================================================================

    def test_generate_test_plan_success(self):
        """Generates complete statutory test plan consumable by Person 4."""
        resp = generate_test_plan_api(self.compliant_instrument)
        self.assertTrue(resp["success"])
        self.assertEqual(resp["status_code"], 200)
        data = resp["data"]
        self.assertTrue(data["test_plan_id"].startswith("PLAN-"))
        self.assertEqual(data["accuracy_class"], "III")
        self.assertEqual(data["max_capacity"], 15.0)
        self.assertIn("A.4.4", data["applicable_tests"])
        self.assertIn("A.4.7", data["applicable_tests"])
        self.assertGreater(len(data["calculated_test_loads"]), 0)
        self.assertGreater(len(data["tests"]), 0)

    def test_generate_test_plan_missing_parameters(self):
        """Missing essential planning parameters returns HTTP 400."""
        resp = generate_test_plan_api({"Max": 15.0})
        self.assertFalse(resp["success"])
        self.assertEqual(resp["status_code"], 400)
        self.assertEqual(resp["error"]["code"], "MISSING_PLAN_PARAMETERS")

    # =========================================================================
    # 5. GET /regulatory/profile
    # =========================================================================

    def test_get_regulatory_profile_success(self):
        """Returns active regulatory profile and statutory sources."""
        resp = get_regulatory_profile_api()
        self.assertTrue(resp["success"])
        self.assertEqual(resp["status_code"], 200)
        data = resp["data"]
        self.assertEqual(data["engine_name"], "MetrIQ Regulatory Compliance Engine")
        self.assertEqual(data["version"], "1.0.0")
        self.assertEqual(data["supported_accuracy_classes"], ["I", "II", "III", "IIII"])

        # Check primary Indian statutory sources
        indian_codes = [s["code"] for s in data["primary_indian_sources"]]
        self.assertIn("LM_ACT_2009", indian_codes)
        self.assertIn("IN_LM_2011", indian_codes)
        self.assertIn("IN_AMR_2011", indian_codes)
        self.assertIn("IN_GATC_2013", indian_codes)

        # Check technical sources
        tech_codes = [s["code"] for s in data["technical_sources"]]
        self.assertIn("OIML_R76_2006", tech_codes)
        self.assertIn("OIML_R76_2_2007", tech_codes)

    # =========================================================================
    # 6. GET /regulatory/rules/{rule_id}
    # =========================================================================

    def test_get_rule_statutory_test_found(self):
        """Retrieves statutory test procedure by test ID (e.g. A.4.4)."""
        resp = get_rule_or_source_api("A.4.4")
        self.assertTrue(resp["success"])
        self.assertEqual(resp["status_code"], 200)
        data = resp["data"]
        self.assertEqual(data["rule_id"], "A.4.4")
        self.assertIn("Weighing Performance Test", data["rule_name"])
        self.assertIn("OIML R 76-1:2006", data["source"])

    def test_get_rule_standard_source_found(self):
        """Retrieves statutory standard source by standard ID (e.g. IN_LM_2011)."""
        resp = get_rule_or_source_api("IN_LM_2011")
        self.assertTrue(resp["success"])
        self.assertEqual(resp["status_code"], 200)
        data = resp["data"]
        self.assertEqual(data["id"], "IN_LM_2011")
        self.assertEqual(data["jurisdiction"], "INDIA")

    def test_get_rule_accuracy_class_found(self):
        """Retrieves accuracy class definition by class ID (e.g. CLASS_III)."""
        resp = get_rule_or_source_api("CLASS_III")
        self.assertTrue(resp["success"])
        self.assertEqual(resp["status_code"], 200)
        data = resp["data"]
        self.assertEqual(data["class_id"], "CLASS_III")
        self.assertEqual(data["roman_numeral"], "III")

    def test_get_rule_not_found(self):
        """Unrecognized rule ID returns HTTP 404 with suggested IDs."""
        resp = get_rule_or_source_api("NON_EXISTENT_RULE_XYZ")
        self.assertFalse(resp["success"])
        self.assertEqual(resp["status_code"], 404)
        self.assertEqual(resp["error"]["code"], "RULE_NOT_FOUND")
        self.assertIn("suggested_ids", resp["error"]["details"])

    def test_get_rule_empty_id(self):
        """Empty rule ID returns HTTP 400."""
        resp = get_rule_or_source_api("")
        self.assertFalse(resp["success"])
        self.assertEqual(resp["status_code"], 400)
        self.assertEqual(resp["error"]["code"], "MISSING_RULE_ID")

    # =========================================================================
    # 7. RegulatoryAPI Facade and Dispatch Routing
    # =========================================================================

    def test_facade_dispatch_post_validate_instrument(self):
        """Tests RegulatoryAPI.dispatch for POST /regulatory/validate-instrument."""
        resp = RegulatoryAPI.dispatch("POST", "/regulatory/validate-instrument", body=self.compliant_instrument)
        self.assertTrue(resp["success"])
        self.assertEqual(resp["status_code"], 200)
        self.assertTrue(resp["data"]["valid"])

    def test_facade_dispatch_post_mpe(self):
        """Tests RegulatoryAPI.dispatch for POST /regulatory/mpe."""
        body = {"accuracy_class": "III", "load": 5.0, "e": 0.005}
        resp = RegulatoryAPI.dispatch("POST", "/regulatory/mpe", body=body)
        self.assertTrue(resp["success"])
        self.assertEqual(resp["status_code"], 200)
        self.assertEqual(resp["data"]["mpe_in_e"], 1.0)

    def test_facade_dispatch_post_applicable_tests(self):
        """Tests RegulatoryAPI.dispatch for POST /regulatory/applicable-tests."""
        resp = RegulatoryAPI.dispatch("POST", "/regulatory/applicable-tests", body=self.compliant_instrument)
        self.assertTrue(resp["success"])
        self.assertEqual(resp["status_code"], 200)

    def test_facade_dispatch_post_test_plan(self):
        """Tests RegulatoryAPI.dispatch for POST /regulatory/test-plan."""
        resp = RegulatoryAPI.dispatch("POST", "/regulatory/test-plan", body=self.compliant_instrument)
        self.assertTrue(resp["success"])
        self.assertEqual(resp["status_code"], 200)

    def test_facade_dispatch_get_profile(self):
        """Tests RegulatoryAPI.dispatch for GET /regulatory/profile."""
        resp = RegulatoryAPI.dispatch("GET", "/regulatory/profile")
        self.assertTrue(resp["success"])
        self.assertEqual(resp["status_code"], 200)
        self.assertEqual(resp["data"]["version"], "1.0.0")

    def test_facade_dispatch_get_rule_by_path(self):
        """Tests RegulatoryAPI.dispatch for GET /regulatory/rules/A.4.7."""
        resp = RegulatoryAPI.dispatch("GET", "/regulatory/rules/A.4.7")
        self.assertTrue(resp["success"])
        self.assertEqual(resp["status_code"], 200)
        self.assertEqual(resp["data"]["rule_id"], "A.4.7")

    def test_facade_dispatch_method_not_allowed(self):
        """Sending wrong HTTP method returns HTTP 405."""
        resp = RegulatoryAPI.dispatch("GET", "/regulatory/validate-instrument")
        self.assertFalse(resp["success"])
        self.assertEqual(resp["status_code"], 405)
        self.assertEqual(resp["error"]["code"], "METHOD_NOT_ALLOWED")

    def test_facade_dispatch_route_not_found(self):
        """Sending unknown path returns HTTP 404."""
        resp = RegulatoryAPI.dispatch("GET", "/regulatory/unknown-endpoint")
        self.assertFalse(resp["success"])
        self.assertEqual(resp["status_code"], 404)
        self.assertEqual(resp["error"]["code"], "ROUTE_NOT_FOUND")

    # =========================================================================
    # 8. Master API Router Integration (app/api/router.py)
    # =========================================================================

    def test_master_router_exports_regulatory_api(self):
        """Verifies master router exposes regulatory API for Person 1."""
        try:
            from app.api.router import (
                validate_instrument_api as master_val,
                calculate_mpe_api as master_mpe,
                RegulatoryAPI as MasterAPI,
            )
        except ImportError:
            from backend.app.api.router import (
                validate_instrument_api as master_val,
                calculate_mpe_api as master_mpe,
                RegulatoryAPI as MasterAPI,
            )

        resp_val = master_val(self.compliant_instrument)
        self.assertTrue(resp_val["success"])

        resp_mpe = master_mpe({"accuracy_class": "II", "load": 5000, "e": 1})
        self.assertTrue(resp_mpe["success"])
        self.assertEqual(resp_mpe["data"]["mpe_in_e"], 0.5)

        resp_disp = MasterAPI.dispatch("GET", "/regulatory/profile")
        self.assertTrue(resp_disp["success"])


if __name__ == "__main__":
    unittest.main()
