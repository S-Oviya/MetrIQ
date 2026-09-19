"""
Unit tests for MetrIQ P4 Regulatory MPE Adapter (backend/app/calculations/mpe.py).
Verifies that P4 delegates all statutory MPE lookups to P2 Regulatory Engine.
"""

import unittest
from app.calculations.mpe import MPEAdapter, RegulatoryMPELimit, MPEEvaluationResult
from app.regulatory.models import AccuracyClass
from app.regulatory.mpe_engine import VerificationType


class TestP4MPEAdapter(unittest.TestCase):

    def test_class_iii_initial_mpe_bands(self):
        """Verify Class III initial verification MPE bands from P2."""
        # Band 1: 0 <= m <= 500e -> MPE = +/- 0.5e
        mpe_1 = MPEAdapter.get_mpe(load=200.0, accuracy_class="CLASS_III", e=1.0, verification_type="INITIAL")
        self.assertEqual(mpe_1.mpe_in_e, 0.5)
        self.assertEqual(mpe_1.mpe_absolute, 0.5)
        self.assertEqual(mpe_1.lower_limit, -0.5)
        self.assertEqual(mpe_1.upper_limit, 0.5)

        # Band 2: 500e < m <= 2000e -> MPE = +/- 1.0e
        mpe_2 = MPEAdapter.get_mpe(load=1000.0, accuracy_class="CLASS_III", e=1.0, verification_type="INITIAL")
        self.assertEqual(mpe_2.mpe_in_e, 1.0)
        self.assertEqual(mpe_2.mpe_absolute, 1.0)

        # Band 3: 2000e < m <= 10000e -> MPE = +/- 1.5e
        mpe_3 = MPEAdapter.get_mpe(load=5000.0, accuracy_class="CLASS_III", e=1.0, verification_type="INITIAL")
        self.assertEqual(mpe_3.mpe_in_e, 1.5)
        self.assertEqual(mpe_3.mpe_absolute, 1.5)

    def test_subsequent_verification_doubles_mpe(self):
        """Verify subsequent / in-service verification uses 2x multiplier from P2."""
        init = MPEAdapter.get_mpe(load=400.0, accuracy_class="CLASS_III", e=1.0, verification_type="INITIAL")
        subseq = MPEAdapter.get_mpe(load=400.0, accuracy_class="CLASS_III", e=1.0, verification_type="SUBSEQUENT")
        self.assertEqual(init.mpe_in_e, 0.5)
        self.assertEqual(subseq.mpe_in_e, 1.0)
        self.assertEqual(subseq.mpe_absolute, 1.0)

    def test_all_accuracy_classes(self):
        """Verify MPE resolution across Class I, II, III, and IIII."""
        for acc_class in ["CLASS_I", "CLASS_II", "CLASS_III", "CLASS_IIII"]:
            res = MPEAdapter.get_mpe(load=10.0, accuracy_class=acc_class, e=0.1)
            self.assertIsInstance(res, RegulatoryMPELimit)
            self.assertGreater(res.mpe_absolute, 0.0)

    def test_multi_interval_partial_ranges(self):
        """Verify effective e selection for multi-interval instruments."""
        partial_ranges = [
            {"range_index": 1, "max_capacity": 6.0, "min_capacity": 0.04, "e": 0.002},
            {"range_index": 2, "max_capacity": 15.0, "min_capacity": 0.1, "e": 0.005},
        ]
        # In range 1: load 3kg <= 6kg -> e = 0.002
        res_r1 = MPEAdapter.get_mpe(load=3.0, accuracy_class="CLASS_III", e=0.002, partial_ranges=partial_ranges)
        self.assertEqual(res_r1.e, 0.002)

        # In range 2: load 10kg > 6kg -> e = 0.005
        res_r2 = MPEAdapter.get_mpe(load=10.0, accuracy_class="CLASS_III", e=0.002, partial_ranges=partial_ranges)
        self.assertEqual(res_r2.e, 0.005)

    def test_evaluate_error_pass_and_fail(self):
        """Verify error evaluation with pass/fail and margin determination."""
        # Class III at 200kg (e=1kg): MPE = +/-0.5kg
        pass_res = MPEAdapter.evaluate_error(
            observed_error=0.3, load=200.0, accuracy_class="CLASS_III", e=1.0
        )
        self.assertTrue(pass_res.passed)
        self.assertAlmostEqual(pass_res.margin, 0.2, places=6)

        fail_res = MPEAdapter.evaluate_error(
            observed_error=0.8, load=200.0, accuracy_class="CLASS_III", e=1.0
        )
        self.assertFalse(fail_res.passed)
        self.assertLess(fail_res.margin, 0.0)

    def test_statutory_zero_creep_and_tare_limits(self):
        """Verify statutory limits derived from OIML standards."""
        e = 0.005
        # Zero drift limit: 0.5e
        self.assertEqual(MPEAdapter.get_zero_drift_limit(e), 0.0025)

        # Creep limits: 0.5e total, 0.2e transient
        creep_lim = MPEAdapter.get_creep_limits(e)
        self.assertEqual(creep_lim["total_creep_limit_e"], 0.5)
        self.assertEqual(creep_lim["transient_creep_limit_e"], 0.2)
        self.assertEqual(creep_lim["total_creep_limit"], 0.0025)
        self.assertEqual(creep_lim["transient_creep_limit"], 0.001)

        # Tare setting limit: 0.25e
        self.assertEqual(MPEAdapter.get_tare_setting_limit(e), 0.00125)


if __name__ == "__main__":
    unittest.main()
