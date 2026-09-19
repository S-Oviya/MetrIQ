"""
MetrIQ P4: Test Engine Execution Layer
======================================
Person 4: Rachitha (Test Engine + Calculations Lead)

Coordinates the generic execution pipeline:
    Test Definition
          ↓
      Test Run
          ↓
   Raw Observations
          ↓
     Calculation
          ↓
     PASS / FAIL

Dispatches raw observation data from verification runs to the appropriate
metrological calculation modules, retrieves statutory limits from Person 2,
and aggregates intermediate steps into an auditable final TestExecutionResult.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from app.calculations.models import (
    RawObservation,
    TestDefinition,
    TestExecutionResult,
    TestRun,
    TestType,
    Verdict,
)
from app.calculations.mpe import MPEAdapter
from app.calculations.weighing import WeighingPerformanceCalculator
from app.calculations.eccentricity import EccentricityCalculator
from app.calculations.repeatability import RepeatabilityCalculator
from app.calculations.zero_return import ZeroReturnCalculator
from app.calculations.creep import CreepCalculator
from app.calculations.discrimination import DiscriminationCalculator
from app.calculations.tare import TareCalculator
from app.calculations.temperature import TemperatureCalculator
from app.calculations.examination import ExaminationCalculator


# Statutory clauses by test type for audit tracking
STANDARD_CLAUSES = {
    TestType.WEIGHING_PERFORMANCE: "OIML R 76-1:2006 Clause A.4.8 / IN LM 2011 7th Sched",
    TestType.ECCENTRICITY: "OIML R 76-1:2006 Clause A.4.7 / IN LM 2011 7th Sched",
    TestType.REPEATABILITY: "OIML R 76-1:2006 Clause A.4.10 / IN LM 2011 7th Sched",
    TestType.ZERO_RETURN: "OIML R 76-1:2006 Clause 4.1.2.2 & A.4.4.2",
    TestType.CREEP: "OIML R 76-1:2006 Clause 4.1.2.1 & A.4.4.1",
    TestType.DISCRIMINATION: "OIML R 76-1:2006 Clause 3.8 & A.4.4.3",
    TestType.TARE: "OIML R 76-1:2006 Clause 4.6 & A.4.6",
    TestType.TEMPERATURE_EFFECT: "OIML R 76-1:2006 Clause 3.9.2.2 & A.5.3",
    TestType.CONSTRUCTION_EXAMINATION: "OIML R 76-1:2006 Clause 3.9, 4, 7.1",
    TestType.SOFTWARE_EXAMINATION: "OIML R 76-1:2006 Clause 5.5",
}


class TestEngine:
    """
    Core orchestrator dispatching test runs to specialized calculators
    and compiling the final compliance verdict.
    """

    @classmethod
    def execute(
        cls,
        test_run: Union[TestRun, Dict[str, Any]],
        instrument: Dict[str, Any],
        verification_type: str = "INITIAL",
    ) -> TestExecutionResult:
        """
        Executes a test run against instrument specifications and returns an auditable result.
        """
        if isinstance(test_run, dict):
            test_run = TestRun.from_dict(test_run)

        # Extract instrument parameters
        accuracy_class = instrument.get("accuracy_class", "CLASS_III")
        if hasattr(accuracy_class, "value"):
            accuracy_class = accuracy_class.value
        raw_e = instrument.get("e") or instrument.get("verification_scale_interval")
        if raw_e is None:
            raise ValueError("Instrument specification missing required parameter 'e'.")
        e = float(raw_e)

        raw_d = instrument.get("d") or instrument.get("actual_scale_interval") or e
        d = float(raw_d)
        unit = str(instrument.get("unit", "kg"))
        receptor_type = str(instrument.get("receptor_type", "STANDARD_PLATTER"))
        partial_ranges = instrument.get("partial_ranges")

        test_type = test_run.test_type
        obs_dicts = [o.to_dict() if isinstance(o, RawObservation) else o for o in test_run.observations]

        # Dispatch calculation by test type
        if test_type == TestType.WEIGHING_PERFORMANCE:
            res = WeighingPerformanceCalculator.evaluate_run(
                observations=obs_dicts,
                accuracy_class=accuracy_class,
                e=e,
                verification_type=verification_type,
                unit=unit,
                partial_ranges=partial_ranges,
            )
            return TestExecutionResult(
                test_run_id=test_run.test_run_id,
                test_type=test_type,
                verdict=res.verdict,
                summary=res.summary,
                calculated_values={
                    "max_error": res.max_error,
                    "max_error_load": res.max_error_load,
                    "max_hysteresis": res.max_hysteresis,
                    "unit": res.unit,
                },
                regulatory_limits={
                    "accuracy_class": accuracy_class,
                    "verification_type": verification_type,
                    "e": e,
                },
                observations_evaluated=len(res.points),
                intermediate_results=[p.to_dict() for p in res.points],
                standard_reference=STANDARD_CLAUSES[test_type],
            )

        elif test_type == TestType.ECCENTRICITY:
            res = EccentricityCalculator.evaluate(
                observations=obs_dicts,
                accuracy_class=accuracy_class,
                e=e,
                verification_type=verification_type,
                unit=unit,
                receptor_type=receptor_type,
                partial_ranges=partial_ranges,
            )
            return TestExecutionResult(
                test_run_id=test_run.test_run_id,
                test_type=test_type,
                verdict=res.verdict,
                summary=res.summary,
                calculated_values={
                    "max_error": res.max_error,
                    "worst_position": res.worst_position,
                    "max_position_difference": res.max_position_difference,
                    "unit": res.unit,
                    "receptor_type": res.receptor_type,
                },
                regulatory_limits={
                    "accuracy_class": accuracy_class,
                    "verification_type": verification_type,
                    "e": e,
                },
                observations_evaluated=len(res.positions),
                intermediate_results=[p.to_dict() for p in res.positions],
                standard_reference=STANDARD_CLAUSES[test_type],
            )

        elif test_type == TestType.REPEATABILITY:
            res = RepeatabilityCalculator.evaluate_run(
                observations=obs_dicts,
                accuracy_class=accuracy_class,
                e=e,
                verification_type=verification_type,
                unit=unit,
                partial_ranges=partial_ranges,
            )
            return TestExecutionResult(
                test_run_id=test_run.test_run_id,
                test_type=test_type,
                verdict=res.verdict,
                summary=res.summary,
                calculated_values={
                    "worst_span": res.worst_span,
                    "worst_span_load": res.worst_span_load,
                    "series_count": len(res.series_results),
                    "unit": res.unit,
                },
                regulatory_limits={
                    "accuracy_class": accuracy_class,
                    "verification_type": verification_type,
                    "e": e,
                },
                observations_evaluated=len(obs_dicts),
                intermediate_results=[s.to_dict() for s in res.series_results],
                standard_reference=STANDARD_CLAUSES[test_type],
            )

        elif test_type == TestType.ZERO_RETURN:
            res = ZeroReturnCalculator.evaluate_run(
                observations=obs_dicts,
                e=e,
                accuracy_class=accuracy_class,
                unit=unit,
                partial_ranges=partial_ranges,
            )
            return TestExecutionResult(
                test_run_id=test_run.test_run_id,
                test_type=test_type,
                verdict=res.verdict,
                summary=res.summary,
                calculated_values={
                    "zero_drift": res.zero_drift,
                    "drift_in_e": res.drift_in_e,
                    "initial_zero": res.initial_zero,
                    "returned_zero": res.returned_zero,
                    "margin": res.margin,
                    "unit": res.unit,
                },
                regulatory_limits={
                    "statutory_limit": res.statutory_limit,
                    "statutory_limit_e": res.statutory_limit_e,
                    "reference": "OIML R 76-1:2006 Clause 4.1.2.2",
                },
                observations_evaluated=len(obs_dicts),
                intermediate_results=[res.to_dict()],
                standard_reference=STANDARD_CLAUSES[test_type],
            )

        elif test_type == TestType.CREEP:
            target_load = float(obs_dicts[0].get("applied_load", instrument.get("max_capacity", 0.0)))
            res = CreepCalculator.evaluate(
                load=target_load,
                time_observations=obs_dicts,
                accuracy_class=accuracy_class,
                e=e,
                verification_type=verification_type,
                unit=unit,
                partial_ranges=partial_ranges,
            )
            return TestExecutionResult(
                test_run_id=test_run.test_run_id,
                test_type=test_type,
                verdict=res.verdict,
                summary=res.summary,
                calculated_values={
                    "load": res.load,
                    "total_creep": res.total_creep,
                    "total_creep_in_e": res.total_creep_in_e,
                    "transient_creep": res.transient_creep,
                    "transient_creep_in_e": res.transient_creep_in_e,
                    "unit": res.unit,
                },
                regulatory_limits={
                    "total_creep_limit": res.total_creep_limit,
                    "total_creep_limit_e": 0.5,
                    "transient_creep_limit": res.transient_creep_limit,
                    "transient_creep_limit_e": 0.2,
                    "mpe_limit": res.mpe_limit.to_dict(),
                },
                observations_evaluated=len(res.time_points),
                intermediate_results=[tp.to_dict() for tp in res.time_points],
                standard_reference=STANDARD_CLAUSES[test_type],
            )

        elif test_type == TestType.DISCRIMINATION:
            res = DiscriminationCalculator.evaluate_run(
                observations=obs_dicts,
                d=d,
                unit=unit,
            )
            return TestExecutionResult(
                test_run_id=test_run.test_run_id,
                test_type=test_type,
                verdict=res.verdict,
                summary=res.summary,
                calculated_values={
                    "d": res.d,
                    "unit": res.unit,
                    "tested_points": len(res.points),
                },
                regulatory_limits={
                    "expected_increment": res.d,
                    "reference": "OIML R 76-1:2006 Clause 3.8",
                },
                observations_evaluated=len(res.points),
                intermediate_results=[p.to_dict() for p in res.points],
                standard_reference=STANDARD_CLAUSES[test_type],
            )

        elif test_type == TestType.TARE:
            # First observation is tare setting, subsequent are net loads
            tare_setting_obs = obs_dicts[0]
            net_obs = obs_dicts[1:]
            tare_val = float(tare_setting_obs.get("tare_load", tare_setting_obs.get("applied_load", 0.0)))
            res = TareCalculator.evaluate_run(
                tare_load=tare_val,
                tare_setting_observation=tare_setting_obs,
                net_observations=net_obs,
                accuracy_class=accuracy_class,
                e=e,
                verification_type=verification_type,
                unit=unit,
                partial_ranges=partial_ranges,
            )
            return TestExecutionResult(
                test_run_id=test_run.test_run_id,
                test_type=test_type,
                verdict=res.verdict,
                summary=res.summary,
                calculated_values={
                    "tare_setting_error": res.tare_setting.tare_setting_error,
                    "max_net_error": res.max_net_error,
                    "unit": res.unit,
                },
                regulatory_limits={
                    "tare_setting_limit": res.tare_setting.statutory_limit,
                    "tare_setting_limit_e": res.tare_setting.statutory_limit_e,
                },
                observations_evaluated=len(obs_dicts),
                intermediate_results=[p.to_dict() for p in res.net_points],
                standard_reference=STANDARD_CLAUSES[test_type],
            )

        elif test_type == TestType.TEMPERATURE_EFFECT:
            res = TemperatureCalculator.evaluate(
                observations=obs_dicts,
                accuracy_class=accuracy_class,
                e=e,
                verification_type=verification_type,
                unit=unit,
                partial_ranges=partial_ranges,
            )
            return TestExecutionResult(
                test_run_id=test_run.test_run_id,
                test_type=test_type,
                verdict=res.verdict,
                summary=res.summary,
                calculated_values={
                    "temperatures_tested": res.temperatures_tested,
                    "max_weighing_error": res.max_weighing_error,
                    "max_drift_rate_in_e": res.max_drift_rate_in_e,
                    "unit": res.unit,
                },
                regulatory_limits={
                    "reference": "OIML R 76-1:2006 Clause 3.9.2.2 & A.5.3",
                },
                observations_evaluated=len(res.points),
                intermediate_results=[z.to_dict() for z in res.zero_drift_evaluations],
                standard_reference=STANDARD_CLAUSES[test_type],
            )

        elif test_type == TestType.CONSTRUCTION_EXAMINATION:
            checklist = [
                obs.get("checklist_item") or obs
                for obs in obs_dicts
            ]
            res = ExaminationCalculator.evaluate_construction(checklist_items=checklist)
            return TestExecutionResult(
                test_run_id=test_run.test_run_id,
                test_type=test_type,
                verdict=res.verdict,
                summary=res.summary,
                calculated_values={
                    "total_items": res.total_items,
                    "compliant_count": res.compliant_count,
                    "non_compliant_count": res.non_compliant_count,
                    "not_applicable_count": res.not_applicable_count,
                },
                regulatory_limits={
                    "reference": "OIML R 76-1:2006 Clause 3.9, Clause 4, Clause 7.1",
                },
                observations_evaluated=res.total_items,
                intermediate_results=res.non_compliant_items,
                standard_reference=STANDARD_CLAUSES[test_type],
            )

        elif test_type == TestType.SOFTWARE_EXAMINATION:
            checklist = [
                obs.get("checklist_item") or obs
                for obs in obs_dicts
            ]
            expected_ver = instrument.get("software_version") or test_run.metadata.get("expected_version")
            observed_ver = test_run.metadata.get("observed_version") or test_run.metadata.get("software_version")
            expected_hash = test_run.metadata.get("expected_hash")
            observed_hash = test_run.metadata.get("observed_hash")

            res = ExaminationCalculator.evaluate_software(
                checklist_items=checklist,
                expected_version=expected_ver,
                observed_version=observed_ver,
                expected_hash=expected_hash,
                observed_hash=observed_hash,
            )
            return TestExecutionResult(
                test_run_id=test_run.test_run_id,
                test_type=test_type,
                verdict=res.verdict,
                summary=res.summary,
                calculated_values={
                    "total_items": res.total_items,
                    "compliant_count": res.compliant_count,
                    "non_compliant_count": res.non_compliant_count,
                    "software_version_match": res.software_version_match,
                    "software_hash_match": res.software_hash_match,
                },
                regulatory_limits={
                    "reference": "OIML R 76-1:2006 Clause 5.5",
                },
                observations_evaluated=res.total_items,
                intermediate_results=res.non_compliant_items,
                standard_reference=STANDARD_CLAUSES[test_type],
            )

        raise ValueError(f"Unsupported TestType for execution: {test_type}")
