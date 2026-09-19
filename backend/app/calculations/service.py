"""
MetrIQ P4: Test Calculation Service Facade
==========================================
Person 4: Rachitha (Test Engine + Calculations Lead)

Provides high-level programmatic invocation interfaces for Person 1 (Team Lead),
Person 3 (Job Lifecycle), Person 5 (Workflow/Evidence), and Person 6 (Reports).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from app.calculations.engine import TestEngine
from app.calculations.models import (
    RawObservation,
    TestDefinition,
    TestExecutionResult,
    TestRun,
    TestType,
    Verdict,
)
from app.calculations.mpe import MPEAdapter, RegulatoryMPELimit


class CalculationService:
    """
    Facade service orchestrating test execution, MPE lookups via P2,
    and report data preparation.
    """

    @classmethod
    def calculate_mpe(
        cls,
        load: float,
        accuracy_class: str,
        e: float,
        verification_type: str = "INITIAL",
        unit: str = "kg",
        partial_ranges: Optional[List[Dict[str, Any]]] = None,
        tare_load: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Queries P2 MPEEngine and returns serializable MPE parameters.
        """
        limit = MPEAdapter.get_mpe(
            load=load,
            accuracy_class=accuracy_class,
            e=e,
            verification_type=verification_type,
            unit=unit,
            partial_ranges=partial_ranges,
            tare_load=tare_load,
        )
        return limit.to_dict()

    @classmethod
    def execute_test(
        cls,
        test_run_data: Dict[str, Any],
        instrument_data: Dict[str, Any],
        verification_type: str = "INITIAL",
    ) -> Dict[str, Any]:
        """
        Executes a test run against instrument metrology parameters and returns structured results.
        """
        run_obj = TestRun.from_dict(test_run_data)
        res: TestExecutionResult = TestEngine.execute(
            test_run=run_obj,
            instrument=instrument_data,
            verification_type=verification_type,
        )
        return res.to_dict()

    @classmethod
    def batch_execute_job(
        cls,
        job_id: str,
        test_runs: List[Dict[str, Any]],
        instrument_data: Dict[str, Any],
        verification_type: str = "INITIAL",
    ) -> Dict[str, Any]:
        """
        Executes all test runs scheduled for a job and produces an aggregated verdict.
        """
        results: List[Dict[str, Any]] = []
        overall_pass = True

        for run_dict in test_runs:
            run_dict["job_id"] = job_id
            res_dict = cls.execute_test(
                test_run_data=run_dict,
                instrument_data=instrument_data,
                verification_type=verification_type,
            )
            results.append(res_dict)
            if res_dict["verdict"] != "PASS":
                overall_pass = False

        final_verdict = "PASS" if overall_pass else "FAIL"
        return {
            "job_id": job_id,
            "overall_verdict": final_verdict,
            "tests_evaluated": len(results),
            "passed_count": sum(1 for r in results if r["verdict"] == "PASS"),
            "failed_count": sum(1 for r in results if r["verdict"] == "FAIL"),
            "results": results,
        }


# High-level procedural functions
def calculate_mpe_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    return CalculationService.calculate_mpe(
        load=float(payload["load"]),
        accuracy_class=payload["accuracy_class"],
        e=float(payload["e"]),
        verification_type=payload.get("verification_type", "INITIAL"),
        unit=payload.get("unit", "kg"),
        partial_ranges=payload.get("partial_ranges"),
        tare_load=float(payload.get("tare_load", 0.0)),
    )


def execute_test_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    test_run = payload["test_run"]
    instrument = payload["instrument"]
    v_type = payload.get("verification_type", "INITIAL")
    return CalculationService.execute_test(test_run, instrument, v_type)
