"""
MetrIQ Unit Tests — Person 4 NAWI Calculators
=============================================
Tests all remaining specialized calculators:
1. EccentricityCalculator (Clause A.4.7)
2. RepeatabilityCalculator (Clause A.4.10)
3. ZeroReturnCalculator (Clause 4.1.2.2 & A.4.4.2)
4. CreepCalculator (Clause 4.1.2.1 & A.4.4.1)
5. DiscriminationCalculator (Clause 3.8 & A.4.4.3)
6. TareCalculator (Clause 4.6 & A.4.6)
7. TemperatureCalculator (Clause 3.9.2.2 & A.5.3)
8. ExaminationCalculator (Clause 3.9, 4, 5.5, 7.1)
"""

import unittest
from app.calculations.models import ChecklistItem, ChecklistStatus, Verdict
from app.calculations.eccentricity import EccentricityCalculator
from app.calculations.repeatability import RepeatabilityCalculator
from app.calculations.zero_return import ZeroReturnCalculator
from app.calculations.creep import CreepCalculator
from app.calculations.discrimination import DiscriminationCalculator
from app.calculations.tare import TareCalculator
from app.calculations.temperature import TemperatureCalculator
from app.calculations.examination import ExaminationCalculator


class TestP4Calculators(unittest.TestCase):

    def setUp(self):
        self.accuracy_class = "CLASS_III"
        self.e = 0.005  # 5g
        self.d = 0.005
        self.unit = "kg"

    # =========================================================================
    # 1. Eccentricity Tests (OIML R 76-1 Clause A.4.7)
    # =========================================================================

    def test_eccentricity_pass(self):
        """Standard platter 5 positions within MPE."""
        # 5kg = 1000e (Band 2: MPE = 1e = 0.005kg)
        obs = [
            {"applied_load": 5.0, "indicated_value": 5.000, "position": "CENTER"},
            {"applied_load": 5.0, "indicated_value": 5.002, "position": "FRONT_LEFT"},
            {"applied_load": 5.0, "indicated_value": 5.001, "position": "BACK_LEFT"},
            {"applied_load": 5.0, "indicated_value": 4.999, "position": "BACK_RIGHT"},
            {"applied_load": 5.0, "indicated_value": 5.000, "position": "FRONT_RIGHT"},
        ]
        res = EccentricityCalculator.evaluate(
            observations=obs,
            accuracy_class=self.accuracy_class,
            e=self.e,
            unit=self.unit,
        )
        self.assertEqual(res.verdict, Verdict.PASS)
        self.assertEqual(len(res.positions), 5)
        self.assertAlmostEqual(res.max_error, 0.002, places=6)
        self.assertEqual(res.worst_position, "FRONT_LEFT")
        self.assertAlmostEqual(res.max_position_difference, 0.003, places=6)

    def test_eccentricity_fail(self):
        """Corner error exceeding MPE (e.g. 0.008kg > 0.005kg) fails test."""
        obs = [
            {"applied_load": 5.0, "indicated_value": 5.000, "position": "CENTER"},
            {"applied_load": 5.0, "indicated_value": 5.008, "position": "FRONT_LEFT"},
        ]
        res = EccentricityCalculator.evaluate(
            observations=obs,
            accuracy_class=self.accuracy_class,
            e=self.e,
            unit=self.unit,
        )
        self.assertEqual(res.verdict, Verdict.FAIL)

    # =========================================================================
    # 2. Repeatability Tests (OIML R 76-1 Clause A.4.10)
    # =========================================================================

    def test_repeatability_pass(self):
        """Repeatability spread within MPE for 10 weighings."""
        # 10kg = 2000e (Band 2: MPE = 1.0e = 0.005kg)
        indications = [10.000, 10.001, 10.000, 10.002, 10.001, 10.000, 10.001, 10.002, 10.000, 10.001]
        series_res = RepeatabilityCalculator.evaluate_series(
            load=10.0,
            indications=indications,
            accuracy_class=self.accuracy_class,
            e=self.e,
            unit=self.unit,
        )
        self.assertTrue(series_res.passed)
        self.assertAlmostEqual(series_res.range_span, 0.002, places=6)
        self.assertLessEqual(series_res.range_span, series_res.mpe_limit.mpe_absolute)

    def test_repeatability_fail(self):
        """Spread exceeding MPE fails."""
        indications = [10.000, 10.007, 10.001]  # span = 0.007 > 0.005
        series_res = RepeatabilityCalculator.evaluate_series(
            load=10.0,
            indications=indications,
            accuracy_class=self.accuracy_class,
            e=self.e,
            unit=self.unit,
        )
        self.assertFalse(series_res.passed)

    # =========================================================================
    # 3. Zero Return Tests (OIML R 76-1 Clause 4.1.2.2)
    # =========================================================================

    def test_zero_return_pass_and_fail(self):
        """Zero drift <= 0.5e passes; > 0.5e fails."""
        # e = 0.005 -> 0.5e = 0.0025kg
        pass_res = ZeroReturnCalculator.evaluate(
            initial_zero=0.000,
            returned_zero=0.001,
            e=self.e,
            unit=self.unit,
        )
        self.assertEqual(pass_res.verdict, Verdict.PASS)
        self.assertAlmostEqual(pass_res.zero_drift, 0.001, places=6)

        fail_res = ZeroReturnCalculator.evaluate(
            initial_zero=0.000,
            returned_zero=0.004,
            e=self.e,
            unit=self.unit,
        )
        self.assertEqual(fail_res.verdict, Verdict.FAIL)

    # =========================================================================
    # 4. Creep Tests (OIML R 76-1 Clause 4.1.2.1)
    # =========================================================================

    def test_creep_pass(self):
        """Creep within total (0.5e) and transient (0.2e) limits."""
        # e = 0.005 -> total <= 0.0025kg, transient <= 0.001kg
        time_obs = [
            {"time_seconds": 5, "indicated_value": 15.000},
            {"time_seconds": 300, "indicated_value": 15.0005},
            {"time_seconds": 900, "indicated_value": 15.001},
            {"time_seconds": 1800, "indicated_value": 15.0015},
        ]
        res = CreepCalculator.evaluate(
            load=15.0,
            time_observations=time_obs,
            accuracy_class=self.accuracy_class,
            e=self.e,
            unit=self.unit,
        )
        self.assertEqual(res.verdict, Verdict.PASS)
        self.assertAlmostEqual(res.total_creep, 0.0015, places=6)
        self.assertTrue(res.total_creep_passed)
        self.assertTrue(res.transient_creep_passed)

    # =========================================================================
    # 5. Discrimination Tests (OIML R 76-1 Clause 3.8)
    # =========================================================================

    def test_discrimination_pass(self):
        """Adding 1.4d produces indication increase of at least 1d."""
        res = DiscriminationCalculator.evaluate_point(
            load=10.0,
            initial_indication=10.000,
            extra_load=0.007,
            new_indication=10.005,
            d=self.d,
            unit=self.unit,
        )
        self.assertTrue(res.passed)
        self.assertEqual(res.indication_change, 0.005)

    def test_discrimination_fail(self):
        """No change in indication fails discrimination."""
        res = DiscriminationCalculator.evaluate_point(
            load=10.0,
            initial_indication=10.000,
            extra_load=0.007,
            new_indication=10.000,
            d=self.d,
            unit=self.unit,
        )
        self.assertFalse(res.passed)

    # =========================================================================
    # 6. Tare Tests (OIML R 76-1 Clause 4.6)
    # =========================================================================

    def test_tare_setting_and_net_weighing(self):
        """Tare setting within 0.25e and net weighing within net MPE."""
        # Tare load 2kg. Limit = 0.25 * 0.005 = 0.00125kg
        setting_obs = {"tare_load": 2.0, "indicated_value": 0.000}
        net_obs = [
            {"applied_load": 1.0, "indicated_value": 1.000},
            {"applied_load": 5.0, "indicated_value": 5.001},
        ]
        res = TareCalculator.evaluate_run(
            tare_load=2.0,
            tare_setting_observation=setting_obs,
            net_observations=net_obs,
            accuracy_class=self.accuracy_class,
            e=self.e,
            unit=self.unit,
        )
        self.assertEqual(res.verdict, Verdict.PASS)
        self.assertTrue(res.tare_setting.passed)
        self.assertEqual(len(res.net_points), 2)

    # =========================================================================
    # 7. Temperature Tests (OIML R 76-1 Clause 3.9.2.2)
    # =========================================================================

    def test_temperature_test(self):
        """Zero drift rate <= 0.2e / °C across chamber temperatures."""
        obs = [
            {"temperature_c": 20.0, "applied_load": 0.0, "indicated_value": 0.000},
            {"temperature_c": 20.0, "applied_load": 5.0, "indicated_value": 5.001},
            {"temperature_c": 40.0, "applied_load": 0.0, "indicated_value": 0.001},
            {"temperature_c": 40.0, "applied_load": 5.0, "indicated_value": 5.0015},
        ]
        res = TemperatureCalculator.evaluate(
            observations=obs,
            accuracy_class=self.accuracy_class,
            e=self.e,
            unit=self.unit,
        )
        self.assertEqual(res.verdict, Verdict.PASS)
        self.assertEqual(len(res.zero_drift_evaluations), 1)

    # =========================================================================
    # 8. Examination Tests (OIML R 76-1 Clause 3.9, 4, 5.5, 7.1)
    # =========================================================================

    def test_construction_examination_pass(self):
        """Compliant construction checklist yields PASS."""
        items = [
            ChecklistItem(item_id="CONST-01", title="Plate", clause="7.1", status=ChecklistStatus.COMPLIANT),
            ChecklistItem(item_id="CONST-02", title="Level", clause="3.9.1.1", status=ChecklistStatus.COMPLIANT),
        ]
        res = ExaminationCalculator.evaluate_construction(items)
        self.assertEqual(res.verdict, Verdict.PASS)

    def test_software_examination_version_mismatch_fails(self):
        """Mismatched software version triggers FAIL."""
        items = [
            ChecklistItem(item_id="SOFT-01", title="Software ID", clause="5.5", status=ChecklistStatus.COMPLIANT),
        ]
        res = ExaminationCalculator.evaluate_software(
            checklist_items=items,
            expected_version="v2.1.0",
            observed_version="v2.0.9",
        )
        self.assertEqual(res.verdict, Verdict.FAIL)
        self.assertFalse(res.software_version_match)


if __name__ == "__main__":
    unittest.main()
