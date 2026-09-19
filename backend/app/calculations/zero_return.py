"""
MetrIQ P4: Zero Return Test Calculation
=======================================
Person 4: Rachitha (Test Engine + Calculations Lead)

Statutory Reference:
- OIML R 76-1:2006 Clause 4.1.2.2 & Clause A.4.4.2 (Zero Return Test)
- Indian Legal Metrology (General) Rules, 2011 Seventh Schedule

Evaluates residual zero drift after removal of a test load that has
remained on the load receptor for a specified period (e.g. 30 minutes).
Statutory Requirement:
  The zero indication upon unloading shall not vary by more than 0.5e.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from app.calculations.models import TestType, Verdict
from app.calculations.mpe import MPEAdapter


@dataclass
class ZeroReturnTestResult:
    """
    Result of a Zero Return metrological test evaluation.
    """
    verdict: Verdict
    summary: str
    initial_zero: float
    returned_zero: float
    zero_drift: float
    drift_in_e: float
    statutory_limit: float
    statutory_limit_e: float
    passed: bool
    margin: float
    load_applied: Optional[float] = None
    duration_minutes: Optional[float] = None
    unit: str = "kg"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "summary": self.summary,
            "initial_zero": self.initial_zero,
            "returned_zero": self.returned_zero,
            "zero_drift": self.zero_drift,
            "drift_in_e": self.drift_in_e,
            "statutory_limit": self.statutory_limit,
            "statutory_limit_e": self.statutory_limit_e,
            "passed": self.passed,
            "margin": self.margin,
            "load_applied": self.load_applied,
            "duration_minutes": self.duration_minutes,
            "unit": self.unit,
            "metadata": self.metadata,
        }


class ZeroReturnCalculator:
    """
    Executes metrological calculations for NAWI Zero Return tests.
    """

    @classmethod
    def evaluate(
        cls,
        initial_zero: float,
        returned_zero: float,
        e: float,
        accuracy_class: str = "CLASS_III",
        unit: str = "kg",
        load_applied: Optional[float] = None,
        duration_minutes: Optional[float] = 30.0,
        turning_point_initial: Optional[float] = None,
        turning_point_returned: Optional[float] = None,
        partial_ranges: Optional[List[Dict[str, Any]]] = None,
    ) -> ZeroReturnTestResult:
        """
        Calculates zero drift and evaluates compliance against statutory 0.5e limit.
        """
        if e <= 0:
            raise ValueError(f"Scale interval e must be strictly positive: {e}")

        effective_e = MPEAdapter.get_effective_e(0.0, e, partial_ranges)

        # Apply turning point corrections if provided
        true_initial = (
            round(initial_zero + 0.5 * effective_e - turning_point_initial, 9)
            if turning_point_initial is not None
            else initial_zero
        )
        true_returned = (
            round(returned_zero + 0.5 * effective_e - turning_point_returned, 9)
            if turning_point_returned is not None
            else returned_zero
        )

        zero_drift = round(true_returned - true_initial, 9)
        abs_drift = abs(zero_drift)
        drift_in_e = round(abs_drift / effective_e, 4)

        # Statutory limit: 0.5e per OIML R 76-1 Clause 4.1.2.2
        statutory_limit = MPEAdapter.get_zero_drift_limit(effective_e)
        statutory_limit_e = 0.5

        passed = abs_drift <= (statutory_limit + 1e-9)
        margin = round(statutory_limit - abs_drift, 9)
        verdict = Verdict.PASS if passed else Verdict.FAIL

        summary = (
            f"Zero Return {verdict.value}: drift = {zero_drift:+.4g} {unit} ({drift_in_e:.2f}e) "
            f"against limit ±{statutory_limit:.4g} {unit} (±{statutory_limit_e}e) "
            f"after unloading from {load_applied or 'Max'} {unit}."
        )

        return ZeroReturnTestResult(
            verdict=verdict,
            summary=summary,
            initial_zero=true_initial,
            returned_zero=true_returned,
            zero_drift=zero_drift,
            drift_in_e=drift_in_e,
            statutory_limit=statutory_limit,
            statutory_limit_e=statutory_limit_e,
            passed=passed,
            margin=margin,
            load_applied=load_applied,
            duration_minutes=duration_minutes,
            unit=unit,
        )

    @classmethod
    def evaluate_run(
        cls,
        observations: List[Dict[str, Any]],
        e: float,
        accuracy_class: str = "CLASS_III",
        unit: str = "kg",
        partial_ranges: Optional[List[Dict[str, Any]]] = None,
    ) -> ZeroReturnTestResult:
        """
        Evaluates zero return from a list of observations (initial zero reading and final zero reading).
        """
        if len(observations) < 2:
            raise ValueError(
                f"Zero return requires at least 2 observations (initial zero and returned zero); received {len(observations)}."
            )

        obs_initial = observations[0]
        obs_returned = observations[-1]

        init_val = float(obs_initial.get("indicated_value") if obs_initial.get("indicated_value") is not None else 0.0)
        ret_val = float(obs_returned.get("indicated_value") if obs_returned.get("indicated_value") is not None else 0.0)
        tp_init = float(obs_initial["turning_point_delta_l"]) if obs_initial.get("turning_point_delta_l") is not None else None
        tp_ret = float(obs_returned["turning_point_delta_l"]) if obs_returned.get("turning_point_delta_l") is not None else None
        load_applied = float(obs_initial.get("applied_load")) if obs_initial.get("applied_load") is not None else None
        raw_dur = obs_returned.get("time_seconds")
        dur = (float(raw_dur) / 60.0) if raw_dur is not None else 30.0

        return cls.evaluate(
            initial_zero=init_val,
            returned_zero=ret_val,
            e=e,
            accuracy_class=accuracy_class,
            unit=unit,
            load_applied=load_applied,
            duration_minutes=dur,
            turning_point_initial=tp_init,
            turning_point_returned=tp_ret,
            partial_ranges=partial_ranges,
        )
