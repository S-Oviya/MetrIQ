"""
Unit Tests for MetrIQ Maximum Permissible Error (MPE) Calculation Engine
========================================================================

Validates:
1. OIML R 76-1:2006 Table 6 & Indian Legal Metrology Rules, 2011 Table 2.
2. Initial Verification MPE thresholds across Classes I, II, III, IIII.
3. Subsequent Verification MPE thresholds (exactly 2 x Initial MPE).
4. Exact boundary transitions and just-over-boundary discrimination:
   - Class I: 50,000e / 50,000.001e, 200,000e / 200,000.001e, 1,000,000e
   - Class II: 5,000e / 5,000.001e, 20,000e / 20,000.001e, 100,000e
   - Class III: 500e / 500.001e, 2,000e / 2,000.001e, 10,000e
   - Class IIII: 50e / 50.001e, 200e / 200.001e, 1,000e
5. Strict floating point precision handling without arbitrary tolerance fudge.
6. Dual-unit representation (e and instrument measurement units).
7. Observed error evaluation: |observed_error| <= MPE with pass/fail/margin.
8. API router integration for stateless calculation.
"""

import math
import os
import sys
import unittest
from decimal import Decimal

# Add backend directory to sys.path so app.regulatory can be imported
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.regulatory.models import AccuracyClass, JobType
from app.regulatory.mpe_engine import (
    MPEBandDefinition,
    MPECalculationResult,
    MPEEngine,
    MPE_STATUTORY_TABLE,
    VerificationType,
    calculate_mpe_statutory,
)
from app.regulatory.router import api_calculate_mpe


class TestMPEEngineClassI(unittest.TestCase):
    """Class I (Special Accuracy) MPE boundary tests."""

    def test_class_i_band_1_boundaries(self):
        # 0 <= m <= 50,000 e -> 0.5e
        e_val = 0.001  # 1 mg

        # Lower bound: 0e
        res_0 = MPEEngine.calculate(AccuracyClass.CLASS_I, load=0.0, e=e_val)
        self.assertEqual(res_0.load_in_e, 0.0)
        self.assertEqual(res_0.mpe_in_e, 0.5)
        self.assertEqual(res_0.band_index, 1)

        # Intermediate: 25,000e
        res_mid = MPEEngine.calculate(AccuracyClass.CLASS_I, load=25.0, e=e_val)
        self.assertEqual(res_mid.load_in_e, 25000.0)
        self.assertEqual(res_mid.mpe_in_e, 0.5)
        self.assertEqual(res_mid.band_index, 1)

        # Upper bound: exactly 50,000e -> must be 0.5e!
        res_50k = MPEEngine.calculate(AccuracyClass.CLASS_I, load=50.0, e=e_val)
        self.assertEqual(res_50k.load_in_e, 50000.0)
        self.assertEqual(res_50k.mpe_in_e, 0.5)
        self.assertEqual(res_50k.band_index, 1)

    def test_class_i_band_2_boundaries(self):
        # 50,000 e < m <= 200,000 e -> 1.0e
        e_val = 0.001

        # Just over boundary: 50,000.001e -> must step up to 1.0e!
        load_just_over = 50.000001
        res_just_over = MPEEngine.calculate(AccuracyClass.CLASS_I, load=load_just_over, e=e_val)
        self.assertAlmostEqual(res_just_over.load_in_e, 50000.001, places=3)
        self.assertEqual(res_just_over.mpe_in_e, 1.0)
        self.assertEqual(res_just_over.band_index, 2)

        # Intermediate: 100,000e
        res_100k = MPEEngine.calculate(AccuracyClass.CLASS_I, load=100.0, e=e_val)
        self.assertEqual(res_100k.load_in_e, 100000.0)
        self.assertEqual(res_100k.mpe_in_e, 1.0)
        self.assertEqual(res_100k.band_index, 2)

        # Upper bound: exactly 200,000e -> must be 1.0e!
        res_200k = MPEEngine.calculate(AccuracyClass.CLASS_I, load=200.0, e=e_val)
        self.assertEqual(res_200k.load_in_e, 200000.0)
        self.assertEqual(res_200k.mpe_in_e, 1.0)
        self.assertEqual(res_200k.band_index, 2)

    def test_class_i_band_3_boundaries(self):
        # 200,000 e < m <= 1,000,000 e -> 1.5e
        e_val = 0.001

        # Just over boundary: 200,000.001e -> must step up to 1.5e!
        load_just_over = 200.000001
        res_just_over = MPEEngine.calculate(AccuracyClass.CLASS_I, load=load_just_over, e=e_val)
        self.assertAlmostEqual(res_just_over.load_in_e, 200000.001, places=3)
        self.assertEqual(res_just_over.mpe_in_e, 1.5)
        self.assertEqual(res_just_over.band_index, 3)

        # 1,000,000e
        res_1m = MPEEngine.calculate(AccuracyClass.CLASS_I, load=1000.0, e=e_val)
        self.assertEqual(res_1m.load_in_e, 1000000.0)
        self.assertEqual(res_1m.mpe_in_e, 1.5)
        self.assertEqual(res_1m.band_index, 3)

        # Over 1,000,000e
        res_over_1m = MPEEngine.calculate(AccuracyClass.CLASS_I, load=1000.000001, e=e_val)
        self.assertEqual(res_over_1m.mpe_in_e, 1.5)
        self.assertFalse(res_over_1m.is_within_statutory_capacity)


class TestMPEEngineClassII(unittest.TestCase):
    """Class II (High Accuracy) MPE boundary tests."""

    def test_class_ii_band_1_boundaries(self):
        # 0 <= m <= 5,000 e -> 0.5e
        e_val = 0.005  # 5 mg (0.005 g)

        # Exactly 0e
        res_0 = MPEEngine.calculate(AccuracyClass.CLASS_II, load=0.0, e=e_val)
        self.assertEqual(res_0.load_in_e, 0.0)
        self.assertEqual(res_0.mpe_in_e, 0.5)
        self.assertEqual(res_0.band_index, 1)

        # Exactly 5,000e (5000 * 0.005 = 25.0) -> must be 0.5e!
        res_5k = MPEEngine.calculate(AccuracyClass.CLASS_II, load=25.0, e=e_val)
        self.assertEqual(res_5k.load_in_e, 5000.0)
        self.assertEqual(res_5k.mpe_in_e, 0.5)
        self.assertEqual(res_5k.band_index, 1)

    def test_class_ii_band_2_boundaries(self):
        # 5,000 e < m <= 20,000 e -> 1.0e
        e_val = 0.005

        # Just over 5,000e (5000.001 * 0.005 = 25.000005) -> must be 1.0e!
        res_just_over_5k = MPEEngine.calculate(AccuracyClass.CLASS_II, load=25.000005, e=e_val)
        self.assertAlmostEqual(res_just_over_5k.load_in_e, 5000.001, places=3)
        self.assertEqual(res_just_over_5k.mpe_in_e, 1.0)
        self.assertEqual(res_just_over_5k.band_index, 2)

        # Exactly 20,000e (20000 * 0.005 = 100.0) -> must be 1.0e!
        res_20k = MPEEngine.calculate(AccuracyClass.CLASS_II, load=100.0, e=e_val)
        self.assertEqual(res_20k.load_in_e, 20000.0)
        self.assertEqual(res_20k.mpe_in_e, 1.0)
        self.assertEqual(res_20k.band_index, 2)

    def test_class_ii_band_3_boundaries(self):
        # 20,000 e < m <= 100,000 e -> 1.5e
        e_val = 0.005

        # Just over 20,000e (20000.001 * 0.005 = 100.000005) -> must be 1.5e!
        res_just_over_20k = MPEEngine.calculate(AccuracyClass.CLASS_II, load=100.000005, e=e_val)
        self.assertAlmostEqual(res_just_over_20k.load_in_e, 20000.001, places=3)
        self.assertEqual(res_just_over_20k.mpe_in_e, 1.5)
        self.assertEqual(res_just_over_20k.band_index, 3)

        # Exactly 100,000e (100000 * 0.005 = 500.0)
        res_100k = MPEEngine.calculate(AccuracyClass.CLASS_II, load=500.0, e=e_val)
        self.assertEqual(res_100k.load_in_e, 100000.0)
        self.assertEqual(res_100k.mpe_in_e, 1.5)
        self.assertTrue(res_100k.is_within_statutory_capacity)

        # Over 100,000e
        res_over_100k = MPEEngine.calculate(AccuracyClass.CLASS_II, load=500.000005, e=e_val)
        self.assertEqual(res_over_100k.mpe_in_e, 1.5)
        self.assertFalse(res_over_100k.is_within_statutory_capacity)


class TestMPEEngineClassIII(unittest.TestCase):
    """Class III (Medium Accuracy) MPE boundary tests."""

    def test_class_iii_band_1_boundaries(self):
        # 0 <= m <= 500 e -> 0.5e
        e_val = 0.002  # 2 g (0.002 kg)

        # Exactly 0e
        res_0 = MPEEngine.calculate(AccuracyClass.CLASS_III, load=0.0, e=e_val)
        self.assertEqual(res_0.load_in_e, 0.0)
        self.assertEqual(res_0.mpe_in_e, 0.5)
        self.assertEqual(res_0.band_index, 1)

        # Exactly 500e (500 * 0.002 = 1.0 kg) -> must be 0.5e!
        res_500 = MPEEngine.calculate(AccuracyClass.CLASS_III, load=1.0, e=e_val)
        self.assertEqual(res_500.load_in_e, 500.0)
        self.assertEqual(res_500.mpe_in_e, 0.5)
        self.assertEqual(res_500.band_index, 1)
        self.assertAlmostEqual(res_500.mpe_absolute, 0.5 * 0.002, places=6)

    def test_class_iii_band_2_boundaries(self):
        # 500 e < m <= 2,000 e -> 1.0e
        e_val = 0.002

        # Just over 500e (500.001 * 0.002 = 1.000002 kg) -> must step to 1.0e!
        res_just_over_500 = MPEEngine.calculate(AccuracyClass.CLASS_III, load=1.000002, e=e_val)
        self.assertAlmostEqual(res_just_over_500.load_in_e, 500.001, places=3)
        self.assertEqual(res_just_over_500.mpe_in_e, 1.0)
        self.assertEqual(res_just_over_500.band_index, 2)
        self.assertAlmostEqual(res_just_over_500.mpe_absolute, 1.0 * 0.002, places=6)

        # Exactly 2,000e (2000 * 0.002 = 4.0 kg) -> must be 1.0e!
        res_2000 = MPEEngine.calculate(AccuracyClass.CLASS_III, load=4.0, e=e_val)
        self.assertEqual(res_2000.load_in_e, 2000.0)
        self.assertEqual(res_2000.mpe_in_e, 1.0)
        self.assertEqual(res_2000.band_index, 2)
        self.assertAlmostEqual(res_2000.mpe_absolute, 1.0 * 0.002, places=6)

    def test_class_iii_band_3_boundaries(self):
        # 2,000 e < m <= 10,000 e -> 1.5e
        e_val = 0.002

        # Just over 2,000e (2000.001 * 0.002 = 4.000002 kg) -> must step to 1.5e!
        res_just_over_2k = MPEEngine.calculate(AccuracyClass.CLASS_III, load=4.000002, e=e_val)
        self.assertAlmostEqual(res_just_over_2k.load_in_e, 2000.001, places=3)
        self.assertEqual(res_just_over_2k.mpe_in_e, 1.5)
        self.assertEqual(res_just_over_2k.band_index, 3)
        self.assertAlmostEqual(res_just_over_2k.mpe_absolute, 1.5 * 0.002, places=6)

        # Exactly 10,000e (10000 * 0.002 = 20.0 kg) -> 1.5e!
        res_10k = MPEEngine.calculate(AccuracyClass.CLASS_III, load=20.0, e=e_val)
        self.assertEqual(res_10k.load_in_e, 10000.0)
        self.assertEqual(res_10k.mpe_in_e, 1.5)
        self.assertTrue(res_10k.is_within_statutory_capacity)

        # Over 10,000e (e.g. 10000.001e)
        res_over_10k = MPEEngine.calculate(AccuracyClass.CLASS_III, load=20.000002, e=e_val)
        self.assertEqual(res_over_10k.mpe_in_e, 1.5)
        self.assertFalse(res_over_10k.is_within_statutory_capacity)


class TestMPEEngineClassIIII(unittest.TestCase):
    """Class IIII (Ordinary Accuracy) MPE boundary tests."""

    def test_class_iiii_band_1_boundaries(self):
        # 0 <= m <= 50 e -> 0.5e
        e_val = 5.0  # 5 kg

        # Exactly 0e
        res_0 = MPEEngine.calculate(AccuracyClass.CLASS_IIII, load=0.0, e=e_val)
        self.assertEqual(res_0.load_in_e, 0.0)
        self.assertEqual(res_0.mpe_in_e, 0.5)
        self.assertEqual(res_0.band_index, 1)

        # Exactly 50e (50 * 5.0 = 250.0 kg) -> must be 0.5e!
        res_50 = MPEEngine.calculate(AccuracyClass.CLASS_IIII, load=250.0, e=e_val)
        self.assertEqual(res_50.load_in_e, 50.0)
        self.assertEqual(res_50.mpe_in_e, 0.5)
        self.assertEqual(res_50.band_index, 1)
        self.assertAlmostEqual(res_50.mpe_absolute, 0.5 * 5.0, places=6)

    def test_class_iiii_band_2_boundaries(self):
        # 50 e < m <= 200 e -> 1.0e
        e_val = 5.0

        # Just over 50e (50.001 * 5.0 = 250.005 kg) -> must step to 1.0e!
        res_just_over_50 = MPEEngine.calculate(AccuracyClass.CLASS_IIII, load=250.005, e=e_val)
        self.assertAlmostEqual(res_just_over_50.load_in_e, 50.001, places=3)
        self.assertEqual(res_just_over_50.mpe_in_e, 1.0)
        self.assertEqual(res_just_over_50.band_index, 2)

        # Exactly 200e (200 * 5.0 = 1000.0 kg) -> must be 1.0e!
        res_200 = MPEEngine.calculate(AccuracyClass.CLASS_IIII, load=1000.0, e=e_val)
        self.assertEqual(res_200.load_in_e, 200.0)
        self.assertEqual(res_200.mpe_in_e, 1.0)
        self.assertEqual(res_200.band_index, 2)

    def test_class_iiii_band_3_boundaries(self):
        # 200 e < m <= 1,000 e -> 1.5e
        e_val = 5.0

        # Just over 200e (200.001 * 5.0 = 1000.005 kg) -> must step to 1.5e!
        res_just_over_200 = MPEEngine.calculate(AccuracyClass.CLASS_IIII, load=1000.005, e=e_val)
        self.assertAlmostEqual(res_just_over_200.load_in_e, 200.001, places=3)
        self.assertEqual(res_just_over_200.mpe_in_e, 1.5)
        self.assertEqual(res_just_over_200.band_index, 3)

        # Exactly 1,000e (1000 * 5.0 = 5000.0 kg) -> 1.5e!
        res_1000 = MPEEngine.calculate(AccuracyClass.CLASS_IIII, load=5000.0, e=e_val)
        self.assertEqual(res_1000.load_in_e, 1000.0)
        self.assertEqual(res_1000.mpe_in_e, 1.5)
        self.assertTrue(res_1000.is_within_statutory_capacity)

        # Over 1,000e
        res_over_1k = MPEEngine.calculate(AccuracyClass.CLASS_IIII, load=5000.005, e=e_val)
        self.assertEqual(res_over_1k.mpe_in_e, 1.5)
        self.assertFalse(res_over_1k.is_within_statutory_capacity)


class TestMPEEngineSubsequentVerification(unittest.TestCase):
    """Tests that subsequent verification MPE is exactly 2 x initial verification MPE."""

    def test_subsequent_verification_multipliers(self):
        # For Class III:
        # Band 1: 0.5e * 2 = 1.0e
        # Band 2: 1.0e * 2 = 2.0e
        # Band 3: 1.5e * 2 = 3.0e
        e = 0.005  # 5 g

        # Band 1: 500e (load = 2.5 kg)
        res_sub_b1 = MPEEngine.calculate(
            accuracy_class="III",
            load=2.5,
            e=e,
            verification_type=VerificationType.SUBSEQUENT,
        )
        self.assertEqual(res_sub_b1.mpe_in_e, 1.0)
        self.assertAlmostEqual(res_sub_b1.mpe_absolute, 1.0 * e, places=6)
        self.assertEqual(res_sub_b1.verification_type, "SUBSEQUENT")

        # Band 2: 1000e (load = 5.0 kg)
        res_sub_b2 = MPEEngine.calculate(
            accuracy_class="III",
            load=5.0,
            e=e,
            verification_type=VerificationType.SUBSEQUENT,
        )
        self.assertEqual(res_sub_b2.mpe_in_e, 2.0)
        self.assertAlmostEqual(res_sub_b2.mpe_absolute, 2.0 * e, places=6)

        # Band 3: 3000e (load = 15.0 kg)
        res_sub_b3 = MPEEngine.calculate(
            accuracy_class="III",
            load=15.0,
            e=e,
            verification_type=VerificationType.SUBSEQUENT,
        )
        self.assertEqual(res_sub_b3.mpe_in_e, 3.0)
        self.assertAlmostEqual(res_sub_b3.mpe_absolute, 3.0 * e, places=6)

    def test_verification_type_aliases(self):
        # Accepts various aliases
        res_in_service = MPEEngine.calculate("III", 2.5, 0.005, verification_type="IN_SERVICE")
        self.assertEqual(res_in_service.mpe_in_e, 1.0)

        res_re_verif = MPEEngine.calculate("III", 2.5, 0.005, verification_type="RE_VERIFICATION")
        self.assertEqual(res_re_verif.mpe_in_e, 1.0)

        res_bool_true = MPEEngine.calculate("III", 2.5, 0.005, verification_type=True)
        self.assertEqual(res_bool_true.mpe_in_e, 1.0)

        res_initial = MPEEngine.calculate("III", 2.5, 0.005, verification_type="INITIAL")
        self.assertEqual(res_initial.mpe_in_e, 0.5)

        res_bool_false = MPEEngine.calculate("III", 2.5, 0.005, verification_type=False)
        self.assertEqual(res_bool_false.mpe_in_e, 0.5)


class TestMPEEngineObservedErrorEvaluation(unittest.TestCase):
    """Tests compliance evaluation: |observed_error| <= MPE and margin computation."""

    def test_pass_zero_error(self):
        # Load 1.0 kg on Class III, e = 0.002 kg -> Band 1, MPE = 0.5e = 0.001 kg
        res = MPEEngine.calculate(
            accuracy_class="III",
            load=1.0,
            e=0.002,
            verification_type="INITIAL",
            observed_error=0.0,
        )
        self.assertTrue(res.passed)
        self.assertFalse(res.fail)
        self.assertAlmostEqual(res.margin, 0.001, places=6)
        self.assertAlmostEqual(res.margin_in_e, 0.5, places=6)

    def test_pass_exact_upper_boundary(self):
        # Observed error is exactly +MPE (+0.001 kg)
        res = MPEEngine.calculate(
            accuracy_class="III",
            load=1.0,
            e=0.002,
            observed_error=0.001,
        )
        self.assertTrue(res.passed)
        self.assertFalse(res.fail)
        self.assertAlmostEqual(res.margin, 0.0, places=9)
        self.assertAlmostEqual(res.margin_in_e, 0.0, places=9)

    def test_pass_exact_lower_boundary(self):
        # Observed error is exactly -MPE (-0.001 kg)
        res = MPEEngine.calculate(
            accuracy_class="III",
            load=1.0,
            e=0.002,
            observed_error=-0.001,
        )
        self.assertTrue(res.passed)
        self.assertFalse(res.fail)
        self.assertAlmostEqual(res.margin, 0.0, places=9)

    def test_fail_just_over_mpe(self):
        # Observed error is +0.001001 kg (exceeds MPE of 0.001 kg by 0.000001 kg)
        res = MPEEngine.calculate(
            accuracy_class="III",
            load=1.0,
            e=0.002,
            observed_error=0.001001,
        )
        self.assertFalse(res.passed)
        self.assertTrue(res.fail)
        self.assertAlmostEqual(res.margin, -0.000001, places=6)
        self.assertLess(res.margin, 0.0)

    def test_fail_just_below_negative_mpe(self):
        # Observed error is -0.001001 kg (exceeds MPE magnitude)
        res = MPEEngine.calculate(
            accuracy_class="III",
            load=1.0,
            e=0.002,
            observed_error=-0.001001,
        )
        self.assertFalse(res.passed)
        self.assertTrue(res.fail)
        self.assertAlmostEqual(res.margin, -0.000001, places=6)

    def test_observed_error_in_e(self):
        # User supplies observed_error_in_e directly (e.g. +0.4e when MPE is 0.5e)
        res = MPEEngine.calculate(
            accuracy_class="III",
            load=1.0,
            e=0.002,
            observed_error_in_e=0.4,
        )
        self.assertTrue(res.passed)
        self.assertAlmostEqual(res.margin_in_e, 0.1, places=4)
        self.assertAlmostEqual(res.margin, 0.0002, places=6)


class TestMPEEngineFloatingPointPrecision(unittest.TestCase):
    """
    Tests exact binary-to-decimal floating point precision without arbitrary tolerance fudge.
    """

    def test_floating_point_representation_boundaries(self):
        # Fractional verification scale intervals that can have binary representation artifacts
        test_e_values = [0.005, 0.002, 0.001, 0.02, 0.05, 0.07]

        for e_val in test_e_values:
            with self.subTest(e=e_val):
                # 500e exactly
                load_500e = 500 * e_val
                res_500 = MPEEngine.calculate(AccuracyClass.CLASS_III, load=load_500e, e=e_val)
                self.assertEqual(res_500.mpe_in_e, 0.5)
                self.assertEqual(res_500.band_index, 1)

                # 2000e exactly
                load_2000e = 2000 * e_val
                res_2000 = MPEEngine.calculate(AccuracyClass.CLASS_III, load=load_2000e, e=e_val)
                self.assertEqual(res_2000.mpe_in_e, 1.0)
                self.assertEqual(res_2000.band_index, 2)

    def test_decimal_inputs(self):
        # Directly passing Decimals
        d_load = Decimal("1.0")
        d_e = Decimal("0.002")
        res = MPEEngine.calculate(AccuracyClass.CLASS_III, load=d_load, e=d_e)
        self.assertEqual(res.mpe_in_e, 0.5)


class TestMPEEngineStructuredDictionaryAndAPI(unittest.TestCase):
    """Tests dictionary serialization and router API compatibility."""

    def test_to_dict_format(self):
        res = MPEEngine.calculate(
            accuracy_class="III",
            load=10.0,
            e=0.005,
            verification_type="INITIAL",
            observed_error=0.004,
        )
        d = res.to_dict()

        # Check required fields
        self.assertEqual(d["load"], 10.0)
        self.assertEqual(d["e"], 0.005)
        self.assertEqual(d["load_in_e"], 2000.0)
        self.assertEqual(d["accuracy_class"], "III")
        self.assertEqual(d["verification_type"], "INITIAL")
        self.assertEqual(d["mpe_in_e"], 1.0)
        self.assertEqual(d["mpe_absolute"], 0.005)
        self.assertIn("applicable_rule", d)
        self.assertIn("source", d)
        self.assertTrue(d["pass"])
        self.assertFalse(d["fail"])
        self.assertAlmostEqual(d["margin"], 0.001, places=6)

    def test_router_api_stateless_calculation(self):
        payload = {
            "accuracy_class": "III",
            "load": 15.0,
            "e": 0.005,
            "verification_type": "INITIAL",
            "observed_error": 0.006,
        }
        res_dict = api_calculate_mpe(payload)
        self.assertEqual(res_dict["accuracy_class"], "III")
        self.assertEqual(res_dict["load_in_e"], 3000.0)
        self.assertEqual(res_dict["mpe_in_e"], 1.5)
        self.assertEqual(res_dict["mpe_absolute"], 0.0075)
        self.assertTrue(res_dict["pass"])  # 0.006 <= 0.0075


class TestMPEEngineErrorHandling(unittest.TestCase):
    """Tests edge cases and input validation errors."""

    def test_zero_e_raises_value_error(self):
        with self.assertRaises(ValueError):
            MPEEngine.calculate("III", 10.0, 0.0)

    def test_negative_e_raises_value_error(self):
        with self.assertRaises(ValueError):
            MPEEngine.calculate("III", 10.0, -0.005)

    def test_invalid_class_raises_value_error(self):
        with self.assertRaises(ValueError):
            MPEEngine.calculate("INVALID_CLASS", 10.0, 0.005)

    def test_negative_load_evaluated_by_magnitude(self):
        # In metrology, error for displacement from zero uses absolute load magnitude
        res = MPEEngine.calculate("III", -1.0, 0.002)
        self.assertEqual(res.load_in_e, 500.0)
        self.assertEqual(res.mpe_in_e, 0.5)


if __name__ == "__main__":
    unittest.main()
