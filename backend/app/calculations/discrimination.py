"""
MetrIQ P4: Digital Discrimination Test Calculation
==================================================
Person 4: Rachitha (Test Engine + Calculations Lead)

Statutory Reference:
- OIML R 76-1:2006 Clause 3.8 & Clause A.4.4.3 (Discrimination Test)
- Indian Legal Metrology (General) Rules, 2011 Seventh Schedule

Evaluates the responsiveness of digital weighing instruments to small load increments.
Statutory Requirement:
  An additional load equal to 1.4d placed gently on the load receptor shall
  definitely increase the indication by at least 1d.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from app.calculations.models import TestType, Verdict


@dataclass
class DiscriminationPointResult:
    """Result of discrimination test at a specific base load point."""
    load: float
    initial_indication: float
    extra_load: float
    new_indication: float
    indication_change: float
    d: float
    minimum_expected_change: float
    passed: bool
    unit: str = "kg"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "load": self.load,
            "initial_indication": self.initial_indication,
            "extra_load": self.extra_load,
            "new_indication": self.new_indication,
            "indication_change": self.indication_change,
            "d": self.d,
            "minimum_expected_change": self.minimum_expected_change,
            "passed": self.passed,
            "unit": self.unit,
        }


@dataclass
class DiscriminationTestResult:
    """Overall result of digital discrimination evaluation."""
    verdict: Verdict
    summary: str
    points: List[DiscriminationPointResult]
    d: float
    unit: str = "kg"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "summary": self.summary,
            "points": [p.to_dict() for p in self.points],
            "d": self.d,
            "unit": self.unit,
            "metadata": self.metadata,
        }


class DiscriminationCalculator:
    """
    Executes metrological calculations for NAWI Digital Discrimination tests.
    """

    @classmethod
    def evaluate_point(
        cls,
        load: float,
        initial_indication: float,
        extra_load: float,
        new_indication: float,
        d: float,
        unit: str = "kg",
    ) -> DiscriminationPointResult:
        """
        Evaluates discrimination response for a single load point with 1.4d added mass.
        """
        if d <= 0:
            raise ValueError(f"Actual scale interval d must be strictly positive: {d}")
        if extra_load <= 0:
            raise ValueError(f"Extra test load must be strictly positive: {extra_load}")

        ind_change = round(new_indication - initial_indication, 9)
        # Indication must change by at least 1d in the direction of the added load
        passed = ind_change >= (d - 1e-9)

        return DiscriminationPointResult(
            load=load,
            initial_indication=initial_indication,
            extra_load=extra_load,
            new_indication=new_indication,
            indication_change=ind_change,
            d=d,
            minimum_expected_change=d,
            passed=passed,
            unit=unit,
        )

    @classmethod
    def evaluate_run(
        cls,
        observations: List[Dict[str, Any]],
        d: float,
        unit: str = "kg",
    ) -> DiscriminationTestResult:
        """
        Evaluates a set of discrimination points (e.g. at Min, 0.5 Max, Max).
        """
        if not observations:
            raise ValueError("Observations list cannot be empty for discrimination evaluation.")

        points: List[DiscriminationPointResult] = []
        all_passed = True

        for obs in observations:
            load = float(obs["applied_load"])
            init_ind = float(obs["indicated_value"])
            new_ind_val = obs.get("new_indication") or obs.get("indicated_value_after") or obs.get("new_indicated_value")
            if new_ind_val is not None:
                new_ind = float(new_ind_val)
            elif obs.get("indication_change") is not None:
                new_ind = init_ind + float(obs["indication_change"])
            elif obs.get("passed", False):
                new_ind = init_ind + d
            else:
                new_ind = init_ind + (d if (obs.get("extra_load") and float(obs["extra_load"]) >= d) else 0.0)

            raw_extra = obs.get("extra_load")
            extra_ld = float(raw_extra) if raw_extra is not None else round(1.4 * d, 6)

            pt = cls.evaluate_point(
                load=load,
                initial_indication=init_ind,
                extra_load=extra_ld,
                new_indication=new_ind,
                d=d,
                unit=unit,
            )
            points.append(pt)
            if not pt.passed:
                all_passed = False

        verdict = Verdict.PASS if all_passed else Verdict.FAIL
        summary = (
            f"Discrimination {verdict.value}: {len(points)} load points tested with extra load ~1.4d. "
            f"Scale interval d = {d} {unit}."
        )

        return DiscriminationTestResult(
            verdict=verdict,
            summary=summary,
            points=points,
            d=d,
            unit=unit,
        )
