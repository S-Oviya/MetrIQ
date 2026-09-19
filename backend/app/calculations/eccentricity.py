"""
MetrIQ P4: Eccentricity Test Calculation
========================================
Person 4: Rachitha (Test Engine + Calculations Lead)

Statutory Reference:
- OIML R 76-1:2006 Clause A.4.7 (Eccentricity Test)
- Indian Legal Metrology (General) Rules, 2011 Seventh Schedule

Evaluates off-center loading on weighing instruments with various load
receptor geometries (standard platter <= 4 supports, > 4 points, rolling loads).
Determines position errors, maximum indication spread between positions,
and evaluates compliance against statutory MPE limits from Person 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from app.calculations.models import TestType, Verdict
from app.calculations.mpe import MPEAdapter, RegulatoryMPELimit


@dataclass
class EccentricityPositionResult:
    """
    Evaluation result for a specific load receptor position.
    """
    position: str
    load: float
    indicated_value: float
    turning_point_delta_l: Optional[float]
    true_indication: float
    error: float
    mpe_limit: RegulatoryMPELimit
    passed: bool
    margin: float
    unit: str = "kg"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position": self.position,
            "load": self.load,
            "indicated_value": self.indicated_value,
            "turning_point_delta_l": self.turning_point_delta_l,
            "true_indication": self.true_indication,
            "error": self.error,
            "mpe_limit": self.mpe_limit.to_dict(),
            "passed": self.passed,
            "margin": self.margin,
            "unit": self.unit,
        }


@dataclass
class EccentricityTestResult:
    """
    Comprehensive result of an eccentricity test evaluation.
    """
    verdict: Verdict
    summary: str
    positions: List[EccentricityPositionResult]
    max_error: float
    worst_position: str
    max_position_difference: float
    unit: str = "kg"
    receptor_type: str = "STANDARD_PLATTER"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "summary": self.summary,
            "positions": [p.to_dict() for p in self.positions],
            "max_error": self.max_error,
            "worst_position": self.worst_position,
            "max_position_difference": self.max_position_difference,
            "unit": self.unit,
            "receptor_type": self.receptor_type,
            "metadata": self.metadata,
        }


class EccentricityCalculator:
    """
    Executes metrological calculations for NAWI Eccentricity tests.
    """

    @classmethod
    def evaluate(
        cls,
        observations: List[Dict[str, Any]],
        accuracy_class: str,
        e: float,
        verification_type: str = "INITIAL",
        unit: str = "kg",
        receptor_type: str = "STANDARD_PLATTER",
        partial_ranges: Optional[List[Dict[str, Any]]] = None,
    ) -> EccentricityTestResult:
        """
        Evaluates eccentricity observations across all load receptor positions.
        """
        if not observations:
            raise ValueError("Observations list cannot be empty for eccentricity evaluation.")

        positions_evaluated: List[EccentricityPositionResult] = []
        all_passed = True
        max_error = 0.0
        worst_pos = "CENTER"
        indications: List[float] = []

        for idx, obs in enumerate(observations, start=1):
            load = float(obs["applied_load"])
            ind = float(obs["indicated_value"])
            pos = str(obs.get("position") or f"POSITION_{idx}").upper()
            dl = float(obs["turning_point_delta_l"]) if obs.get("turning_point_delta_l") is not None else None

            effective_e = MPEAdapter.get_effective_e(load, e, partial_ranges)
            if dl is not None:
                if dl < 0:
                    raise ValueError(f"Turning point delta_L cannot be negative: {dl}")
                true_indication = round(ind + 0.5 * effective_e - dl, 9)
            else:
                true_indication = ind

            error = round(true_indication - load, 9)
            indications.append(true_indication)

            # Retrieve statutory limit from Person 2
            mpe_limit = MPEAdapter.get_mpe(
                load=load,
                accuracy_class=accuracy_class,
                e=e,
                verification_type=verification_type,
                unit=unit,
                partial_ranges=partial_ranges,
            )

            abs_err = abs(error)
            passed = abs_err <= (mpe_limit.mpe_absolute + 1e-9)
            margin = round(mpe_limit.mpe_absolute - abs_err, 9)

            if not passed:
                all_passed = False

            if abs_err >= abs(max_error):
                max_error = error
                worst_pos = pos

            positions_evaluated.append(
                EccentricityPositionResult(
                    position=pos,
                    load=load,
                    indicated_value=ind,
                    turning_point_delta_l=dl,
                    true_indication=true_indication,
                    error=error,
                    mpe_limit=mpe_limit,
                    passed=passed,
                    margin=margin,
                    unit=unit,
                )
            )

        max_diff = round(max(indications) - min(indications), 9) if indications else 0.0
        verdict = Verdict.PASS if all_passed else Verdict.FAIL

        summary = (
            f"Eccentricity {verdict.value}: {len(positions_evaluated)} positions tested on {receptor_type}. "
            f"Max error = {max_error:+.4g} {unit} at {worst_pos}. "
            f"Max difference between positions = {max_diff:.4g} {unit}."
        )

        return EccentricityTestResult(
            verdict=verdict,
            summary=summary,
            positions=positions_evaluated,
            max_error=max_error,
            worst_position=worst_pos,
            max_position_difference=max_diff,
            unit=unit,
            receptor_type=receptor_type,
        )
