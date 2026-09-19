"""
MetrIQ P4: Creep Test Calculation
=================================
Person 4: Rachitha (Test Engine + Calculations Lead)

Statutory Reference:
- OIML R 76-1:2006 Clause 4.1.2.1 & Clause A.4.4.1 (Creep Test)
- Indian Legal Metrology (General) Rules, 2011 Seventh Schedule

Evaluates time-dependent indication drift under constant test load:
1. Total creep between initial indication (approx 5s) and 30 minutes:
   |I(30 min) - I(5s)| <= 0.5e
2. Transient creep between 15 minutes and 30 minutes:
   |I(30 min) - I(15 min)| <= 0.2e
3. Error of indication at any time must not exceed MPE from Person 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from app.calculations.models import TestType, Verdict
from app.calculations.mpe import MPEAdapter, RegulatoryMPELimit


@dataclass
class CreepTimeObservation:
    """A reading taken at a specific elapsed time under constant load."""
    time_seconds: float
    time_minutes: float
    indicated_value: float
    turning_point_delta_l: Optional[float]
    true_indication: float
    error_from_load: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "time_seconds": self.time_seconds,
            "time_minutes": self.time_minutes,
            "indicated_value": self.indicated_value,
            "turning_point_delta_l": self.turning_point_delta_l,
            "true_indication": self.true_indication,
            "error_from_load": self.error_from_load,
        }


@dataclass
class CreepTestResult:
    """
    Comprehensive result of a Creep Test evaluation.
    """
    verdict: Verdict
    summary: str
    load: float
    time_points: List[CreepTimeObservation]
    total_creep: float
    total_creep_in_e: float
    total_creep_limit: float
    total_creep_passed: bool
    transient_creep: Optional[float]
    transient_creep_in_e: Optional[float]
    transient_creep_limit: Optional[float]
    transient_creep_passed: bool
    mpe_limit: RegulatoryMPELimit
    max_error_passed: bool
    unit: str = "kg"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "summary": self.summary,
            "load": self.load,
            "time_points": [tp.to_dict() for tp in self.time_points],
            "total_creep": self.total_creep,
            "total_creep_in_e": self.total_creep_in_e,
            "total_creep_limit": self.total_creep_limit,
            "total_creep_passed": self.total_creep_passed,
            "transient_creep": self.transient_creep,
            "transient_creep_in_e": self.transient_creep_in_e,
            "transient_creep_limit": self.transient_creep_limit,
            "transient_creep_passed": self.transient_creep_passed,
            "mpe_limit": self.mpe_limit.to_dict(),
            "max_error_passed": self.max_error_passed,
            "unit": self.unit,
            "metadata": self.metadata,
        }


class CreepCalculator:
    """
    Executes metrological calculations for NAWI Creep tests.
    """

    @classmethod
    def evaluate(
        cls,
        load: float,
        time_observations: List[Dict[str, Any]],
        accuracy_class: str,
        e: float,
        verification_type: str = "INITIAL",
        unit: str = "kg",
        partial_ranges: Optional[List[Dict[str, Any]]] = None,
    ) -> CreepTestResult:
        """
        Evaluates creep time series under constant load.
        """
        if len(time_observations) < 2:
            raise ValueError(
                f"Creep test requires at least 2 time observations (e.g., initial and 30 min); received {len(time_observations)}."
            )

        effective_e = MPEAdapter.get_effective_e(load, e, partial_ranges)
        creep_limits = MPEAdapter.get_creep_limits(effective_e)

        parsed_points: List[CreepTimeObservation] = []
        for obs in time_observations:
            raw_time = obs.get("time_seconds")
            t_sec = float(raw_time) if raw_time is not None else 0.0
            ind = float(obs["indicated_value"])
            dl = float(obs["turning_point_delta_l"]) if obs.get("turning_point_delta_l") is not None else None
            if dl is not None:
                true_ind = round(ind + 0.5 * effective_e - dl, 9)
            else:
                true_ind = ind
            err = round(true_ind - load, 9)

            parsed_points.append(
                CreepTimeObservation(
                    time_seconds=t_sec,
                    time_minutes=round(t_sec / 60.0, 2),
                    indicated_value=ind,
                    turning_point_delta_l=dl,
                    true_indication=true_ind,
                    error_from_load=err,
                )
            )

        # Sort by elapsed time
        parsed_points.sort(key=lambda p: p.time_seconds)

        initial_pt = parsed_points[0]
        final_pt = parsed_points[-1]

        # Total creep: I(final) - I(initial)
        total_creep = round(final_pt.true_indication - initial_pt.true_indication, 9)
        abs_total = abs(total_creep)
        total_creep_in_e = round(abs_total / effective_e, 4)
        total_limit = creep_limits["total_creep_limit"]
        total_passed = abs_total <= (total_limit + 1e-9)

        # Transient creep: between 15 min (900s) and 30 min (1800s) if present
        pt_15m = None
        for pt in parsed_points:
            if 800 <= pt.time_seconds <= 1000:
                pt_15m = pt
                break

        transient_creep = None
        transient_in_e = None
        transient_limit = None
        transient_passed = True

        if pt_15m is not None and final_pt.time_seconds >= 1700:
            transient_creep = round(final_pt.true_indication - pt_15m.true_indication, 9)
            abs_trans = abs(transient_creep)
            transient_in_e = round(abs_trans / effective_e, 4)
            transient_limit = creep_limits["transient_creep_limit"]
            transient_passed = abs_trans <= (transient_limit + 1e-9)

        # Verify all indications are within MPE from Person 2
        mpe_limit = MPEAdapter.get_mpe(
            load=load,
            accuracy_class=accuracy_class,
            e=e,
            verification_type=verification_type,
            unit=unit,
            partial_ranges=partial_ranges,
        )
        max_err_passed = all(abs(p.error_from_load) <= (mpe_limit.mpe_absolute + 1e-9) for p in parsed_points)

        all_passed = total_passed and transient_passed and max_err_passed
        verdict = Verdict.PASS if all_passed else Verdict.FAIL

        summary = (
            f"Creep {verdict.value}: total creep = {total_creep:+.4g} {unit} ({total_creep_in_e:.2f}e) "
            f"vs limit ±{total_limit:.4g} {unit} (±0.5e)."
        )
        if transient_creep is not None:
            summary += (
                f" Transient creep (15-30 min) = {transient_creep:+.4g} {unit} ({transient_in_e:.2f}e) "
                f"vs limit ±{transient_limit:.4g} {unit} (±0.2e)."
            )

        return CreepTestResult(
            verdict=verdict,
            summary=summary,
            load=load,
            time_points=parsed_points,
            total_creep=total_creep,
            total_creep_in_e=total_creep_in_e,
            total_creep_limit=total_limit,
            total_creep_passed=total_passed,
            transient_creep=transient_creep,
            transient_creep_in_e=transient_in_e,
            transient_creep_limit=transient_limit,
            transient_creep_passed=transient_passed,
            mpe_limit=mpe_limit,
            max_error_passed=max_err_passed,
            unit=unit,
        )
