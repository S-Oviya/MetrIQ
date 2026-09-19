"""
MetrIQ Unit Tests — Person 4 Test Engine Orchestration & Service Layer
======================================================================
Tests:
1. TestEngine.execute dispatching for all 10 statutory NAWI test types
2. CalculationService facade methods (calculate_mpe, execute_test, batch_execute_job)
3. Audit tracking and standard references
4. Error handling and validation
"""

import unittest
from app.calculations.engine import TestEngine, STANDARD_CLAUSES
from app.calculations.models import (
    ChecklistItem,
    ChecklistStatus,
    RawObservation,
    TestDefinition,
    TestExecutionResult,
    TestRun,
    TestType,
    Verdict,
)
from app.calculations.service import CalculationService, calculate_mpe_service, execute_test_service


class TestP4Engine(unittest.TestCase):

    def setUp(self):
        self.instrument = {
            "instrument_id": "INST-TEST-001",
            "accuracy_class": "CLASS_III",
            "max_capacity": 15.0,
            "min_capacity": 0.1,
            "e": 0.005,
            "d": 0.005,
            "unit": "kg",
            "software_version": "v1.0.0",
        }

    def test_execute_weighing_performance(self):
        """TestEngine dispatches and evaluates WEIGHING_PERFORMANCE."""
        run = TestRun(
            job_id="JOB-001",
            instrument_id=self.instrument["instrument_id"],
            test_type=TestType.WEIGHING_PERFORMANCE,
            observations=[
                RawObservation(step_number=1, applied_load=0.0, indicated_value=0.0),
                RawObservation(step_number=2, applied_load=5.0, indicated_value=5.001),
                RawObservation(step_number=3, applied_load=15.0, indicated_value=15.002),
            ],
        )
        res: TestExecutionResult = TestEngine.execute(run, self.instrument)
        self.assertIsInstance(res, TestExecutionResult)
        self.assertEqual(res.verdict, Verdict.PASS)
        self.assertEqual(res.test_type, TestType.WEIGHING_PERFORMANCE)
        self.assertEqual(res.observations_evaluated, 3)
        self.assertEqual(res.standard_reference, STANDARD_CLAUSES[TestType.WEIGHING_PERFORMANCE])

    def test_execute_all_10_statutory_tests(self):
        """Verify TestEngine executes every statutory test type cleanly."""
        test_payloads = [
            (
                TestType.WEIGHING_PERFORMANCE,
                [
                    RawObservation(applied_load=0.0, indicated_value=0.0),
                    RawObservation(applied_load=5.0, indicated_value=5.001),
                ],
            ),
            (
                TestType.ECCENTRICITY,
                [
                    RawObservation(applied_load=5.0, indicated_value=5.000, position="CENTER"),
                    RawObservation(applied_load=5.0, indicated_value=5.001, position="CORNER_1"),
                ],
            ),
            (
                TestType.REPEATABILITY,
                [
                    RawObservation(applied_load=10.0, indicated_value=10.000),
                    RawObservation(applied_load=10.0, indicated_value=10.001),
                    RawObservation(applied_load=10.0, indicated_value=10.001),
                ],
            ),
            (
                TestType.ZERO_RETURN,
                [
                    RawObservation(applied_load=0.0, indicated_value=0.0),
                    RawObservation(applied_load=15.0, indicated_value=15.0),
                    RawObservation(applied_load=0.0, indicated_value=0.001),
                ],
            ),
            (
                TestType.CREEP,
                [
                    RawObservation(applied_load=15.0, indicated_value=15.000, time_seconds=5),
                    RawObservation(applied_load=15.0, indicated_value=15.001, time_seconds=1800),
                ],
            ),
            (
                TestType.DISCRIMINATION,
                [
                    RawObservation(applied_load=10.0, indicated_value=10.000, extra_load=0.007),
                ],
            ),
            (
                TestType.TARE,
                [
                    RawObservation(tare_load=2.0, indicated_value=0.0),
                    RawObservation(applied_load=5.0, indicated_value=5.001),
                ],
            ),
            (
                TestType.TEMPERATURE_EFFECT,
                [
                    RawObservation(temperature_c=20.0, applied_load=0.0, indicated_value=0.0),
                    RawObservation(temperature_c=20.0, applied_load=5.0, indicated_value=5.001),
                    RawObservation(temperature_c=40.0, applied_load=0.0, indicated_value=0.0005),
                    RawObservation(temperature_c=40.0, applied_load=5.0, indicated_value=5.0012),
                ],
            ),
            (
                TestType.CONSTRUCTION_EXAMINATION,
                [
                    RawObservation(
                        checklist_item=ChecklistItem(
                            item_id="CONST-01",
                            title="Nameplate",
                            clause="7.1",
                            status=ChecklistStatus.COMPLIANT,
                        )
                    )
                ],
            ),
            (
                TestType.SOFTWARE_EXAMINATION,
                [
                    RawObservation(
                        checklist_item=ChecklistItem(
                            item_id="SOFT-01",
                            title="Software Identification",
                            clause="5.5",
                            status=ChecklistStatus.COMPLIANT,
                        )
                    )
                ],
            ),
        ]

        for ttype, observations in test_payloads:
            with self.subTest(test_type=ttype.value):
                run = TestRun(test_type=ttype, observations=observations)
                res = TestEngine.execute(run, self.instrument)
                self.assertIsInstance(res, TestExecutionResult)
                self.assertEqual(res.verdict, Verdict.PASS)
                self.assertIn("data", {"data": res.to_dict()})

    def test_calculation_service_calculate_mpe(self):
        """CalculationService.calculate_mpe returns serializable dictionary."""
        res = CalculationService.calculate_mpe(
            load=10.0,
            accuracy_class="CLASS_III",
            e=0.005,
            verification_type="INITIAL",
            unit="kg",
        )
        self.assertIsInstance(res, dict)
        self.assertIn("mpe_absolute", res)
        self.assertIn("band_description", res)
        self.assertIn("reference_clause", res)

    def test_calculation_service_batch_execute_job(self):
        """CalculationService.batch_execute_job evaluates all tests and aggregates verdict."""
        test_runs = [
            {
                "test_type": "WEIGHING_PERFORMANCE",
                "observations": [
                    {"applied_load": 0.0, "indicated_value": 0.0},
                    {"applied_load": 5.0, "indicated_value": 5.001},
                ],
            },
            {
                "test_type": "ECCENTRICITY",
                "observations": [
                    {"applied_load": 5.0, "indicated_value": 5.000, "position": "CENTER"},
                    {"applied_load": 5.0, "indicated_value": 5.001, "position": "CORNER_1"},
                ],
            },
        ]
        res = CalculationService.batch_execute_job(
            job_id="JOB-BATCH-1",
            test_runs=test_runs,
            instrument_data=self.instrument,
        )
        self.assertEqual(res["overall_verdict"], "PASS")
        self.assertEqual(res["tests_evaluated"], 2)
        self.assertEqual(res["passed_count"], 2)
        self.assertEqual(res["failed_count"], 0)

    def test_missing_instrument_e_raises_error(self):
        """Executing without required scale interval 'e' raises ValueError."""
        bad_instrument = {"accuracy_class": "CLASS_III"}
        run = TestRun(
            test_type=TestType.WEIGHING_PERFORMANCE,
            observations=[RawObservation(applied_load=0.0, indicated_value=0.0)],
        )
        with self.assertRaises(ValueError):
            TestEngine.execute(run, bad_instrument)


if __name__ == "__main__":
    unittest.main()
