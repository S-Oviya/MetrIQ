"""
MetrIQ Comprehensive Regulatory Engine QA Pipeline Test Suite
=============================================================
Author: Person 2 - Regulatory Engineer
Target: MetrIQ Regulatory Engine (OIML R 76 / Indian Legal Metrology)

This test suite performs final end-to-end QA validation across the complete
regulatory compliance pipeline:
    Instrument Specification
    -> Classification Validation
    -> n Calculation
    -> MPE Calculation
    -> Test Applicability Evaluation
    -> Test Load Generation
    -> Final Executable Test Plan

Systematically verifies all 20 mandatory QA scenarios:
 1. Class I instrument (analytical precision balance)
 2. Class II instrument (high accuracy laboratory scale)
 3. Class III instrument (medium accuracy commercial scale)
 4. Class IIII instrument (ordinary accuracy heavy industrial scale)
 5. Electronic instrument (disturbance, creep, warm-up applicability)
 6. Mechanical instrument (isolation from electronic tests)
 7. Digital indication (digital discrimination with 1.4d additional load)
 8. Analog indication (analog discrimination with 0.7d displacement)
 9. Zero-setting instrument (zero-setting accuracy test criteria +/-0.25e)
10. Tare instrument (tare accuracy and net weighing evaluation)
11. Non-self-indicating instrument (sensitivity pointer displacement test)
12. Multi-range instrument (multi-range boundary validations and load points)
13. Multi-interval instrument (safe partial plan with manual review flag)
14. Invalid e (non-1,2,5 step sequence or out-of-bounds rejection)
15. Invalid Min/Max (Min > Max, non-positive capacity rejection)
16. Invalid n (n < n_min or n > n_max statutory violations)
17. MPE boundary values (exact Decimal boundary transitions 500e, 2000e, 10000e)
18. Subsequent verification (exact 2.0x in-service multiplier)
19. GATC routing (Rule 4(1) eligibility, Class I exclusion, capacity thresholds)
20. Manual-review scenarios (unverified draft profile, visual checklists)
"""

from decimal import Decimal
import os
import sys
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

try:
    from app.regulatory.models import AccuracyClass, JobType, MassUnit
    from app.regulatory.classification_validator import (
        RegulatoryClassificationValidator,
        ClassificationValidationResult,
    )
    from app.regulatory.test_applicability_engine import (
        RegulatoryTestApplicabilityEngine,
        InstrumentCharacteristics,
        IndicationType,
        InstrumentIndicationMode,
    )
    from app.regulatory.mpe_engine import (
        MPEEngine,
        VerificationType,
        DigitalIndicationErrorResult,
        calculate_digital_indication_error,
    )
    from app.regulatory.test_plan_generator import (
        RegulatoryTestPlanGenerator,
        GeneratedTestPlan,
        generate_regulatory_test_plan,
    )
    from app.regulatory.profile import (
        RegulatoryProfile,
        PROFILE_REGISTRY,
        ProfileStatus,
    )
except ImportError:
    from backend.app.regulatory.models import AccuracyClass, JobType, MassUnit
    from backend.app.regulatory.classification_validator import (
        RegulatoryClassificationValidator,
        ClassificationValidationResult,
    )
    from backend.app.regulatory.test_applicability_engine import (
        RegulatoryTestApplicabilityEngine,
        InstrumentCharacteristics,
        IndicationType,
        InstrumentIndicationMode,
    )
    from backend.app.regulatory.mpe_engine import MPEEngine, VerificationType
    from backend.app.regulatory.test_plan_generator import (
        RegulatoryTestPlanGenerator,
        GeneratedTestPlan,
        generate_regulatory_test_plan,
    )
    from backend.app.regulatory.profile import (
        RegulatoryProfile,
        PROFILE_REGISTRY,
        ProfileStatus,
    )


class TestRegulatoryQAPipeline(unittest.TestCase):
    """
    Final QA test suite validating the complete regulatory engine pipeline
    across all 20 mandatory scenarios.
    """

    def setUp(self):
        self.generator = RegulatoryTestPlanGenerator()
        self.mpe_engine = MPEEngine()
        self.validator = RegulatoryClassificationValidator()
        self.applicability_engine = RegulatoryTestApplicabilityEngine()

    # =========================================================================
    # 1. Class I Instrument
    # =========================================================================
    def test_01_class_i_instrument_pipeline(self):
        """Scenario 1: Class I analytical balance end-to-end pipeline verification."""
        spec = {
            "job_id": "QA-JOB-01",
            "instrument_id": "CLASS-I-BAL-01",
            "accuracy_class": "I",
            "Max": 220.0,
            "Min": 0.1,  # Min >= 100e (0.1 g)
            "e": 0.001,  # 1 mg
            "d": 0.0001,  # 0.1 mg
            "unit": "g",
            "is_electronic": True,
            "indication_type": "digital",
            "has_zero_setting": True,
            "has_tare": True,
            "is_self_indicating": True,
            "verification_type": "INITIAL",
        }

        # Stage 1: Validation
        val = self.validator.validate(spec)
        self.assertTrue(val.valid, f"Class I validation failed: {val.errors}")
        self.assertEqual(val.instrument_summary["accuracy_class"], "I")
        self.assertEqual(val.ranges_evaluated[0]["n"], 220000)

        # Stage 2: MPE calculation across bands
        # Band 1: 0 to 50,000e (0 to 50g) -> 0.5e (0.0005g)
        mpe_50g = self.mpe_engine.calculate(
            accuracy_class="I", load=50.0, e=0.001, verification_type="INITIAL"
        )
        self.assertEqual(mpe_50g.mpe_in_e, 0.5)
        self.assertAlmostEqual(mpe_50g.mpe_absolute, 0.0005, places=6)

        # Band 2: 50,000e to 200,000e (50g to 200g) -> 1.0e (0.001g)
        mpe_100g = self.mpe_engine.calculate(
            accuracy_class="I", load=100.0, e=0.001, verification_type="INITIAL"
        )
        self.assertEqual(mpe_100g.mpe_in_e, 1.0)
        self.assertAlmostEqual(mpe_100g.mpe_absolute, 0.001, places=6)

        # Band 3: >200,000e (200g to 220g) -> 1.5e (0.0015g)
        mpe_220g = self.mpe_engine.calculate(
            accuracy_class="I", load=220.0, e=0.001, verification_type="INITIAL"
        )
        self.assertEqual(mpe_220g.mpe_in_e, 1.5)
        self.assertAlmostEqual(mpe_220g.mpe_absolute, 0.0015, places=6)

        # Stage 3: Test Plan Generation
        plan = self.generator.generate(spec)
        self.assertFalse(plan.is_partial_plan)
        self.assertEqual(plan.accuracy_class, "I")
        self.assertEqual(plan.n, 220000)

        # Class I environmental condition: narrow chamber temperature limits
        env = plan.required_environmental_conditions
        self.assertIn("+18°C to +23°C", env["prescribed_temperature_range"])
        self.assertIn("1°C", env["max_temperature_rate_of_change"])

        # GATC Routing: Class I is prohibited from GATC testing under Rule 4(1) of GATC Rules 2013
        self.assertFalse(plan.gatc_eligible)
        self.assertIn("Class I instruments must be tested directly by State Legal Metrology", plan.gatc_remarks)

    # =========================================================================
    # 2. Class II Instrument
    # =========================================================================
    def test_02_class_ii_instrument_pipeline(self):
        """Scenario 2: Class II high accuracy laboratory scale pipeline verification."""
        spec = {
            "job_id": "QA-JOB-02",
            "instrument_id": "CLASS-II-LAB-02",
            "accuracy_class": "II",
            "Max": 6000.0,
            "Min": 5.0,  # Min >= 50e (5.0 g) for Band B
            "e": 0.1,
            "d": 0.01,
            "unit": "g",
            "is_electronic": True,
            "indication_type": "digital",
            "has_zero_setting": True,
            "has_tare": True,
            "is_self_indicating": True,
            "verification_type": "INITIAL",
        }

        plan = self.generator.generate(spec)
        self.assertFalse(plan.is_partial_plan)
        self.assertEqual(plan.accuracy_class, "II")
        self.assertEqual(plan.n, 60000)

        # GATC Eligibility: Class II is strictly prohibited from GATC under Rules 2013 First Schedule
        self.assertFalse(plan.gatc_eligible)

        # MPE check at 50,000e (5,000g) -> 1.5e
        mpe_5000g = self.mpe_engine.calculate(
            accuracy_class="II", load=5000.0, e=0.1, verification_type="INITIAL"
        )
        self.assertEqual(mpe_5000g.mpe_in_e, 1.5)

    # =========================================================================
    # 3. Class III Instrument
    # =========================================================================
    def test_03_class_iii_instrument_pipeline(self):
        """Scenario 3: Class III medium accuracy commercial scale pipeline verification."""
        spec = {
            "job_id": "QA-JOB-03",
            "instrument_id": "CLASS-III-COMM-03",
            "accuracy_class": "III",
            "Max": 30.0,
            "Min": 0.2,  # Min >= 20e (0.2 kg)
            "e": 0.01,  # 10 g
            "d": 0.01,
            "unit": "kg",
            "is_electronic": True,
            "indication_type": "digital",
            "has_zero_setting": True,
            "has_tare": True,
            "is_self_indicating": True,
            "verification_type": "INITIAL",
        }

        plan = self.generator.generate(spec)
        self.assertFalse(plan.is_partial_plan)
        self.assertEqual(plan.accuracy_class, "III")
        self.assertEqual(plan.n, 3000)
        self.assertTrue(plan.gatc_eligible)

        # Check required tests presence
        test_ids = [t["test_id"] for t in plan.tests if t["applicable"]]
        self.assertIn("A.4.4", test_ids)  # Weighing
        self.assertIn("A.4.7", test_ids)  # Eccentricity
        self.assertIn("A.4.10", test_ids)  # Repeatability
        self.assertIn("A.4.8", test_ids)  # Discrimination

        # Eccentricity test load for Class III standard receptor: Max / 3 = 10 kg
        ecc_test = next(t for t in plan.tests if t["test_id"] == "A.4.7")
        self.assertEqual(ecc_test["test_loads"][0]["load"], 10.0)

    # =========================================================================
    # 4. Class IIII Instrument
    # =========================================================================
    def test_04_class_iiii_instrument_pipeline(self):
        """Scenario 4: Class IIII ordinary accuracy industrial scale pipeline verification."""
        spec = {
            "job_id": "QA-JOB-04",
            "instrument_id": "CLASS-IIII-IND-04",
            "accuracy_class": "IIII",
            "Max": 4000.0,
            "Min": 100.0,
            "e": 5.0,  # 5 kg
            "d": 5.0,
            "unit": "kg",
            "is_electronic": True,
            "indication_type": "digital",
            "has_zero_setting": True,
            "has_tare": False,
            "is_self_indicating": True,
            "verification_type": "INITIAL",
        }

        plan = self.generator.generate(spec)
        self.assertFalse(plan.is_partial_plan)
        self.assertEqual(plan.accuracy_class, "IIII")
        self.assertEqual(plan.n, 800)  # 100 <= n <= 1000
        self.assertTrue(plan.gatc_eligible)  # <= 5000 kg

        # Band 1: 0 to 50e (0 to 250 kg) -> 0.5e
        mpe_200kg = self.mpe_engine.calculate(
            accuracy_class="IIII", load=200.0, e=5.0, verification_type="INITIAL"
        )
        self.assertEqual(mpe_200kg.mpe_in_e, 0.5)

        # Band 2: 50e to 200e (250 kg to 1000 kg) -> 1.0e
        mpe_500kg = self.mpe_engine.calculate(
            accuracy_class="IIII", load=500.0, e=5.0, verification_type="INITIAL"
        )
        self.assertEqual(mpe_500kg.mpe_in_e, 1.0)

        # Band 3: >200e (1000 kg to 4000 kg) -> 1.5e
        mpe_4000kg = self.mpe_engine.calculate(
            accuracy_class="IIII", load=4000.0, e=5.0, verification_type="INITIAL"
        )
        self.assertEqual(mpe_4000kg.mpe_in_e, 1.5)

    # =========================================================================
    # 5. Electronic Instrument
    # =========================================================================
    def test_05_electronic_instrument_applicability(self):
        """Scenario 5: Electronic instrument triggers disturbance and electronic tests."""
        spec = {
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "is_electronic": True,
            "is_type_evaluation": True,  # Type Evaluation triggers comprehensive electronic suite
            "indication_type": "digital",
            "verification_type": "INITIAL",
        }

        plan = self.generator.generate(spec)
        applicable_tests = plan.applicable_tests

        # Electronic-specific tests must apply under type evaluation
        self.assertIn("A.5.2", applicable_tests)  # Warm-up time
        self.assertIn("A.4.11.1", applicable_tests)  # Creep test
        self.assertIn("A.4.11", applicable_tests)  # Zero return test
        self.assertIn("A.5.3", applicable_tests)  # Static temperature effect
        self.assertIn("B.1", applicable_tests)  # Disturbance immunity

    # =========================================================================
    # 6. Mechanical Instrument
    # =========================================================================
    def test_06_mechanical_instrument_applicability(self):
        """Scenario 6: Mechanical instrument isolates and excludes electronic tests."""
        spec = {
            "accuracy_class": "III",
            "Max": 20.0,
            "Min": 0.2,
            "e": 0.01,
            "d": 0.01,
            "unit": "kg",
            "is_electronic": False,  # Purely mechanical
            "indication_type": "analog",
            "verification_type": "INITIAL",
        }

        plan = self.generator.generate(spec)
        not_applicable = plan.not_applicable_tests

        # Electronic-specific tests MUST NOT apply to purely mechanical instruments
        self.assertIn("A.5.2", not_applicable)  # Warm-up not applicable
        self.assertIn("A.4.11.1", not_applicable)  # Creep not applicable
        self.assertIn("A.4.11", not_applicable)  # Zero return not applicable
        self.assertIn("B.1", not_applicable)  # Static AC disturbance not applicable
        self.assertIn("B.2", not_applicable)  # Damp heat disturbance not applicable
        self.assertIn("B.3", not_applicable)  # Span stability not applicable

    # =========================================================================
    # 7. Digital Indication
    # =========================================================================
    def test_07_digital_indication_discrimination(self):
        """Scenario 7: Digital indication applies digital discrimination with 1.4d test load."""
        spec = {
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "is_electronic": True,
            "indication_type": "digital",
            "is_self_indicating": True,
        }

        plan = self.generator.generate(spec)
        disc_test = next(t for t in plan.tests if t["test_id"] == "A.4.8")
        self.assertTrue(disc_test["applicable"])
        self.assertIn("1.4d", disc_test["acceptance_criteria"])

        # Sensitivity (A.4.9 pointer displacement) does NOT apply to digital self-indicating
        self.assertIn("A.4.9", plan.not_applicable_tests)

    # =========================================================================
    # 8. Analog Indication
    # =========================================================================
    def test_08_analog_indication_discrimination(self):
        """Scenario 8: Analog indication applies analog discrimination with 0.7d test load displacement."""
        char = InstrumentCharacteristics(
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            verification_scale_interval=0.005,
            is_electronic=False,
            indication_type=IndicationType.ANALOG,
        )

        app_report = self.applicability_engine.evaluate(char)
        disc_test = next(t for t in app_report.applicable_tests if t["test_id"] == "A.4.8")
        self.assertTrue(disc_test["applicable"])
        self.assertIn("0.7d", disc_test["reason"])

    # =========================================================================
    # 9. Zero-Setting Instrument
    # =========================================================================
    def test_09_zero_setting_applicability_and_criteria(self):
        """Scenario 9: Zero-setting accuracy applies only when zero-setting device is present."""
        # Case A: With zero-setting
        spec_with_zero = {
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "unit": "kg",
            "has_zero_setting": True,
        }
        plan_with_zero = self.generator.generate(spec_with_zero)
        self.assertIn("A.4.2", plan_with_zero.applicable_tests)
        zero_test = next(t for t in plan_with_zero.tests if t["test_id"] == "A.4.2")
        self.assertIn("0.25e", zero_test["acceptance_criteria"])

        # Case B: Without zero-setting
        spec_without_zero = {
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "unit": "kg",
            "has_zero_setting": False,
        }
        plan_without_zero = self.generator.generate(spec_without_zero)
        self.assertIn("A.4.2", plan_without_zero.not_applicable_tests)

    # =========================================================================
    # 10. Tare Instrument
    # =========================================================================
    def test_10_tare_instrument_applicability_and_net_loads(self):
        """Scenario 10: Tare device inclusion triggers tare accuracy and net load points."""
        # Case A: With tare
        spec_with_tare = {
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "unit": "kg",
            "has_tare": True,
        }
        plan_with_tare = self.generator.generate(spec_with_tare)
        self.assertIn("A.4.3", plan_with_tare.applicable_tests)
        tare_test = next(t for t in plan_with_tare.tests if t["test_id"] == "A.4.3")
        self.assertTrue(tare_test["applicable"])
        self.assertIn("net weighing", tare_test["acceptance_criteria"].lower())

        # Case B: Without tare
        spec_without_tare = {
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "unit": "kg",
            "has_tare": False,
        }
        plan_without_tare = self.generator.generate(spec_without_tare)
        self.assertIn("A.4.3", plan_without_tare.not_applicable_tests)

    # =========================================================================
    # 11. Non-Self-Indicating Instrument
    # =========================================================================
    def test_11_non_self_indicating_instrument_sensitivity(self):
        """Scenario 11: Non-self-indicating instrument triggers sensitivity pointer test."""
        spec = {
            "accuracy_class": "III",
            "Max": 20.0,
            "Min": 0.2,
            "e": 0.01,
            "unit": "kg",
            "instrument_type": "NON_SELF_INDICATING",  # Non-self-indicating
            "is_self_indicating": False,
            "indication_type": "analog",
            "is_electronic": False,
        }

        plan = self.generator.generate(spec)
        self.assertIn("A.4.9", plan.applicable_tests)  # Sensitivity applies
        sens_test = next(t for t in plan.tests if t["test_id"] == "A.4.9")
        self.assertTrue(sens_test["applicable"])
        self.assertIn("displacement", sens_test["acceptance_criteria"].lower())

    # =========================================================================
    # 12. Multi-Range Instrument
    # =========================================================================
    def test_12_multi_range_instrument_pipeline(self):
        """Scenario 12: Multi-range instrument boundary validations and test loads."""
        spec = {
            "job_id": "QA-JOB-MR",
            "instrument_id": "MULTI-RANGE-SCALE",
            "accuracy_class": "III",
            "multi_range_status": True,
            "unit": "kg",
            "ranges": [
                {"range_index": 1, "Max": 30.0, "Min": 0.2, "e": 0.01},
                {"range_index": 2, "Max": 60.0, "Min": 0.4, "e": 0.02},
            ],
        }

        # Validate multi-range specification
        val = self.validator.validate(spec)
        self.assertTrue(val.valid, f"Multi-range validation failed: {val.errors}")
        self.assertEqual(len(val.ranges_evaluated), 2)
        self.assertEqual(val.ranges_evaluated[0]["n"], 3000)
        self.assertEqual(val.ranges_evaluated[1]["n"], 3000)
        self.assertTrue(val.manual_review_required)

    # =========================================================================
    # 13. Multi-Interval Instrument
    # =========================================================================
    def test_13_multi_interval_instrument_safe_partial_plan(self):
        """Scenario 13: Multi-interval instrument triggers safe partial plan and manual review."""
        spec = {
            "job_id": "QA-JOB-MI",
            "instrument_id": "MULTI-INTERVAL-SCALE",
            "accuracy_class": "III",
            "is_multi_interval": True,
            "Max": 15.0,
            "Min": 0.04,
            "e": 0.002,
            "d": 0.002,
            "unit": "kg",
        }

        plan = self.generator.generate(spec)
        # Must flag partial plan due to automatic changeover thresholds
        self.assertTrue(plan.is_partial_plan)
        self.assertTrue(any("Multi-interval scale" in r for r in plan.partial_plan_reasons))
        self.assertTrue(
            any("PARTIAL_PLAN_ALERT" in item.get("test_id", "") for item in plan.manual_review_items)
        )

    # =========================================================================
    # 14. Invalid e
    # =========================================================================
    def test_14_invalid_scale_interval_e_rejection(self):
        """Scenario 14: Non-1,2,5 step sequence or class-incompatible e fails validation."""
        # Non-standard step: e = 0.003 (not in 1, 2, 5 * 10^k)
        spec = {
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.003,
            "d": 0.003,
            "unit": "kg",
        }

        val = self.validator.validate(spec)
        self.assertFalse(val.valid)
        error_rules = [e.rule_id for e in val.errors]
        self.assertIn("RULE_SCALE_INTERVAL_FORM", error_rules)

        # Attempting pipeline execution with invalid e generates partial plan with validation errors
        plan = self.generator.generate(spec)
        self.assertTrue(plan.is_partial_plan)
        self.assertTrue(any("Classification validation failed" in r for r in plan.partial_plan_reasons))

    # =========================================================================
    # 15. Invalid Min/Max
    # =========================================================================
    def test_15_invalid_min_max_rejection(self):
        """Scenario 15: Min > Max or non-positive capacity values fail validation safely."""
        # Case A: Min > Max
        spec_min_exceeds_max = {
            "accuracy_class": "III",
            "Max": 10.0,
            "Min": 15.0,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
        }
        val_a = self.validator.validate(spec_min_exceeds_max)
        self.assertFalse(val_a.valid)
        self.assertTrue(any("RULE_MIN_EXCEEDS_MAX" in e.rule_id for e in val_a.errors))

        # Case B: Non-positive Max
        spec_zero_max = {
            "accuracy_class": "III",
            "Max": 0.0,
            "Min": 0.0,
            "e": 0.005,
            "unit": "kg",
        }
        val_b = self.validator.validate(spec_zero_max)
        self.assertFalse(val_b.valid)
        self.assertTrue(any("RULE_MAX_NON_POSITIVE" in e.rule_id for e in val_b.errors))

    # =========================================================================
    # 16. Invalid n
    # =========================================================================
    def test_16_invalid_n_out_of_bounds_rejection(self):
        """Scenario 16: n exceeding statutory class limits fails validation."""
        # Class III allows 500 <= n <= 10,000.
        # Here n = 15 kg / 0.001 kg = 15,000 (> 10,000)
        spec_n_high = {
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.001,
            "d": 0.001,
            "unit": "kg",
        }
        val_high = self.validator.validate(spec_n_high)
        self.assertFalse(val_high.valid)
        self.assertTrue(any("RULE_CLASS_III_N_MAX" in e.rule_id for e in val_high.errors))

        # Class III with n below minimum: Max = 1 kg, e = 0.005 kg -> n = 200 (< 500)
        spec_n_low = {
            "accuracy_class": "III",
            "Max": 1.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
        }
        val_low = self.validator.validate(spec_n_low)
        self.assertFalse(val_low.valid)
        self.assertTrue(any("RULE_CLASS_III_N_MIN" in e.rule_id for e in val_low.errors))

    # =========================================================================
    # 17. MPE Boundary Values
    # =========================================================================
    def test_17_mpe_boundary_transitions_exact(self):
        """Scenario 17: Exact Decimal MPE boundary transitions for Class III initial verification."""
        # Class III Initial Verification thresholds:
        # 0 <= m <= 500e: MPE = +/-0.5e
        # 500e < m <= 2000e: MPE = +/-1.0e
        # 2000e < m <= 10000e: MPE = +/-1.5e
        e = 0.01  # 10 g

        # Exactly at 500e (5.00 kg) -> 0.5e (0.005 kg)
        mpe_500 = self.mpe_engine.calculate(
            accuracy_class="III", load=5.00, e=e, verification_type="INITIAL"
        )
        self.assertEqual(mpe_500.mpe_in_e, 0.5)
        self.assertAlmostEqual(mpe_500.mpe_absolute, 0.005, places=6)

        # Just above 500e (5.0001 kg = 500.01e) -> transitions immediately to 1.0e (0.01 kg)
        mpe_500_plus = self.mpe_engine.calculate(
            accuracy_class="III", load=5.0001, e=e, verification_type="INITIAL"
        )
        self.assertEqual(mpe_500_plus.mpe_in_e, 1.0)
        self.assertAlmostEqual(mpe_500_plus.mpe_absolute, 0.01, places=6)

        # Exactly at 2000e (20.00 kg) -> 1.0e (0.01 kg)
        mpe_2000 = self.mpe_engine.calculate(
            accuracy_class="III", load=20.00, e=e, verification_type="INITIAL"
        )
        self.assertEqual(mpe_2000.mpe_in_e, 1.0)
        self.assertAlmostEqual(mpe_2000.mpe_absolute, 0.01, places=6)

        # Just above 2000e (20.0001 kg = 2000.01e) -> transitions immediately to 1.5e (0.015 kg)
        mpe_2000_plus = self.mpe_engine.calculate(
            accuracy_class="III", load=20.0001, e=e, verification_type="INITIAL"
        )
        self.assertEqual(mpe_2000_plus.mpe_in_e, 1.5)
        self.assertAlmostEqual(mpe_2000_plus.mpe_absolute, 0.015, places=6)

        # At Max capacity 10000e (100.00 kg) -> 1.5e (0.015 kg)
        mpe_max = self.mpe_engine.calculate(
            accuracy_class="III", load=100.00, e=e, verification_type="INITIAL"
        )
        self.assertEqual(mpe_max.mpe_in_e, 1.5)
        self.assertAlmostEqual(mpe_max.mpe_absolute, 0.015, places=6)

    # =========================================================================
    # 18. Subsequent Verification
    # =========================================================================
    def test_18_subsequent_verification_multiplier(self):
        """Scenario 18: Subsequent verification strictly applies 2.0x in-service multiplier."""
        e = 0.01

        # Class III at 500e: initial is 0.5e, subsequent must be 1.0e
        mpe_sub_500 = self.mpe_engine.calculate(
            accuracy_class="III", load=5.0, e=e, verification_type="SUBSEQUENT"
        )
        self.assertEqual(mpe_sub_500.mpe_in_e, 1.0)
        self.assertAlmostEqual(mpe_sub_500.mpe_absolute, 0.01, places=6)

        # Class III at 2000e: initial is 1.0e, subsequent must be 2.0e
        mpe_sub_2000 = self.mpe_engine.calculate(
            accuracy_class="III", load=20.0, e=e, verification_type="SUBSEQUENT"
        )
        self.assertEqual(mpe_sub_2000.mpe_in_e, 2.0)
        self.assertAlmostEqual(mpe_sub_2000.mpe_absolute, 0.02, places=6)

        # Class III at 10000e: initial is 1.5e, subsequent must be 3.0e
        mpe_sub_10000 = self.mpe_engine.calculate(
            accuracy_class="III", load=100.0, e=e, verification_type="SUBSEQUENT"
        )
        self.assertEqual(mpe_sub_10000.mpe_in_e, 3.0)
        self.assertAlmostEqual(mpe_sub_10000.mpe_absolute, 0.03, places=6)

    # =========================================================================
    # 19. GATC Routing
    # =========================================================================
    def test_19_gatc_routing_logic(self):
        """Scenario 19: GATC eligibility adheres to Rule 3 and First Schedule of GATC Rules 2013."""
        active_prof = PROFILE_REGISTRY.get_profile("IN_LM_2011_ACTIVE")

        # Class I: always GATC ineligible (prohibited under GATC Rules 2013 First Schedule)
        ok_i, msg_i = active_prof.is_gatc_eligible("I", 220.0)
        self.assertFalse(ok_i)
        self.assertIn("Class I", msg_i)

        # Class II: always GATC ineligible (prohibited under GATC Rules 2013 First Schedule)
        ok_ii, msg_ii = active_prof.is_gatc_eligible("II", 50.0)
        self.assertFalse(ok_ii)
        self.assertIn("Class II", msg_ii)

        # Class III <= 150 kg: eligible
        ok_iii, msg_iii = active_prof.is_gatc_eligible("III", 150.0)
        self.assertTrue(ok_iii)

        # Class III > 150 kg: ineligible (exceeds statutory GATC ceiling of 150 kg)
        ok_heavy, msg_heavy = active_prof.is_gatc_eligible("III", 200.0)
        self.assertFalse(ok_heavy)
        self.assertIn("exceeds statutory GATC limit of 150.0 kg", msg_heavy)

        # Class IIII <= 5000 kg: eligible
        ok_iiii, _ = active_prof.is_gatc_eligible("IIII", 4000.0)
        self.assertTrue(ok_iiii)

    # =========================================================================
    # 20. Manual-Review Scenarios
    # =========================================================================
    def test_20_manual_review_unverified_draft_profile(self):
        """Scenario 20: Draft profile triggers manual review flag and non-authoritative mark."""
        spec = {
            "job_id": "QA-JOB-DRAFT",
            "instrument_id": "SCALE-DRAFT-01",
            "profile_id": "IN_LM_2026_GSR568E_DRAFT",  # Unverified secondary-source draft
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "verification_type": "INITIAL",
        }

        plan = self.generator.generate(spec)

        # Must flag partial plan and require manual review
        self.assertTrue(plan.is_partial_plan)
        self.assertEqual(plan.profile_status, "MANUAL_REVIEW")
        self.assertFalse(plan.is_authoritative)
        self.assertTrue(
            any("PROFILE_MANUAL_REVIEW_REQUIRED" in item["test_id"] for item in plan.manual_review_items)
        )
        self.assertTrue(
            any("is marked MANUAL_REVIEW / UNVERIFIED" in r for r in plan.partial_plan_reasons)
        )

    # =========================================================================
    # 21. Digital Indication Turning-Point Error Calculation (OIML A.4.4.3)
    # =========================================================================
    def test_21_digital_indication_turning_point_error(self):
        """
        Scenario 21: Verify digital turning-point error calculation per OIML R 76-1 Clause A.4.4.3:
            P = I + 0.5e - delta_L
            E = P - L = I + 0.5e - delta_L - L
            Ec = E - E0
        """
        # Test Case 1: Standard turning-point shift
        # e = 1 g, L = 200 g, I = 200 g, delta_L = 0.7 g, zero error E0 = +0.1 g
        # P = 200 + 0.5 - 0.7 = 199.8 g
        # E = 199.8 - 200 = -0.2 g
        # Ec = -0.2 - (+0.1) = -0.3 g
        # Class II at 200 g (200e <= 5000e -> MPE = +/- 0.5 g)
        # |Ec| = 0.3 <= 0.5 -> PASS, margin = 0.2 g
        res = calculate_digital_indication_error(
            accuracy_class="II",
            applied_load_L=200.0,
            indication_I=200.0,
            delta_L=0.7,
            e=1.0,
            zero_error_E0=0.1,
            verification_type="INITIAL",
        )

        self.assertAlmostEqual(res.turning_point_indication_P, 199.8, places=6)
        self.assertAlmostEqual(res.error_E, -0.2, places=6)
        self.assertAlmostEqual(res.corrected_error_Ec, -0.3, places=6)
        self.assertAlmostEqual(res.mpe_absolute, 0.5, places=6)
        self.assertTrue(res.passed)
        self.assertFalse(res.fail)
        self.assertAlmostEqual(res.margin, 0.2, places=6)
        self.assertAlmostEqual(res.margin_in_e, 0.2, places=6)

        # Test Case 2: Out of tolerance failure
        # delta_L = 1.2 g -> P = 200 + 0.5 - 1.2 = 199.3 g -> E = -0.7 g -> Ec = -0.7 - 0.1 = -0.8 g
        # |Ec| = 0.8 > 0.5 -> FAIL
        res_fail = calculate_digital_indication_error(
            accuracy_class="II",
            applied_load_L=200.0,
            indication_I=200.0,
            delta_L=1.2,
            e=1.0,
            zero_error_E0=0.1,
            verification_type="INITIAL",
        )
        self.assertFalse(res_fail.passed)
        self.assertTrue(res_fail.fail)
        self.assertAlmostEqual(res_fail.margin, -0.3, places=6)

    # =========================================================================
    # 22. Zero-Setting Range Statutory Limits (OIML Clause 4.5.1)
    # =========================================================================
    def test_22_initial_zero_setting_range_limits(self):
        """
        Scenario 22: Initial zero-setting range > 20% Max triggers regulatory warning
        and manual review flag under OIML R 76-1:2006 Clause 4.5.1.
        """
        # Spec with initial zero-setting = 25% (exceeds 20% Max)
        spec_invalid_zs = {
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "initial_zero_setting_range_percent": 25.0,
        }
        res = self.validator.validate(spec_invalid_zs)
        self.assertTrue(res.manual_review_required)
        self.assertTrue(any(w.rule_id == "RULE_INITIAL_ZERO_SETTING_RANGE_EXCEEDED" for w in res.warnings))

        # Spec with initial zero-setting = 15% (compliant)
        spec_valid_zs = {
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "initial_zero_setting_range_percent": 15.0,
        }
        res_valid = self.validator.validate(spec_valid_zs)
        self.assertFalse(any(w.rule_id == "RULE_INITIAL_ZERO_SETTING_RANGE_EXCEEDED" for w in res_valid.warnings))

    # =========================================================================
    # 23. Repeatability Cycles by Accuracy Class (OIML Clause A.4.10)
    # =========================================================================
    def test_23_repeatability_cycles_by_accuracy_class(self):
        """
        Scenario 23: Repeatability weighings must be at least 6 for Class I and II,
        and at least 3 for Class III and IIII under Clause A.4.10.
        """
        # Class II scale
        spec_cls2 = {
            "accuracy_class": "II",
            "Max": 6000.0,
            "Min": 5.0,
            "e": 0.1,
            "d": 0.1,
            "unit": "g",
            "verification_type": "INITIAL",
        }
        plan_cls2 = self.generator.generate(spec_cls2)
        rep_cls2 = next(t for t in plan_cls2.tests if t["test_id"] == "A.4.10")
        # 2 load levels * 6 cycles = 12 test loads
        self.assertEqual(len(rep_cls2["test_loads"]), 12)
        self.assertIn("6 repeated weighings", rep_cls2["acceptance_criteria"])

        # Class III scale
        spec_cls3 = {
            "accuracy_class": "III",
            "Max": 15.0,
            "Min": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "verification_type": "INITIAL",
        }
        plan_cls3 = self.generator.generate(spec_cls3)
        rep_cls3 = next(t for t in plan_cls3.tests if t["test_id"] == "A.4.10")
        # 2 load levels * 3 cycles = 6 test loads
        self.assertEqual(len(rep_cls3["test_loads"]), 6)
        self.assertIn("3 repeated weighings", rep_cls3["acceptance_criteria"])


if __name__ == "__main__":
    unittest.main()
