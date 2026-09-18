"""
MetrIQ Regulatory Engine - Comprehensive Unit Test Suite
Verifies OIML R 76-1:2006 and Indian Legal Metrology (General) Rules, 2011 compliance:
- Scale interval form (1, 2, 5 * 10^k)
- Accuracy class limits (I, II, III, IIII)
- e / Max / Min / n relationships
- Auxiliary indicating devices (d vs e)
- Multi-interval instruments
- MPE calculation for Initial and In-Service verification
- Tare and net load MPE
- Statutory test applicability matrix
- Automatic test plan generation
"""

import unittest
import json
import sys
import os

# Add backend directory to sys.path so app.regulatory can be imported
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.regulatory import (
    AccuracyClass,
    InstrumentProfile,
    JobType,
    MassUnit,
    MPEValue,
    ReceptorType,
    RegulatoryConfig,
    RegulatoryErrorCode,
    RegulatoryIssue,
    RegulatoryValidationError,
    TestPlan,
    TestPoint,
    TestType,
    ValidationResult,
    WeighingRange,
    calculate_mpe,
    calculate_mpe_in_e,
    determine_eligible_classes,
    generate_test_plan,
    get_applicable_tests,
    is_error_within_mpe,
    is_test_applicable,
    is_valid_scale_interval_form,
    validate_accuracy_class,
    validate_auxiliary_device,
    validate_instrument_scales,
    validate_multi_interval,
    REGULATORY_REGISTRY,
)
from app.regulatory.router import (
    api_validate_scales,
    api_calculate_mpe,
    api_evaluate_error,
    api_applicable_tests,
    api_generate_test_plan,
    api_list_standards,
)


class TestScaleIntervalForm(unittest.TestCase):
    """Verifies that verification scale interval e is strictly 1, 2, or 5 * 10^k."""

    def test_valid_scale_intervals(self):
        valid_values = [
            0.0001, 0.0002, 0.0005,
            0.001, 0.002, 0.005,
            0.01, 0.02, 0.05,
            0.1, 0.2, 0.5,
            1.0, 2.0, 5.0,
            10.0, 20.0, 50.0,
            100.0, 200.0, 500.0,
            1000.0, 2000.0, 5000.0,
        ]
        for v in valid_values:
            is_valid, msg = is_valid_scale_interval_form(v)
            self.assertTrue(is_valid, f"Expected {v} to be valid, got: {msg}")

    def test_invalid_scale_intervals(self):
        invalid_values = [
            0.003, 0.007, 0.025,
            0.3, 0.4, 0.7,
            3.0, 4.0, 6.0, 7.0, 8.0, 9.0,
            15.0, 25.0, 30.0, 75.0,
            -1.0, 0.0,
        ]
        for v in invalid_values:
            is_valid, _ = is_valid_scale_interval_form(v)
            self.assertFalse(is_valid, f"Expected {v} to be invalid form.")


class TestAccuracyClassValidation(unittest.TestCase):
    """Verifies statutory accuracy class validation against Table 3 / Table 1."""

    def test_valid_class_i_analytical_balance(self):
        # Class I: Max = 220 g, e = 1 mg (0.001 g), d = 0.1 mg (0.0001 g), Min = 100e (0.1 g), n = 220,000
        inst = InstrumentProfile(
            manufacturer="Mettler",
            model="XSR205",
            accuracy_class=AccuracyClass.CLASS_I,
            max_capacity=220.0,
            min_capacity=0.1,
            e=0.001,
            d=0.0001,
            unit=MassUnit.G,
        )
        res = validate_instrument_scales(inst)
        self.assertTrue(res.is_valid, f"Validation errors: {[e.message for e in res.errors]}")
        self.assertEqual(res.metadata["n"], 220000)

    def test_valid_class_ii_precision_scale(self):
        # Class II: Max = 6000 g, e = 0.1 g, d = 0.01 g, Min = 50e (5 g), n = 60,000
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_II,
            max_capacity=6000.0,
            min_capacity=5.0,
            e=0.1,
            d=0.01,
            unit=MassUnit.G,
        )
        res = validate_instrument_scales(inst)
        self.assertTrue(res.is_valid, f"Validation errors: {[e.message for e in res.errors]}")

    def test_valid_class_iii_commercial_bench_scale(self):
        # Class III: Max = 15 kg, e = 5 g (0.005 kg), d = 5 g, Min = 20e (100 g = 0.1 kg), n = 3,000
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
        )
        res = validate_instrument_scales(inst)
        self.assertTrue(res.is_valid, f"Validation errors: {[e.message for e in res.errors]}")
        self.assertEqual(res.metadata["n"], 3000)

    def test_valid_class_iiii_industrial_platform(self):
        # Class IIII: Max = 1000 kg, e = 1 kg, Min = 10e (10 kg), n = 1,000
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_IIII,
            max_capacity=1000.0,
            min_capacity=10.0,
            e=1.0,
            d=1.0,
            unit=MassUnit.KG,
        )
        res = validate_instrument_scales(inst)
        self.assertTrue(res.is_valid, f"Validation errors: {[e.message for e in res.errors]}")

    def test_class_iii_n_too_large(self):
        # Class III has maximum n = 10,000. If Max = 300 kg and e = 5 g (0.005 kg), n = 60,000 -> INVALID
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=300.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
        )
        res = validate_instrument_scales(inst)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn(RegulatoryErrorCode.N_OUT_OF_BOUNDS, error_codes)

    def test_class_iii_n_too_small(self):
        # For Class III with e >= 5 g, n_min is 500. If Max = 2 kg, e = 5 g (0.005 kg), n = 400 -> INVALID
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=2.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
        )
        res = validate_instrument_scales(inst)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn(RegulatoryErrorCode.N_OUT_OF_BOUNDS, error_codes)

    def test_min_capacity_violation(self):
        # Class III requires Min >= 20e. If e = 5 g (0.005 kg), Min must be >= 0.1 kg (100 g).
        # If Min = 0.05 kg (10e), it violates statutory minimum.
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.05,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
        )
        res = validate_instrument_scales(inst)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn(RegulatoryErrorCode.MIN_CAPACITY_VIOLATION, error_codes)


class TestAuxiliaryIndicatingDeviceRules(unittest.TestCase):
    """Verifies rules for d vs e (Clause 3.4)."""

    def test_class_iii_disallows_auxiliary_device(self):
        # In Class III, d < e is not permitted under standard verification
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            d=0.001,  # d < e on Class III
            unit=MassUnit.KG,
        )
        res = validate_instrument_scales(inst)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn(RegulatoryErrorCode.INVALID_AUXILIARY_DEVICE, error_codes)

    def test_d_cannot_exceed_e(self):
        # d > e is always an error
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_II,
            max_capacity=1000.0,
            min_capacity=1.0,
            e=0.01,
            d=0.02,  # d > e
            unit=MassUnit.G,
        )
        res = validate_instrument_scales(inst)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn(RegulatoryErrorCode.INVALID_AUXILIARY_DEVICE, error_codes)

    def test_e_cannot_exceed_10d(self):
        # e <= 10d required. If e = 0.1 g and d = 0.001 g (e = 100d), it violates Clause 3.4.2
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_II,
            max_capacity=2000.0,
            min_capacity=5.0,
            e=0.1,
            d=0.001,  # e = 100d > 10d
            unit=MassUnit.G,
        )
        res = validate_instrument_scales(inst)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn(RegulatoryErrorCode.INVALID_AUXILIARY_DEVICE, error_codes)


class TestMultiIntervalValidation(unittest.TestCase):
    """Verifies multi-interval partial range specifications."""

    def test_valid_dual_interval_scale(self):
        # Dual interval retail scale:
        # Range 1: Max 6 kg, Min 0.04 kg, e1 = 2 g (0.002 kg), n1 = 3,000
        # Range 2: Max 15 kg, Min 0.04 kg, e2 = 5 g (0.005 kg), n2 = 3,000
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.04,
            e=0.002,
            unit=MassUnit.KG,
            is_multi_interval=True,
            partial_ranges=[
                WeighingRange(range_index=1, max_capacity=6.0, min_capacity=0.04, e=0.002, unit=MassUnit.KG),
                WeighingRange(range_index=2, max_capacity=15.0, min_capacity=0.04, e=0.005, unit=MassUnit.KG),
            ],
        )
        res = validate_instrument_scales(inst)
        self.assertTrue(res.is_valid, f"Errors: {[e.message for e in res.errors]}")

    def test_invalid_partial_range_order(self):
        # e2 <= e1 is illegal
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.04,
            e=0.005,
            unit=MassUnit.KG,
            is_multi_interval=True,
            partial_ranges=[
                WeighingRange(range_index=1, max_capacity=6.0, min_capacity=0.04, e=0.005, unit=MassUnit.KG),
                WeighingRange(range_index=2, max_capacity=15.0, min_capacity=0.04, e=0.002, unit=MassUnit.KG),
            ],
        )
        res = validate_instrument_scales(inst)
        self.assertFalse(res.is_valid)
        error_codes = [e.code for e in res.errors]
        self.assertIn(RegulatoryErrorCode.PARTIAL_RANGE_ORDERING, error_codes)


class TestMPECalculation(unittest.TestCase):
    """Verifies MPE calculations across all accuracy classes and verification types."""

    def test_class_iii_initial_verification_mpe(self):
        # Class III instrument with e = 5 g (0.005 kg)
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            unit=MassUnit.KG,
        )

        # 1. Load = 2.5 kg (500e): should be +/- 0.5e = +/- 2.5 g (+/- 0.0025 kg)
        mpe_500 = calculate_mpe(2.5, inst, job_type=JobType.INITIAL_VERIFICATION)
        self.assertEqual(mpe_500.mpe_in_e, 0.5)
        self.assertAlmostEqual(mpe_500.mpe_in_units, 0.0025, places=6)
        self.assertEqual(mpe_500.verification_type, "INITIAL")

        # 2. Load = 5.0 kg (1000e): in range (500e, 2000e] -> +/- 1.0e = +/- 5.0 g (+/- 0.005 kg)
        mpe_1000 = calculate_mpe(5.0, inst, job_type=JobType.INITIAL_VERIFICATION)
        self.assertEqual(mpe_1000.mpe_in_e, 1.0)
        self.assertAlmostEqual(mpe_1000.mpe_in_units, 0.005, places=6)

        # 3. Load = 10.0 kg (2000e): boundary -> +/- 1.0e = +/- 5.0 g (+/- 0.005 kg)
        mpe_2000 = calculate_mpe(10.0, inst, job_type=JobType.INITIAL_VERIFICATION)
        self.assertEqual(mpe_2000.mpe_in_e, 1.0)
        self.assertAlmostEqual(mpe_2000.mpe_in_units, 0.005, places=6)

        # 4. Load = 15.0 kg (3000e): in range (2000e, 10000e] -> +/- 1.5e = +/- 7.5 g (+/- 0.0075 kg)
        mpe_3000 = calculate_mpe(15.0, inst, job_type=JobType.INITIAL_VERIFICATION)
        self.assertEqual(mpe_3000.mpe_in_e, 1.5)
        self.assertAlmostEqual(mpe_3000.mpe_in_units, 0.0075, places=6)

    def test_class_iii_in_service_reverification_mpe(self):
        # In-service MPE is 2 * Initial MPE (Clause 3.5.2)
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            unit=MassUnit.KG,
        )

        # 1. Load = 2.5 kg (500e): in-service MPE = 2 * 0.5e = 1.0e = 5 g
        mpe_500 = calculate_mpe(2.5, inst, job_type=JobType.RE_VERIFICATION)
        self.assertEqual(mpe_500.mpe_in_e, 1.0)
        self.assertAlmostEqual(mpe_500.mpe_in_units, 0.005, places=6)
        self.assertEqual(mpe_500.verification_type, "IN_SERVICE")

        # 2. Load = 15.0 kg (3000e): in-service MPE = 2 * 1.5e = 3.0e = 15 g
        mpe_3000 = calculate_mpe(15.0, inst, job_type=JobType.RE_VERIFICATION)
        self.assertEqual(mpe_3000.mpe_in_e, 3.0)
        self.assertAlmostEqual(mpe_3000.mpe_in_units, 0.015, places=6)

    def test_tare_net_load_mpe(self):
        # When tare is applied, MPE applies to the net load (Clause 3.5.3.3)
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            has_tare=True,
            unit=MassUnit.KG,
        )
        # Tare load = 5 kg (1000e). Gross load = 7.5 kg. Net load = 2.5 kg (500e).
        # For net load 500e, MPE on initial verification is +/- 0.5e (not +/- 1.0e that 7.5 kg gross would yield)
        mpe_net = calculate_mpe(7.5, inst, job_type=JobType.INITIAL_VERIFICATION, tare_load=5.0)
        self.assertEqual(mpe_net.mpe_in_e, 0.5)
        self.assertEqual(mpe_net.net_load, 2.5)
        self.assertAlmostEqual(mpe_net.mpe_in_units, 0.0025, places=6)

    def test_error_pass_fail_evaluation(self):
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            unit=MassUnit.KG,
        )
        # At 2.5 kg, MPE is +/- 0.0025 kg
        is_pass, mpe = is_error_within_mpe(0.002, 2.5, inst)
        self.assertTrue(is_pass)

        is_fail, mpe = is_error_within_mpe(0.003, 2.5, inst)
        self.assertFalse(is_fail)


class TestApplicabilityAndTestPlan(unittest.TestCase):
    """Verifies statutory test applicability and automatic test plan generation."""

    def test_applicable_tests_for_initial_verification(self):
        inst = InstrumentProfile(
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            has_tare=True,
            is_electronic=True,
            has_software=True,
            unit=MassUnit.KG,
        )
        tests = get_applicable_tests(inst, JobType.INITIAL_VERIFICATION)
        app_types = {t.test_type for t in tests if t.applicable}

        self.assertIn(TestType.VISUAL_EXAMINATION, app_types)
        self.assertIn(TestType.WEIGHING_PERFORMANCE, app_types)
        self.assertIn(TestType.ECCENTRICITY, app_types)
        self.assertIn(TestType.REPEATABILITY, app_types)
        self.assertIn(TestType.DISCRIMINATION, app_types)
        self.assertIn(TestType.TARE, app_types)
        self.assertIn(TestType.SOFTWARE_EXAMINATION, app_types)

        # Environmental chamber temperature test is strictly MODEL_APPROVAL
        self.assertNotIn(TestType.TEMPERATURE_EFFECT, app_types)

    def test_generate_test_plan(self):
        inst = InstrumentProfile(
            manufacturer="Avery Weigh-Tronix",
            model="ZM301",
            serial_number="SN-998822",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            has_tare=True,
            unit=MassUnit.KG,
        )
        plan = generate_test_plan(inst, JobType.INITIAL_VERIFICATION)

        self.assertIsNotNone(plan.plan_id)
        self.assertGreater(plan.total_test_points, 10)
        self.assertIn(TestType.WEIGHING_PERFORMANCE.value, plan.test_suites)
        self.assertIn(TestType.ECCENTRICITY.value, plan.test_suites)
        self.assertIn(TestType.REPEATABILITY.value, plan.test_suites)
        self.assertIn(TestType.TARE.value, plan.test_suites)

        # Eccentricity points should be 1/3 Max = 5.0 kg
        ecc_points = plan.test_suites[TestType.ECCENTRICITY.value]
        self.assertEqual(len(ecc_points), 5)  # Center + 4 corners
        self.assertEqual(ecc_points[0].target_load, 5.0)

        # Repeatability points should have 3 runs each for ~50% and ~100% Max
        rep_points = plan.test_suites[TestType.REPEATABILITY.value]
        self.assertEqual(len(rep_points), 6)

        # Verify JSON serializability of test plan
        plan_dict = plan.to_dict()
        json_str = json.dumps(plan_dict)
        self.assertIn("PLAN-", json_str)


class TestAPIEndpoints(unittest.TestCase):
    """Verifies the pure-Python service functions designed for Person 1 integration."""

    def test_api_validate_scales(self):
        payload = {
            "accuracy_class": "CLASS_III",
            "max_capacity": 15.0,
            "min_capacity": 0.1,
            "e": 0.005,
            "unit": "kg",
        }
        res = api_validate_scales(payload)
        self.assertTrue(res["is_valid"])
        self.assertEqual(res["error_count"], 0)

    def test_api_calculate_mpe(self):
        payload = {
            "instrument": {
                "accuracy_class": "CLASS_III",
                "max_capacity": 15.0,
                "min_capacity": 0.1,
                "e": 0.005,
                "unit": "kg",
            },
            "load": 2.5,
            "job_type": "INITIAL_VERIFICATION",
        }
        res = api_calculate_mpe(payload)
        self.assertEqual(res["mpe_in_e"], 0.5)
        self.assertEqual(res["mpe_in_units"], 0.0025)

    def test_api_generate_test_plan(self):
        payload = {
            "instrument": {
                "accuracy_class": "CLASS_III",
                "max_capacity": 30.0,
                "min_capacity": 0.2,
                "e": 0.01,
                "unit": "kg",
            },
            "job_type": "INITIAL_VERIFICATION",
        }
        res = api_generate_test_plan(payload)
        self.assertIn("plan_id", res)
        self.assertGreater(res["total_test_points"], 5)


if __name__ == "__main__":
    unittest.main()
