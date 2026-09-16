"""
MetrIQ Regulatory Engine - Instrument Classification Validator Unit Tests
Covers comprehensive statutory validation tests per OIML R 76-1 Table 3 and Indian Legal Metrology Table 1:
- valid Class I
- invalid Class I
- valid Class II
- invalid Class II
- valid Class III
- invalid Class III
- valid Class IIII
- invalid Class IIII
- invalid Min/Max (Min >= Max, negative, zero)
- invalid e (non 1,2,5 mantissa, negative, zero, table gap)
- invalid n (n mismatch, non-integer n, out of bounds)
- multi-interval (progression, auxiliary device prohibition, manual review flagging)
- multi-range (independent representation, manual review flagging)
- boundary values (exact n_min, exact n_max, exact Min = 20e/50e/100e)
- safe non-crashing handling of invalid types
- zero silent rounding
"""

import unittest
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.regulatory import (
    RegulatoryClassificationValidator,
    validate_classification,
    ClassificationValidationResult,
    ClassificationValidationIssue,
)


class TestClassIValidation(unittest.TestCase):
    """Verifies Class I (Special Accuracy) validation."""

    def test_valid_class_i(self):
        # Micro-balance: Max = 220 g, Min = 0.1 g (100e), e = 0.001 g (1 mg), d = 0.0001 g (0.1 mg)
        # n = 220 / 0.001 = 220,000 (>= 50,000)
        spec = {
            "accuracy_class": "I",
            "Max": 220.0,
            "Min": 0.1,
            "e": 0.001,
            "d": 0.0001,
            "calculated_n": 220000,
            "instrument_type": "ANALYTICAL_BALANCE",
            "electronic_status": True,
            "multi_range_status": False,
            "multi_interval_status": False,
            "unit": "g",
        }
        res = validate_classification(spec)
        self.assertTrue(res.valid)
        self.assertEqual(len(res.errors), 0)
        self.assertFalse(res.manual_review_required)
        self.assertEqual(res.instrument_summary["accuracy_class"], "I")

    def test_invalid_class_i_e_below_1mg(self):
        # Class I e must be >= 1 mg (0.001 g)
        spec = {
            "accuracy_class": "I",
            "Max": 50.0,
            "Min": 0.01,
            "e": 0.0005,  # 0.5 mg < 1 mg statutory threshold
            "unit": "g",
        }
        res = validate_classification(spec)
        self.assertFalse(res.valid)
        rule_ids = {e.rule_id for e in res.errors}
        self.assertIn("RULE_CLASS_I_E_MIN", rule_ids)
        err = [e for e in res.errors if e.rule_id == "RULE_CLASS_I_E_MIN"][0]
        self.assertEqual(err.field, "e")
        self.assertIn("0.001 g", err.expected_condition)

    def test_invalid_class_i_n_below_50000(self):
        # Class I requires n >= 50,000. Here Max = 30 g, e = 0.001 g -> n = 30,000 (< 50,000)
        spec = {
            "accuracy_class": "I",
            "Max": 30.0,
            "Min": 0.1,
            "e": 0.001,
            "unit": "g",
        }
        res = validate_classification(spec)
        self.assertFalse(res.valid)
        rule_ids = {e.rule_id for e in res.errors}
        self.assertIn("RULE_CLASS_I_N_MIN", rule_ids)

    def test_invalid_class_i_min_capacity(self):
        # Class I requires Min >= 100e. With e = 0.001 g, Min must be >= 0.1 g.
        spec = {
            "accuracy_class": "I",
            "Max": 200.0,
            "Min": 0.05,  # 50e < 100e
            "e": 0.001,
            "unit": "g",
        }
        res = validate_classification(spec)
        self.assertFalse(res.valid)
        rule_ids = {e.rule_id for e in res.errors}
        self.assertIn("RULE_CLASS_I_MIN_CAPACITY", rule_ids)


class TestClassIIValidation(unittest.TestCase):
    """Verifies Class II (High Accuracy) validation."""

    def test_valid_class_ii_band_a(self):
        # Band A: 0.001 g <= e <= 0.05 g: Max = 500 g, e = 0.01 g, Min = 0.2 g (20e), n = 50,000
        spec = {
            "accuracy_class": "II",
            "Max": 500.0,
            "Min": 0.2,
            "e": 0.01,
            "d": 0.001,
            "calculated_n": 50000,
            "unit": "g",
        }
        res = validate_classification(spec)
        self.assertTrue(res.valid)
        self.assertEqual(len(res.errors), 0)

    def test_valid_class_ii_band_b(self):
        # Band B: e >= 0.1 g: Max = 6000 g (6 kg), e = 0.1 g (100 mg), Min = 5 g (50e), n = 60,000
        spec = {
            "accuracy_class": "II",
            "Max": 6000.0,
            "Min": 5.0,
            "e": 0.1,
            "d": 0.01,
            "unit": "g",
        }
        res = validate_classification(spec)
        self.assertTrue(res.valid)

    def test_invalid_class_ii_n_out_of_bounds(self):
        # Band B requires n in [5000, 100000].
        # 1. n too low: Max = 200 g, e = 0.1 g -> n = 2000 (< 5000)
        spec_low = {
            "accuracy_class": "II",
            "Max": 200.0,
            "Min": 5.0,
            "e": 0.1,
            "unit": "g",
        }
        res_low = validate_classification(spec_low)
        self.assertFalse(res_low.valid)
        self.assertIn("RULE_CLASS_II_N_MIN", {e.rule_id for e in res_low.errors})

        # 2. n too high: Max = 15,000 g, e = 0.1 g -> n = 150,000 (> 100,000)
        spec_high = {
            "accuracy_class": "II",
            "Max": 15000.0,
            "Min": 5.0,
            "e": 0.1,
            "unit": "g",
        }
        res_high = validate_classification(spec_high)
        self.assertFalse(res_high.valid)
        self.assertIn("RULE_CLASS_II_N_MAX", {e.rule_id for e in res_high.errors})

    def test_invalid_class_ii_min_capacity(self):
        # Band B requires Min >= 50e. With e = 0.1 g, Min must be >= 5 g.
        spec = {
            "accuracy_class": "II",
            "Max": 6000.0,
            "Min": 2.0,  # 20e < 50e
            "e": 0.1,
            "unit": "g",
        }
        res = validate_classification(spec)
        self.assertFalse(res.valid)
        self.assertIn("RULE_CLASS_II_MIN_CAPACITY", {e.rule_id for e in res.errors})


class TestClassIIIValidation(unittest.TestCase):
    """Verifies Class III (Medium Accuracy) validation."""

    def test_valid_class_iii_retail_scale(self):
        # Retail counter scale: Max = 15 kg, Min = 0.1 kg (20e), e = 0.005 kg (5 g), d = 0.005 kg, n = 3,000
        spec = {
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "calculated_n": 3000,
            "instrument_type": "RETAIL_PRICE_COMPUTING",
            "unit": "kg",
        }
        res = validate_classification(spec)
        self.assertTrue(res.valid)
        self.assertEqual(len(res.errors), 0)

    def test_invalid_class_iii_auxiliary_device(self):
        # Class III strictly disallows auxiliary indicating devices (d < e)
        spec = {
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.001,  # d < e on Class III
            "unit": "kg",
        }
        res = validate_classification(spec)
        self.assertFalse(res.valid)
        self.assertIn("RULE_AUXILIARY_DEVICE_PROHIBITED", {e.rule_id for e in res.errors})
        err = [e for e in res.errors if e.rule_id == "RULE_AUXILIARY_DEVICE_PROHIBITED"][0]
        self.assertIn("PROHIBITED", err.message)

    def test_invalid_class_iii_n_out_of_bounds(self):
        # Class III requires n in [500, 10000] for e >= 5 g.
        # Max = 100 kg, e = 0.005 kg (5 g) -> n = 20,000 (> 10,000)
        spec = {
            "accuracy_class": "III",
            "Max": 100.0,
            "Min": 0.1,
            "e": 0.005,
            "unit": "kg",
        }
        res = validate_classification(spec)
        self.assertFalse(res.valid)
        self.assertIn("RULE_CLASS_III_N_MAX", {e.rule_id for e in res.errors})

    def test_invalid_class_iii_e_below_100mg(self):
        # Class III verification scale interval cannot be below 0.1 g (100 mg)
        spec = {
            "accuracy_class": "III",
            "Max": 500.0,
            "Min": 1.0,
            "e": 0.05,  # 0.05 g < 0.1 g
            "unit": "g",
        }
        res = validate_classification(spec)
        self.assertFalse(res.valid)
        self.assertIn("RULE_CLASS_III_E_MIN", {e.rule_id for e in res.errors})


class TestClassIIIIValidation(unittest.TestCase):
    """Verifies Class IIII (Ordinary Accuracy) validation."""

    def test_valid_class_iiii(self):
        # Heavy crane scale: Max = 5000 kg, Min = 50 kg (10e), e = 5 kg, d = 5 kg, n = 1,000
        spec = {
            "accuracy_class": "IIII",
            "Max": 5000.0,
            "Min": 50.0,
            "e": 5.0,
            "d": 5.0,
            "calculated_n": 1000,
            "instrument_type": "CRANE_SCALE",
            "unit": "kg",
        }
        res = validate_classification(spec)
        self.assertTrue(res.valid)

    def test_invalid_class_iiii_e_below_5g(self):
        # Class IIII e must be >= 5 g
        spec = {
            "accuracy_class": "IIII",
            "Max": 200.0,
            "Min": 2.0,
            "e": 2.0,  # 2 g < 5 g
            "unit": "g",
        }
        res = validate_classification(spec)
        self.assertFalse(res.valid)
        self.assertIn("RULE_CLASS_IIII_E_MIN", {e.rule_id for e in res.errors})

    def test_invalid_class_iiii_n_above_1000(self):
        # Class IIII maximum n is 1,000. If Max = 15,000 kg, e = 5 kg -> n = 3,000
        spec = {
            "accuracy_class": "IIII",
            "Max": 15000.0,
            "Min": 50.0,
            "e": 5.0,
            "unit": "kg",
        }
        res = validate_classification(spec)
        self.assertFalse(res.valid)
        self.assertIn("RULE_CLASS_IIII_N_MAX", {e.rule_id for e in res.errors})


class TestCapacityAndIntervalIntegrity(unittest.TestCase):
    """Verifies relationships between Max, Min, e, d, and n."""

    def test_min_exceeds_max(self):
        spec = {
            "accuracy_class": "III",
            "Max": 10.0,
            "Min": 15.0,  # Min > Max
            "e": 0.005,
            "unit": "kg",
        }
        res = validate_classification(spec)
        self.assertFalse(res.valid)
        self.assertIn("RULE_MIN_EXCEEDS_MAX", {e.rule_id for e in res.errors})

    def test_zero_or_negative_capacity(self):
        spec_zero = {
            "accuracy_class": "III",
            "Max": 0.0,
            "Min": 0.0,
            "e": 0.005,
            "unit": "kg",
        }
        res = validate_classification(spec_zero)
        self.assertFalse(res.valid)
        self.assertIn("RULE_MAX_NON_POSITIVE", {e.rule_id for e in res.errors})

        spec_neg = {
            "accuracy_class": "III",
            "Max": -15.0,
            "Min": -1.0,
            "e": 0.005,
            "unit": "kg",
        }
        res_neg = validate_classification(spec_neg)
        self.assertFalse(res_neg.valid)
        self.assertIn("RULE_MAX_NON_POSITIVE", {e.rule_id for e in res_neg.errors})
        self.assertIn("RULE_MIN_NEGATIVE", {e.rule_id for e in res_neg.errors})

    def test_invalid_e_form(self):
        # e = 3 g is invalid form (not 1, 2, 5 * 10^k)
        spec = {
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.003,
            "unit": "kg",
        }
        res = validate_classification(spec)
        self.assertFalse(res.valid)
        self.assertIn("RULE_SCALE_INTERVAL_FORM", {e.rule_id for e in res.errors})

    def test_d_exceeds_e(self):
        # d cannot exceed e
        spec = {
            "accuracy_class": "II",
            "Max": 1000.0,
            "Min": 5.0,
            "e": 0.1,
            "d": 0.2,  # d > e
            "unit": "g",
        }
        res = validate_classification(spec)
        self.assertFalse(res.valid)
        self.assertIn("RULE_D_EXCEEDS_E", {e.rule_id for e in res.errors})

    def test_n_calculation_mismatch(self):
        # Max = 15 kg, e = 0.005 kg -> exact n = 3,000. If user sends calculated_n = 3,500
        spec = {
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "calculated_n": 3500,
            "unit": "kg",
        }
        res = validate_classification(spec)
        self.assertFalse(res.valid)
        self.assertIn("RULE_N_CALCULATION_MISMATCH", {e.rule_id for e in res.errors})

    def test_no_silent_rounding_on_n(self):
        # Max = 10 kg, e = 0.007 kg (invalid form, and 10/0.007 = 1428.5714 fractional n)
        spec = {
            "accuracy_class": "III",
            "Max": 10.0,
            "Min": 0.2,
            "e": 0.007,
            "unit": "kg",
        }
        res = validate_classification(spec)
        self.assertFalse(res.valid)
        self.assertIn("RULE_N_NON_INTEGER", {e.rule_id for e in res.errors})


class TestMultiIntervalAndRangeValidation(unittest.TestCase):
    """Verifies multi-interval and multi-range validation."""

    def test_valid_multi_interval(self):
        # Dual-interval scale:
        # Range 1: Max 6 kg, Min 0.04 kg, e = 2 g (0.002 kg) -> n1 = 3000
        # Range 2: Max 15 kg, Min 0.04 kg, e = 5 g (0.005 kg) -> n2 = 3000
        spec = {
            "accuracy_class": "III",
            "multi_interval_status": True,
            "unit": "kg",
            "partial_ranges": [
                {"range_index": 1, "Max": 6.0, "Min": 0.04, "e": 0.002, "d": 0.002},
                {"range_index": 2, "Max": 15.0, "Min": 0.04, "e": 0.005, "d": 0.005},
            ],
        }
        res = validate_classification(spec)
        self.assertTrue(res.valid)
        # Must require manual review for multi-interval physical changeover verification!
        self.assertTrue(res.manual_review_required)
        self.assertGreater(len(res.manual_review_reasons), 0)
        self.assertEqual(len(res.ranges_evaluated), 2)

    def test_invalid_multi_interval_e_order(self):
        # e2 <= e1 is illegal
        spec = {
            "accuracy_class": "III",
            "multi_interval_status": True,
            "unit": "kg",
            "partial_ranges": [
                {"range_index": 1, "Max": 6.0, "Min": 0.04, "e": 0.005},
                {"range_index": 2, "Max": 15.0, "Min": 0.04, "e": 0.002},  # e2 < e1!
            ],
        }
        res = validate_classification(spec)
        self.assertFalse(res.valid)
        self.assertIn("RULE_MULTI_INTERVAL_E_ORDER", {e.rule_id for e in res.errors})

    def test_valid_multi_range(self):
        # Multi-range platform:
        # Range 1: Max 30 kg, Min 0.2 kg, e = 10 g (0.01 kg) -> n = 3000
        # Range 2: Max 60 kg, Min 0.4 kg, e = 20 g (0.02 kg) -> n = 3000
        spec = {
            "accuracy_class": "III",
            "multi_range_status": True,
            "unit": "kg",
            "ranges": [
                {"range_index": 1, "Max": 30.0, "Min": 0.2, "e": 0.01},
                {"range_index": 2, "Max": 60.0, "Min": 0.4, "e": 0.02},
            ],
        }
        res = validate_classification(spec)
        self.assertTrue(res.valid)
        self.assertTrue(res.manual_review_required)
        self.assertEqual(len(res.ranges_evaluated), 2)


class TestBoundaryValues(unittest.TestCase):
    """Verifies statutory boundary conditions (exact n_min, n_max, and Min)."""

    def test_class_i_exact_n_min_boundary(self):
        # Class I: n exactly 50,000 (Max = 50 g, e = 0.001 g, Min = 0.1 g = 100e)
        spec = {
            "accuracy_class": "I",
            "Max": 50.0,
            "Min": 0.1,
            "e": 0.001,
            "unit": "g",
        }
        res = validate_classification(spec)
        self.assertTrue(res.valid)

    def test_class_ii_exact_n_bounds(self):
        # Band A: n exactly 100 (Max = 1 g, e = 0.01 g, Min = 0.2 g = 20e)
        spec_min = {
            "accuracy_class": "II",
            "Max": 1.0,
            "Min": 0.2,
            "e": 0.01,
            "unit": "g",
        }
        res_min = validate_classification(spec_min)
        self.assertTrue(res_min.valid)

        # Band B: n exactly 100,000 (Max = 10,000 g, e = 0.1 g, Min = 5 g = 50e)
        spec_max = {
            "accuracy_class": "II",
            "Max": 10000.0,
            "Min": 5.0,
            "e": 0.1,
            "unit": "g",
        }
        res_max = validate_classification(spec_max)
        self.assertTrue(res_max.valid)

    def test_class_iii_exact_n_bounds(self):
        # Band B: n exactly 500 (Max = 2.5 kg, e = 0.005 kg = 5 g, Min = 0.1 kg = 20e)
        spec_min = {
            "accuracy_class": "III",
            "Max": 2.5,
            "Min": 0.1,
            "e": 0.005,
            "unit": "kg",
        }
        res_min = validate_classification(spec_min)
        self.assertTrue(res_min.valid)

        # Band B: n exactly 10,000 (Max = 50 kg, e = 0.005 kg = 5 g, Min = 0.1 kg = 20e)
        spec_max = {
            "accuracy_class": "III",
            "Max": 50.0,
            "Min": 0.1,
            "e": 0.005,
            "unit": "kg",
        }
        res_max = validate_classification(spec_max)
        self.assertTrue(res_max.valid)


class TestSafeHandlingOfInvalidTypes(unittest.TestCase):
    """Verifies that non-numeric or malformed data produces structured errors rather than unhandled crashes."""

    def test_string_instead_of_numbers(self):
        spec = {
            "accuracy_class": "III",
            "Max": "one hundred",
            "Min": 0.1,
            "e": 0.005,
            "unit": "kg",
        }
        res = validate_classification(spec)
        self.assertFalse(res.valid)
        self.assertIn("RULE_MAX_INVALID", {e.rule_id for e in res.errors})

    def test_missing_accuracy_class(self):
        spec = {
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "unit": "kg",
        }
        res = validate_classification(spec)
        self.assertFalse(res.valid)
        self.assertIn("RULE_ACCURACY_CLASS_MISSING", {e.rule_id for e in res.errors})

    def test_invalid_accuracy_class_name(self):
        spec = {
            "accuracy_class": "V_SUPER_SPECIAL",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "unit": "kg",
        }
        res = validate_classification(spec)
        self.assertFalse(res.valid)
        self.assertIn("RULE_ACCURACY_CLASS_INVALID", {e.rule_id for e in res.errors})


if __name__ == "__main__":
    unittest.main()
