"""
Unit tests for MetrIQ P4 Weighing Performance Test (backend/app/calculations/weighing.py).
Verifies single-point, multi-point, turning point, and hysteresis calculations.
"""

import unittest
from app.calculations.models import Verdict
from app.calculations.weighing import WeighingPerformanceCalculator


class TestP4Weighing(unittest.TestCase):

    def setUp(self):
        self.accuracy_class = "CLASS_III"
        self.e = 0.005  # 5g
        self.unit = "kg"

    def test_single_point_exact_indication(self):
        """Standard indication with zero error."""
        res = WeighingPerformanceCalculator.calculate_single_point(
            load=10.0,
            indicated_value=10.0,
            accuracy_class=self.accuracy_class,
            e=self.e,
            unit=self.unit,
        )
        self.assertTrue(res.passed)
        self.assertEqual(res.raw_error, 0.0)
        self.assertEqual(res.corrected_error, 0.0)
        self.assertEqual(res.margin, res.mpe_limit.mpe_absolute)

    def test_single_point_turning_point_interpolation(self):
        """Turning point: P = I + 0.5e - delta_L."""
        # e = 0.005. Let I = 10.000, delta_L = 0.002.
        # P = 10.000 + 0.0025 - 0.002 = 10.0005.
        # Load = 10.000 -> Error = +0.0005
        res = WeighingPerformanceCalculator.calculate_single_point(
            load=10.0,
            indicated_value=10.0,
            turning_point_delta_l=0.002,
            accuracy_class=self.accuracy_class,
            e=self.e,
            unit=self.unit,
        )
        self.assertTrue(res.passed)
        self.assertAlmostEqual(res.true_indication, 10.0005, places=6)
        self.assertAlmostEqual(res.corrected_error, 0.0005, places=6)

    def test_single_point_exceeding_mpe_fails(self):
        """Load 2kg = 400e (Band 1, MPE = 0.5e = 0.0025kg). Error = 0.005kg -> FAIL."""
        res = WeighingPerformanceCalculator.calculate_single_point(
            load=2.0,
            indicated_value=2.005,
            accuracy_class=self.accuracy_class,
            e=self.e,
            unit=self.unit,
        )
        self.assertFalse(res.passed)
        self.assertAlmostEqual(res.corrected_error, 0.005, places=6)
        self.assertLess(res.margin, 0.0)

    def test_multi_point_ascending_and_descending_run(self):
        """Full ascending and descending run with hysteresis."""
        observations = [
            {"step_number": 1, "applied_load": 0.0, "indicated_value": 0.0, "direction": "INCREASING"},
            {"step_number": 2, "applied_load": 2.0, "indicated_value": 2.001, "direction": "INCREASING"},
            {"step_number": 3, "applied_load": 5.0, "indicated_value": 5.002, "direction": "INCREASING"},
            {"step_number": 4, "applied_load": 15.0, "indicated_value": 15.003, "direction": "INCREASING"},
            {"step_number": 5, "applied_load": 5.0, "indicated_value": 5.001, "direction": "DECREASING"},
            {"step_number": 6, "applied_load": 2.0, "indicated_value": 2.000, "direction": "DECREASING"},
            {"step_number": 7, "applied_load": 0.0, "indicated_value": 0.0, "direction": "DECREASING"},
        ]
        run_res = WeighingPerformanceCalculator.evaluate_run(
            observations=observations,
            accuracy_class=self.accuracy_class,
            e=self.e,
            unit=self.unit,
        )
        self.assertEqual(run_res.verdict, Verdict.PASS)
        self.assertEqual(len(run_res.points), 7)
        self.assertIsNotNone(run_res.max_hysteresis)
        # Hysteresis at 5kg: |0.002 - 0.001| = 0.001kg
        self.assertAlmostEqual(run_res.max_hysteresis, 0.001, places=6)

    def test_invalid_parameters_raise_error(self):
        """Negative load or negative e raises ValueError."""
        with self.assertRaises(ValueError):
            WeighingPerformanceCalculator.calculate_single_point(
                load=-5.0, indicated_value=0.0, accuracy_class=self.accuracy_class, e=self.e
            )
        with self.assertRaises(ValueError):
            WeighingPerformanceCalculator.calculate_single_point(
                load=5.0, indicated_value=5.0, accuracy_class=self.accuracy_class, e=-0.01
            )


if __name__ == "__main__":
    unittest.main()
