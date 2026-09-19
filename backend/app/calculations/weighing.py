"""
MetrIQ P4: Weighing Performance Test Calculation
=================================================
Person 4: Rachitha (Test Engine + Calculations Lead)

Statutory Reference:
- OIML R 76-1:2006 Clause A.4.8 (Weighing Test)
- Indian Legal Metrology (General) Rules, 2011 Seventh Schedule

Calculates errors of indication for increasing and decreasing test loads,
supports turning-point interpolation (P = I + 0.5e - delta_L),
evaluates hysteresis (reversal error), and determines PASS/FAIL against
statutory MPE limits obtained strictly from Person 2 Regulatory Engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from app.calculations.models import TestType, Verdict
from app.calculations.mpe import MPEAdapter, RegulatoryMPELimit


@dataclass
class WeighingPointResult:
    """
    Evaluation result for a single weighing test load point.
    """
    step_number: int
    load: float
    indicated_value: float
    turning_point_delta_l: Optional[float]
    true_indication: float
    raw_error: float
    zero_error_correction: float
    corrected_error: float
    direction: str  # "INCREASING", "DECREASING", "STATIC"
    mpe_limit: RegulatoryMPELimit
    passed: bool
    margin: float
    unit: str = "kg"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "load": self.load,
            "indicated_value": self.indicated_value,
            "turning_point_delta_l": self.turning_point_delta_l,
            "true_indication": self.true_indication,
            "raw_error": self.raw_error,
            "zero_error_correction": self.zero_error_correction,
            "corrected_error": self.corrected_error,
            "direction": self.direction,
            "mpe_limit": self.mpe_limit.to_dict(),
            "passed": self.passed,
            "margin": self.margin,
            "unit": self.unit,
        }


@dataclass
class WeighingTestResult:
    """
    Comprehensive result of a full weighing performance test run.
    """
    verdict: Verdict
    summary: str
    points: List[WeighingPointResult]
    max_error: float
    max_error_load: float
    max_hysteresis: Optional[float]
    unit: str = "kg"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "summary": self.summary,
            "points": [p.to_dict() for p in self.points],
            "max_error": self.max_error,
            "max_error_load": self.max_error_load,
            "max_hysteresis": self.max_hysteresis,
            "unit": self.unit,
            "metadata": self.metadata,
        }


class WeighingPerformanceCalculator:
    """
    Executes metrological calculations for NAWI Weighing Performance tests.
    """

    @classmethod
    def calculate_single_point(
        cls,
        load: float,
        indicated_value: float,
        accuracy_class: str,
        e: float,
        verification_type: str = "INITIAL",
        unit: str = "kg",
        step_number: int = 1,
        turning_point_delta_l: Optional[float] = None,
        zero_error: float = 0.0,
        direction: str = "INCREASING",
        partial_ranges: Optional[List[Dict[str, Any]]] = None,
    ) -> WeighingPointResult:
        """
        Calculates error and evaluates compliance for a single load application.
        """
        if load < 0:
            raise ValueError(f"Test load cannot be negative: {load}")
        if e <= 0:
            raise ValueError(f"Scale interval e must be strictly positive: {e}")

        # Turning point calculation per OIML R 76-1 A.4.4.3:
        # P = I + 0.5e - delta_L
        effective_e = MPEAdapter.get_effective_e(load, e, partial_ranges)
        if turning_point_delta_l is not None:
            if turning_point_delta_l < 0:
                raise ValueError(f"Turning point delta_L cannot be negative: {turning_point_delta_l}")
            true_indication = round(indicated_value + 0.5 * effective_e - turning_point_delta_l, 9)
        else:
            true_indication = indicated_value

        raw_error = round(true_indication - load, 9)
        corrected_error = round(raw_error - zero_error, 9)

        # Retrieve statutory limit from Person 2
        mpe_limit = MPEAdapter.get_mpe(
            load=load,
            accuracy_class=accuracy_class,
            e=e,
            verification_type=verification_type,
            unit=unit,
            partial_ranges=partial_ranges,
        )

        abs_err = abs(corrected_error)
        passed = abs_err <= (mpe_limit.mpe_absolute + 1e-9)
        margin = round(mpe_limit.mpe_absolute - abs_err, 9)

        return WeighingPointResult(
            step_number=step_number,
            load=load,
            indicated_value=indicated_value,
            turning_point_delta_l=turning_point_delta_l,
            true_indication=true_indication,
            raw_error=raw_error,
            zero_error_correction=zero_error,
            corrected_error=corrected_error,
            direction=direction.upper(),
            mpe_limit=mpe_limit,
            passed=passed,
            margin=margin,
            unit=unit,
        )

    @classmethod
    def evaluate_run(
        cls,
        observations: List[Dict[str, Any]],
        accuracy_class: str,
        e: float,
        verification_type: str = "INITIAL",
        unit: str = "kg",
        partial_ranges: Optional[List[Dict[str, Any]]] = None,
    ) -> WeighingTestResult:
        """
        Evaluates a complete sequence of weighing points (e.g. ascending & descending).
        """
        if not observations:
            raise ValueError("Observations list cannot be empty for weighing test evaluation.")

        # Find zero error from initial zero reading if provided
        initial_zero_err = 0.0
        for obs in observations:
            if float(obs.get("applied_load", 0.0)) == 0.0:
                ind = float(obs.get("indicated_value", 0.0))
                dl = obs.get("turning_point_delta_l")
                eff_e = MPEAdapter.get_effective_e(0.0, e, partial_ranges)
                if dl is not None:
                    initial_zero_err = round(ind + 0.5 * eff_e - float(dl), 9)
                else:
                    initial_zero_err = ind
                break

        evaluated_points: List[WeighingPointResult] = []
        all_passed = True
        max_error = 0.0
        max_error_load = 0.0

        # Group by load to calculate hysteresis
        increasing_errors: Dict[float, float] = {}
        decreasing_errors: Dict[float, float] = {}

        for idx, obs in enumerate(observations, start=1):
            load = float(obs["applied_load"])
            ind = float(obs["indicated_value"])
            dl = float(obs["turning_point_delta_l"]) if obs.get("turning_point_delta_l") is not None else None
            direction = str(obs.get("direction", "INCREASING")).upper()

            point_res = cls.calculate_single_point(
                load=load,
                indicated_value=ind,
                accuracy_class=accuracy_class,
                e=e,
                verification_type=verification_type,
                unit=unit,
                step_number=obs.get("step_number", idx),
                turning_point_delta_l=dl,
                zero_error=initial_zero_err,
                direction=direction,
                partial_ranges=partial_ranges,
            )
            evaluated_points.append(point_res)

            if not point_res.passed:
                all_passed = False

            if abs(point_res.corrected_error) > abs(max_error):
                max_error = point_res.corrected_error
                max_error_load = load

            if direction == "INCREASING":
                increasing_errors[load] = point_res.corrected_error
            elif direction == "DECREASING":
                decreasing_errors[load] = point_res.corrected_error

        # Compute max hysteresis where matching loads exist
        max_hysteresis = None
        common_loads = set(increasing_errors.keys()) & set(decreasing_errors.keys())
        if common_loads:
            max_hysteresis = max(abs(increasing_errors[ld] - decreasing_errors[ld]) for ld in common_loads)
            max_hysteresis = round(max_hysteresis, 9)

        verdict = Verdict.PASS if all_passed else Verdict.FAIL
        summary = (
            f"Weighing Performance {verdict.value}: {len(evaluated_points)} points evaluated. "
            f"Max error = {max_error:+.4g} {unit} at {max_error_load} {unit}."
        )
        if max_hysteresis is not None:
            summary += f" Max hysteresis = {max_hysteresis:.4g} {unit}."

        return WeighingTestResult(
            verdict=verdict,
            summary=summary,
            points=evaluated_points,
            max_error=max_error,
            max_error_load=max_error_load,
            max_hysteresis=max_hysteresis,
            unit=unit,
        )
