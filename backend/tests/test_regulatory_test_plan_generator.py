"""
MetrIQ Unit Tests - Regulatory Test Plan Generator
==================================================
Tests for RegulatoryTestPlanGenerator and generate_regulatory_test_plan.
Verifies the complete 5-stage pipeline:
1. Instrument Specification
2. Classification Validation
3. Regulatory Applicability
4. Test Load Calculation (Weighing, Eccentricity, Repeatability, Discrimination, Creep, Temperature)
5. Generated Test Plan Output (Consumable by Person 4 Test Engine)
"""

import os
import sys
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

try:
    from app.regulatory.test_plan_generator import (
        RegulatoryTestPlanGenerator,
        GeneratedTestPlan,
        TestLoadPoint,
        ExecutableTestItem,
        generate_regulatory_test_plan,
    )
    from app.regulatory.router import (
        api_generate_test_plan,
        api_generate_regulatory_test_plan,
    )
except ImportError:
    from backend.app.regulatory.test_plan_generator import (
        RegulatoryTestPlanGenerator,
        GeneratedTestPlan,
        TestLoadPoint,
        ExecutableTestItem,
        generate_regulatory_test_plan,
    )
    from backend.app.regulatory.router import (
        api_generate_test_plan,
        api_generate_regulatory_test_plan,
    )


class TestRegulatoryTestPlanGenerator(unittest.TestCase):
    """Test suite for the Regulatory Test Plan Generator."""

    def setUp(self):
        self.standard_class_iii_spec = {
            "job_id": "JOB-2026-001",
            "instrument_id": "INST-NAWI-882",
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "verification_type": "INITIAL",
            "electronic_status": True,
            "digital_analog": "DIGITAL",
            "zero_setting_device": True,
            "tare_device": True,
            "is_type_evaluation": False,
        }

    # -------------------------------------------------------------------------
    # 1. Pipeline & Top-Level Structure Tests
    # -------------------------------------------------------------------------

    def test_pipeline_execution_and_fields(self):
        """Verify standard plan generates all top-level statutory fields."""
        plan = RegulatoryTestPlanGenerator.generate(self.standard_class_iii_spec)

        self.assertIsInstance(plan, GeneratedTestPlan)
        self.assertTrue(plan.test_plan_id.startswith("PLAN-"))
        self.assertEqual(plan.job_id, "JOB-2026-001")
        self.assertEqual(plan.instrument_id, "INST-NAWI-882")
        self.assertIn("OIML R 76-1:2006", plan.regulatory_profile)
        self.assertEqual(plan.accuracy_class, "III")
        self.assertEqual(plan.max_capacity, 15.0)
        self.assertEqual(plan.min_capacity, 0.1)
        self.assertEqual(plan.e, 0.005)
        self.assertEqual(plan.d, 0.005)
        self.assertEqual(plan.n, 3000)
        self.assertEqual(plan.unit, "kg")
        self.assertEqual(plan.verification_type, "INITIAL")
        self.assertFalse(plan.is_partial_plan)
        self.assertEqual(len(plan.partial_plan_reasons), 0)

        # Check collections
        self.assertIsInstance(plan.applicable_tests, list)
        self.assertIn("A.4.4", plan.applicable_tests)
        self.assertIn("A.4.7", plan.applicable_tests)
        self.assertIn("A.4.10", plan.applicable_tests)
        self.assertIn("A.4.8", plan.applicable_tests)
        self.assertIsInstance(plan.not_applicable_tests, list)
        self.assertIsInstance(plan.manual_review_items, list)
        self.assertIsInstance(plan.calculated_test_loads, list)
        self.assertGreater(len(plan.calculated_test_loads), 0)
        self.assertIsInstance(plan.required_equipment, list)
        self.assertIn("M1", "".join(plan.required_equipment))
        self.assertIsInstance(plan.required_environmental_conditions, dict)
        self.assertIn("prescribed_temperature_range", plan.required_environmental_conditions)
        self.assertIsInstance(plan.tests, list)
        self.assertGreater(len(plan.tests), 5)

    def test_to_dict_conversion(self):
        """Verify to_dict returns serializable dictionary with all required keys."""
        plan_dict = generate_regulatory_test_plan(self.standard_class_iii_spec)
        self.assertIsInstance(plan_dict, dict)
        expected_keys = {
            "test_plan_id", "job_id", "instrument_id", "regulatory_profile",
            "accuracy_class", "max_capacity", "min_capacity", "e", "d", "n",
            "unit", "verification_type", "is_partial_plan", "partial_plan_reasons",
            "applicable_tests", "not_applicable_tests", "manual_review_items",
            "calculated_test_loads", "required_equipment",
            "required_environmental_conditions", "mpe_reference", "tests",
            "generated_at"
        }
        for k in expected_keys:
            self.assertIn(k, plan_dict, f"Missing key '{k}' in generated plan dictionary.")

    # -------------------------------------------------------------------------
    # 2. Weighing Performance (A.4.4)
    # -------------------------------------------------------------------------

    def test_weighing_performance_load_points_and_mpe(self):
        """
        Verify A.4.4 weighing performance points include Zero, Min, MPE breakpoints,
        50% Max, Max with increasing and decreasing sequence and exact MPE bounds.
        """
        plan = RegulatoryTestPlanGenerator.generate(self.standard_class_iii_spec)
        wp_tests = [t for t in plan.tests if t["test_id"] == "A.4.4"]
        self.assertEqual(len(wp_tests), 1)
        wp = wp_tests[0]

        loads = wp["test_loads"]
        self.assertGreater(len(loads), 8)

        # Separate increasing and decreasing
        inc = [pt for pt in loads if pt["direction"] == "INCREASING"]
        dec = [pt for pt in loads if pt["direction"] == "DECREASING"]
        self.assertTrue(len(inc) > 0)
        self.assertTrue(len(dec) > 0)

        # Increasing loads start at 0 and end at Max (15.0)
        self.assertEqual(inc[0]["load"], 0.0)
        self.assertEqual(inc[-1]["load"], 15.0)

        # Breakpoints for Class III with e=0.005kg:
        # 500e = 2.5 kg, 2000e = 10.0 kg, 50% Max = 7.5 kg
        inc_load_vals = [pt["load"] for pt in inc]
        self.assertIn(0.1, inc_load_vals)   # Min
        self.assertIn(2.5, inc_load_vals)   # 500e
        self.assertIn(7.5, inc_load_vals)   # 50% Max
        self.assertIn(10.0, inc_load_vals)  # 2000e
        self.assertIn(15.0, inc_load_vals)  # Max

        # Check MPE values on increasing points:
        # Load 2.5kg = 500e -> MPE is 0.5e = 0.0025kg
        pt_500e = next(pt for pt in inc if abs(pt["load"] - 2.5) < 1e-6)
        self.assertEqual(pt_500e["mpe_in_e"], 0.5)
        self.assertEqual(pt_500e["mpe_absolute"], 0.0025)

        # Load 7.5kg = 1500e -> MPE is 1.0e = 0.005kg
        pt_7500 = next(pt for pt in inc if abs(pt["load"] - 7.5) < 1e-6)
        self.assertEqual(pt_7500["mpe_in_e"], 1.0)
        self.assertEqual(pt_7500["mpe_absolute"], 0.005)

        # Load 15.0kg = 3000e -> MPE is 1.5e = 0.0075kg
        pt_max = next(pt for pt in inc if abs(pt["load"] - 15.0) < 1e-6)
        self.assertEqual(pt_max["mpe_in_e"], 1.5)
        self.assertEqual(pt_max["mpe_absolute"], 0.0075)

        # Decreasing loads end at 0.0
        self.assertEqual(dec[-1]["load"], 0.0)

    # -------------------------------------------------------------------------
    # 3. Eccentricity Test (A.4.7)
    # -------------------------------------------------------------------------

    def test_eccentricity_load_calculation_standard_platter(self):
        """Verify standard platter eccentricity load = Max / 3 across 5 positions."""
        plan = RegulatoryTestPlanGenerator.generate(self.standard_class_iii_spec)
        ecc_tests = [t for t in plan.tests if t["test_id"] == "A.4.7"]
        self.assertEqual(len(ecc_tests), 1)
        ecc = ecc_tests[0]

        # 15.0 / 3 = 5.0 kg
        self.assertEqual(len(ecc["test_loads"]), 5)
        positions = [pt["position"] for pt in ecc["test_loads"]]
        self.assertEqual(positions, [
            "CENTER",
            "CORNER_1_FRONT_LEFT",
            "CORNER_2_BACK_LEFT",
            "CORNER_3_BACK_RIGHT",
            "CORNER_4_FRONT_RIGHT",
        ])
        for pt in ecc["test_loads"]:
            self.assertEqual(pt["load"], 5.0)
            self.assertEqual(pt["mpe_in_e"], 1.0)  # 5kg = 1000e -> 1.0e

    def test_eccentricity_with_additive_tare(self):
        """Verify eccentricity load = (Max + AdditiveTare) / 3."""
        spec = dict(self.standard_class_iii_spec)
        spec["additive_tare"] = 3.0  # (15 + 3) / 3 = 6.0 kg
        plan = RegulatoryTestPlanGenerator.generate(spec)

        ecc = next(t for t in plan.tests if t["test_id"] == "A.4.7")
        for pt in ecc["test_loads"]:
            self.assertEqual(pt["load"], 6.0)

    # -------------------------------------------------------------------------
    # 4. Repeatability Test (A.4.10)
    # -------------------------------------------------------------------------

    def test_repeatability_routine_verification(self):
        """Verify routine verification repeatability generates 3 cycles at 50% and 100% Max."""
        plan = RegulatoryTestPlanGenerator.generate(self.standard_class_iii_spec)
        rep = next(t for t in plan.tests if t["test_id"] == "A.4.10")

        # 2 levels * 3 weighings = 6 test points
        self.assertEqual(len(rep["test_loads"]), 6)
        loads_50 = [pt for pt in rep["test_loads"] if abs(pt["load"] - 7.5) < 1e-6]
        loads_100 = [pt for pt in rep["test_loads"] if abs(pt["load"] - 15.0) < 1e-6]
        self.assertEqual(len(loads_50), 3)
        self.assertEqual(len(loads_100), 3)
        self.assertIn("Spread", rep["acceptance_criteria"])

    def test_repeatability_type_evaluation(self):
        """Verify type evaluation repeatability generates 10 cycles at each load level."""
        spec = dict(self.standard_class_iii_spec)
        spec["is_type_evaluation"] = True
        plan = RegulatoryTestPlanGenerator.generate(spec)

        rep = next(t for t in plan.tests if t["test_id"] == "A.4.10")
        # 2 levels * 10 weighings = 20 test points
        self.assertEqual(len(rep["test_loads"]), 20)
        self.assertIn("10 repeated weighings", rep["acceptance_criteria"])

    # -------------------------------------------------------------------------
    # 5. Digital Discrimination Test (A.4.8)
    # -------------------------------------------------------------------------

    def test_digital_discrimination_calculation(self):
        """Verify extra load of 1.4d and acceptance criteria of +1d change."""
        plan = RegulatoryTestPlanGenerator.generate(self.standard_class_iii_spec)
        disc = next(t for t in plan.tests if t["test_id"] == "A.4.8")

        self.assertEqual(len(disc["test_loads"]), 3)  # Min, 50% Max, Max
        for pt in disc["test_loads"]:
            # d = 0.005 -> 1.4d = 0.007
            self.assertEqual(pt["extra_load"], 0.007)
            self.assertIn("1.4d", pt["remarks"])

        self.assertIn("+0.005 kg", disc["acceptance_criteria"])

    # -------------------------------------------------------------------------
    # 6. Creep Test (A.4.11.1)
    # -------------------------------------------------------------------------

    def test_creep_test_schedule_and_early_termination(self):
        """Verify 0, 5, 15, 30 min intervals and 0.2e early termination rule."""
        spec = dict(self.standard_class_iii_spec)
        spec["is_type_evaluation"] = True
        plan = RegulatoryTestPlanGenerator.generate(spec)
        creep = next(t for t in plan.tests if t["test_id"] == "A.4.11.1")

        self.assertEqual(len(creep["test_loads"]), 4)
        times = [pt["observation_period_minutes"] for pt in creep["test_loads"]]
        self.assertEqual(times, [0, 5, 15, 30])

        # Verify special conditions dictionary
        conds = creep.get("special_conditions", {})
        self.assertEqual(conds.get("early_termination_delta_e"), 0.2)
        self.assertEqual(conds.get("total_max_drift_e"), 0.5)
        self.assertIn("Early Termination Rule", creep["acceptance_criteria"])

    # -------------------------------------------------------------------------
    # 7. Temperature Effect Test (A.5.3)
    # -------------------------------------------------------------------------

    def test_temperature_test_specifications(self):
        """Verify climatic chamber steps and rate of change limits."""
        spec = dict(self.standard_class_iii_spec)
        spec["is_type_evaluation"] = True
        plan = RegulatoryTestPlanGenerator.generate(spec)

        temp_test = next(t for t in plan.tests if t["test_id"] == "A.5.3")
        conds = temp_test.get("special_conditions", {})
        self.assertEqual(conds.get("chamber_temperature_steps_celsius"), [20, 40, -10, 20])
        self.assertEqual(conds.get("thermal_soak_hours_per_step"), 2)
        self.assertEqual(conds.get("max_temp_change_rate_c_per_hour"), 5.0)

    # -------------------------------------------------------------------------
    # 8. Ambiguous / Complex Cases: Multi-Interval Partial Plan
    # -------------------------------------------------------------------------

    def test_multi_interval_generates_partial_plan(self):
        """Verify multi-interval instruments trigger partial plan and manual review flags."""
        spec = dict(self.standard_class_iii_spec)
        spec["multi_interval_status"] = True
        plan = RegulatoryTestPlanGenerator.generate(spec)

        self.assertTrue(plan.is_partial_plan)
        self.assertTrue(len(plan.partial_plan_reasons) > 0)
        self.assertIn("discontinuous scale intervals", plan.partial_plan_reasons[0])

        # Verify PARTIAL_PLAN_ALERT in manual review items
        alerts = [m for m in plan.manual_review_items if m.get("test_id") == "PARTIAL_PLAN_ALERT"]
        self.assertTrue(len(alerts) > 0)

    # -------------------------------------------------------------------------
    # 9. Invalid Specification Handling
    # -------------------------------------------------------------------------

    def test_invalid_spec_generates_partial_plan_with_errors(self):
        """Verify classification validation failures are captured in partial plan reasons."""
        spec = dict(self.standard_class_iii_spec)
        spec["Min"] = 25.0  # Min > Max (15.0)
        plan = RegulatoryTestPlanGenerator.generate(spec)

        self.assertTrue(plan.is_partial_plan)
        self.assertTrue(any("Min" in r for r in plan.partial_plan_reasons))

    # -------------------------------------------------------------------------
    # 10. Subsequent Verification (Doubled MPE)
    # -------------------------------------------------------------------------

    def test_subsequent_verification_mpe_doubling(self):
        """Verify subsequent verification uses 2x initial MPE for tolerance bounds."""
        spec = dict(self.standard_class_iii_spec)
        spec["verification_type"] = "SUBSEQUENT"
        plan = RegulatoryTestPlanGenerator.generate(spec)

        self.assertEqual(plan.verification_type, "SUBSEQUENT")
        wp = next(t for t in plan.tests if t["test_id"] == "A.4.4")
        pt_500e = next(pt for pt in wp["test_loads"] if abs(pt["load"] - 2.5) < 1e-6)
        # Initial 0.5e -> Subsequent 1.0e = 0.005kg
        self.assertEqual(pt_500e["mpe_in_e"], 1.0)
        self.assertEqual(pt_500e["mpe_absolute"], 0.005)

    # -------------------------------------------------------------------------
    # 11. Router Functions Compatibility
    # -------------------------------------------------------------------------

    def test_router_api_generate_regulatory_test_plan(self):
        """Verify api_generate_regulatory_test_plan returns complete dictionary."""
        res = api_generate_regulatory_test_plan(self.standard_class_iii_spec)
        self.assertIn("test_plan_id", res)
        self.assertIn("tests", res)
        self.assertEqual(res["accuracy_class"], "III")

    def test_router_api_generate_test_plan_flat_spec(self):
        """Verify api_generate_test_plan automatically handles flat specs with new pipeline."""
        res = api_generate_test_plan(self.standard_class_iii_spec)
        self.assertIn("test_plan_id", res)
        self.assertEqual(res["max_capacity"], 15.0)

    def test_weights_accuracy_class_mapping(self):
        """Verify standard weights class selection across accuracy classes."""
        for acc_cls, expected_wt in [
            ("I", "E2"),
            ("II", "F1"),
            ("III", "M1"),
            ("IIII", "M2"),
        ]:
            spec = dict(self.standard_class_iii_spec)
            spec["accuracy_class"] = acc_cls
            if acc_cls == "I":
                spec["Max"] = 1.0
                spec["e"] = 0.0001
            elif acc_cls == "II":
                spec["Max"] = 5.0
                spec["e"] = 0.001
            elif acc_cls == "IIII":
                spec["Max"] = 50.0
                spec["e"] = 0.1

            plan = RegulatoryTestPlanGenerator.generate(spec)
            weights_found = any(expected_wt in eq for eq in plan.required_equipment)
            self.assertTrue(weights_found, f"Expected {expected_wt} for class {acc_cls}")


if __name__ == "__main__":
    unittest.main()
