"""
Unit Tests for MetrIQ Regulatory Test Applicability Engine
==========================================================

Validates:
1. Standard Electronic Digital NAWI applicability.
2. Stability of equilibrium conditional on printing/data-storage.
3. Rolling-load eccentricity conditional on rolling-load capability / weighbridge.
4. Sensitivity test strictly for non-self-indicating instruments.
5. Digital vs Analog discrimination tests.
6. Warm-up, voltage variation, and EMC disturbance tests strictly for electronic instruments.
7. Type Evaluation / Model Approval tests (A.2, A.4.11.1 Creep, A.5.3 Temperature, A.5.4 Voltage, B.1 Disturbance, B.2 Damp Heat, B.3 Span Stability, A.6 Endurance).
8. Endurance test capacity cutoff (Max <= 100 kg).
9. Tilting test conditional logic and Class I exemption.
10. Absence of zero-setting and tare facilities.
11. Multi-interval and multi-range architectural warnings.
12. Structural output format (applicable_tests, not_applicable_tests, manual_review_tests, warnings).
13. Regulatory source citation in every test item.
14. REST API router integration.
"""

import os
import sys
import unittest

# Add backend directory to sys.path so app.regulatory can be imported
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.regulatory.models import AccuracyClass
from app.regulatory.test_applicability_engine import (
    IndicationType,
    InstrumentCharacteristics,
    InstrumentIndicationMode,
    RegulatoryTestApplicabilityEngine,
    evaluate_test_applicability,
)
from app.regulatory.router import api_evaluate_applicability


class TestRegulatoryTestApplicabilityEngine(unittest.TestCase):

    def test_standard_electronic_digital_nawi_field_verification(self):
        """Standard commercial bench scale undergoing routine initial verification."""
        spec = {
            "accuracy_class": "III",
            "instrument_type": "SELF_INDICATING",
            "indication_type": "DIGITAL",
            "electronic_status": True,
            "has_zero_setting": True,
            "has_tare": True,
            "load_receptor": "STANDARD_PLATTER",
            "rolling_load_capability": False,
            "printing_data_storage": False,
            "tilting_susceptibility": False,
            "is_mobile": False,
            "has_level_indicator": True,
            "type_evaluation_status": False,
            "max_capacity": 15.0,
            "verification_scale_interval": 0.005,
        }

        report = evaluate_test_applicability(spec)

        app_ids = {t["test_id"] for t in report["applicable_tests"]}
        not_app_ids = {t["test_id"] for t in report["not_applicable_tests"]}
        manual_ids = {t["test_id"] for t in report["manual_review_tests"]}

        # Mandatory core tests must apply
        self.assertIn("A.1", app_ids)    # Administrative examination
        self.assertIn("A.3", app_ids)    # Initial examination
        self.assertIn("A.4.2", app_ids)  # Zero-setting accuracy
        self.assertIn("A.4.3", app_ids)  # Tare accuracy
        self.assertIn("A.4.4", app_ids)  # Weighing performance
        self.assertIn("A.4.7", app_ids)  # Eccentricity
        self.assertIn("A.4.8", app_ids)  # Digital discrimination
        self.assertIn("A.4.10", app_ids) # Repeatability
        self.assertIn("A.5.2", app_ids)  # Warm-up (electronic)

        # Non-applicable tests for standard routine verification
        self.assertIn("A.2", not_app_ids)      # Construction docs (type evaluation only)
        self.assertIn("A.4.7.1", not_app_ids)  # Rolling load (standard platter)
        self.assertIn("A.4.9", not_app_ids)    # Sensitivity (self-indicating scale)
        self.assertIn("A.4.11.1", not_app_ids) # Creep (type evaluation only)
        self.assertIn("A.4.12", not_app_ids)   # Stability of equilibrium (no printer/storage)
        self.assertIn("A.5.1", not_app_ids)    # Tilting (stationary with level indicator)
        self.assertIn("A.5.3", not_app_ids)    # Temperature chamber (type evaluation only)
        self.assertIn("A.5.4", not_app_ids)    # Voltage variation (type evaluation only)
        self.assertIn("B.1", not_app_ids)      # Electronic disturbances (type evaluation only)
        self.assertIn("B.2", not_app_ids)      # Damp heat (type evaluation only)
        self.assertIn("B.3", not_app_ids)      # Span stability (type evaluation only)
        self.assertIn("A.6", not_app_ids)      # Endurance (type evaluation only)

        # Manual review tests must include A.1 and A.3
        self.assertIn("A.1", manual_ids)
        self.assertIn("A.3", manual_ids)
        self.assertNotIn("A.4.4", manual_ids)

        # Every test must contain regulatory source
        for t in report["applicable_tests"] + report["not_applicable_tests"]:
            self.assertTrue(bool(t.get("source")))
            self.assertTrue(bool(t.get("reason")))

    def test_stability_of_equilibrium_conditional_on_printing_storage(self):
        """A.4.12 applies conditionally when printing or automated data storage is present."""
        # Without printer/storage
        spec_no_print = {"printing_data_storage": False}
        rep_no_print = evaluate_test_applicability(spec_no_print)
        not_app = {t["test_id"] for t in rep_no_print["not_applicable_tests"]}
        self.assertIn("A.4.12", not_app)

        # With printer/storage
        spec_print = {"printing_data_storage": True}
        rep_print = evaluate_test_applicability(spec_print)
        app = {t["test_id"] for t in rep_print["applicable_tests"]}
        manual = {t["test_id"] for t in rep_print["manual_review_tests"]}
        self.assertIn("A.4.12", app)
        self.assertIn("A.4.12", manual)  # Requires manual examination of lockout during motion

        # Check warning
        self.assertTrue(any("lockout during motion" in w for w in rep_print["warnings"]))

    def test_rolling_load_eccentricity_conditional(self):
        """A.4.7.1 Rolling load eccentricity applies only for rolling load capability."""
        # Standard platter -> not applicable
        rep_static = evaluate_test_applicability({"rolling_load_capability": False, "load_receptor": "PLATTER"})
        not_app = {t["test_id"] for t in rep_static["not_applicable_tests"]}
        self.assertIn("A.4.7.1", not_app)

        # Vehicle weighbridge -> applicable
        rep_rolling = evaluate_test_applicability({"rolling_load_capability": True, "load_receptor": "VEHICLE_WEIGHBRIDGE"})
        app = {t["test_id"] for t in rep_rolling["applicable_tests"]}
        self.assertIn("A.4.7.1", app)
        self.assertIn("A.4.7", app)  # Standard eccentricity also applies

    def test_sensitivity_applies_strictly_to_non_self_indicating(self):
        """A.4.9 Sensitivity applies to non-self-indicating instruments, not self-indicating."""
        # Non-self-indicating beam scale
        rep_non_self = evaluate_test_applicability({
            "instrument_type": "NON_SELF_INDICATING",
            "electronic_status": False,
            "digital_analog": "NON_INDICATING",
        })
        app_non_self = {t["test_id"] for t in rep_non_self["applicable_tests"]}
        not_app_non_self = {t["test_id"] for t in rep_non_self["not_applicable_tests"]}
        self.assertIn("A.4.9", app_non_self)      # Sensitivity applies!
        self.assertIn("A.4.8", not_app_non_self)  # Discrimination does NOT apply

        # Self-indicating electronic scale
        rep_self = evaluate_test_applicability({
            "instrument_type": "SELF_INDICATING",
            "electronic_status": True,
            "digital_analog": "DIGITAL",
        })
        app_self = {t["test_id"] for t in rep_self["applicable_tests"]}
        not_app_self = {t["test_id"] for t in rep_self["not_applicable_tests"]}
        self.assertIn("A.4.8", app_self)          # Digital discrimination applies
        self.assertIn("A.4.9", not_app_self)      # Sensitivity does NOT apply

    def test_digital_vs_analog_discrimination(self):
        """Discrimination test distinguishes digital (1.4d) vs analog (0.7d)."""
        # Digital
        rep_dig = evaluate_test_applicability({"digital_analog": "DIGITAL"})
        test_dig = next(t for t in rep_dig["applicable_tests"] if t["test_id"] == "A.4.8")
        self.assertIn("Digital", test_dig["reason"])
        self.assertIn("1.4d", test_dig["reason"])

        # Analog
        rep_ana = evaluate_test_applicability({"digital_analog": "ANALOG"})
        test_ana = next(t for t in rep_ana["applicable_tests"] if t["test_id"] == "A.4.8")
        self.assertIn("Analog", test_ana["reason"])
        self.assertIn("0.7d", test_ana["reason"])

    def test_electronic_instrument_tests(self):
        """Warm-up, voltage variation, and disturbances apply strictly to electronic instruments."""
        # Mechanical scale
        rep_mech = evaluate_test_applicability({
            "electronic_status": False,
            "type_evaluation_status": True,
        })
        not_app_mech = {t["test_id"] for t in rep_mech["not_applicable_tests"]}
        self.assertIn("A.5.2", not_app_mech)  # Warm-up not applicable
        self.assertIn("A.5.4", not_app_mech)  # Voltage variation not applicable
        self.assertIn("B.1", not_app_mech)    # Electronic disturbances not applicable
        self.assertIn("B.2", not_app_mech)    # Damp heat not applicable
        self.assertIn("B.3", not_app_mech)    # Span stability not applicable

        # Electronic scale during Type Evaluation
        rep_elec = evaluate_test_applicability({
            "electronic_status": True,
            "type_evaluation_status": True,
            "max_capacity": 30.0,
        })
        app_elec = {t["test_id"] for t in rep_elec["applicable_tests"]}
        self.assertIn("A.5.2", app_elec)  # Warm-up applies
        self.assertIn("A.5.4", app_elec)  # Voltage variation applies
        self.assertIn("B.1", app_elec)    # Disturbance tests apply
        self.assertIn("B.2", app_elec)    # Damp heat applies
        self.assertIn("B.3", app_elec)    # Span stability applies

    def test_type_evaluation_laboratory_suite(self):
        """Type Evaluation (Model Approval) triggers full environmental & endurance suite."""
        rep_type = evaluate_test_applicability({
            "electronic_status": True,
            "type_evaluation_status": True,
            "max_capacity": 60.0,  # <= 100 kg
            "accuracy_class": "III",
        })
        app_type = {t["test_id"] for t in rep_type["applicable_tests"]}

        self.assertIn("A.2", app_type)      # Comparison with docs
        self.assertIn("A.4.11.1", app_type) # Creep
        self.assertIn("A.5.1", app_type)    # Tilting
        self.assertIn("A.5.3", app_type)    # Temperature chamber
        self.assertIn("A.5.4", app_type)    # Voltage variation
        self.assertIn("B.1", app_type)      # Electronic disturbance tests
        self.assertIn("B.2", app_type)      # Damp heat
        self.assertIn("B.3", app_type)      # Span stability
        self.assertIn("A.6", app_type)      # Endurance (100,000 cycles)

    def test_endurance_test_capacity_cutoff(self):
        """Endurance test A.6 applies for Max <= 100 kg during Type Evaluation."""
        # Max = 60 kg -> Applicable
        rep_60kg = evaluate_test_applicability({
            "type_evaluation_status": True,
            "max_capacity": 60.0,
        })
        app_60kg = {t["test_id"] for t in rep_60kg["applicable_tests"]}
        self.assertIn("A.6", app_60kg)

        # Max = 500 kg -> Not Applicable
        rep_500kg = evaluate_test_applicability({
            "type_evaluation_status": True,
            "max_capacity": 500.0,
        })
        not_app_500kg = {t["test_id"] for t in rep_500kg["not_applicable_tests"]}
        self.assertIn("A.6", not_app_500kg)
        reason = next(t["reason"] for t in rep_500kg["not_applicable_tests"] if t["test_id"] == "A.6")
        self.assertIn("Max <= 100 kg", reason)

    def test_tilting_test_conditional_and_class_i_exemption(self):
        """Class I instruments are strictly exempt from tilting test."""
        # Class I mobile instrument
        rep_class_i = evaluate_test_applicability({
            "accuracy_class": "I",
            "is_mobile": True,
            "tilting_susceptibility": True,
        })
        not_app = {t["test_id"] for t in rep_class_i["not_applicable_tests"]}
        self.assertIn("A.5.1", not_app)
        reason = next(t["reason"] for t in rep_class_i["not_applicable_tests"] if t["test_id"] == "A.5.1")
        self.assertIn("Class I", reason)

        # Class III mobile instrument
        rep_class_iii_mobile = evaluate_test_applicability({
            "accuracy_class": "III",
            "is_mobile": True,
            "tilting_susceptibility": True,
        })
        app_iii = {t["test_id"] for t in rep_class_iii_mobile["applicable_tests"]}
        self.assertIn("A.5.1", app_iii)

    def test_zero_and_tare_device_absence(self):
        """Zero-setting and tare tests depend strictly on presence of those devices."""
        rep = evaluate_test_applicability({
            "has_zero_setting": False,
            "has_tare": False,
        })
        not_app = {t["test_id"] for t in rep["not_applicable_tests"]}
        self.assertIn("A.4.2", not_app)
        self.assertIn("A.4.3", not_app)

    def test_architectural_warnings(self):
        """Multi-interval and multi-range features trigger statutory warnings."""
        rep = evaluate_test_applicability({
            "is_multi_interval": True,
            "is_multi_range": True,
            "printing_data_storage": True,
        })
        warnings = rep["warnings"]
        self.assertTrue(any("Multi-interval" in w for w in warnings))
        self.assertTrue(any("Multi-range" in w for w in warnings))
        self.assertTrue(any("Printing/Data-storage" in w for w in warnings))

    def test_router_api_evaluate_applicability(self):
        """Verifies router API returns exact required dictionary format."""
        payload = {
            "accuracy_class": "II",
            "instrument_type": "SELF_INDICATING",
            "electronic_status": True,
            "type_evaluation_status": True,
            "max_capacity": 6.0,
            "has_tare": True,
            "has_zero_setting": True,
            "printing_data_storage": True,
        }
        res = api_evaluate_applicability(payload)

        self.assertIn("applicable_tests", res)
        self.assertIn("not_applicable_tests", res)
        self.assertIn("manual_review_tests", res)
        self.assertIn("warnings", res)

        # Verify items inside applicable_tests
        for item in res["applicable_tests"]:
            self.assertIn("test_id", item)
            self.assertIn("test_name", item)
            self.assertIn("source", item)
            self.assertIn("applicable_when", item)
            self.assertIn("not_applicable_when", item)
            self.assertIn("required_inputs", item)
            self.assertIn("manual_review", item)
            self.assertIn("priority", item)
            self.assertTrue(item["applicable"])


if __name__ == "__main__":
    unittest.main()
