"""
MetrIQ P4: Temperature Effect Test Calculation
==============================================
Person 4: Rachitha (Test Engine + Calculations Lead)

Statutory Reference:
- OIML R 76-1:2006 Clause 3.9.2.2 & Clause A.5.3 (Static Temperature Test)
- Indian Legal Metrology (General) Rules, 2011 Seventh Schedule

Evaluates metrological stability under extreme operating temperatures:
1. Error of indication at each temperature must stay within statutory MPE
   obtained strictly from Person 2 Regulatory Engine.
2. Temperature zero drift rate:
   - Class II, III, IIII: <= 1e per 5 °C (0.2e / °C)
   - Class I: <= 1e per 1 °C
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from app.calculations.models import TestType, Verdict
from app.calculations.mpe import MPEAdapter, RegulatoryMPELimit


@dataclass
class TemperatureChamberPoint:
    """Weighing or zero measurement taken at a specific chamber temperature."""
    temperature_c: float
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
            "temperature_c": self.temperature_c,
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
class ZeroDriftPairResult:
    """Evaluation of zero drift rate between two temperatures."""
    temp_1_c: float
    zero_1: float
    temp_2_c: float
    zero_2: float
    temp_diff_c: float
    zero_shift: float
    drift_rate_per_c: float
    drift_rate_in_e_per_c: float
    statutory_limit_per_c: float
    statutory_limit_in_e_per_c: float
    passed: bool
    unit: str = "kg"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "temp_1_c": self.temp_1_c,
            "zero_1": self.zero_1,
            "temp_2_c": self.temp_2_c,
            "zero_2": self.zero_2,
            "temp_diff_c": self.temp_diff_c,
            "zero_shift": self.zero_shift,
            "drift_rate_per_c": self.drift_rate_per_c,
            "drift_rate_in_e_per_c": self.drift_rate_in_e_per_c,
            "statutory_limit_per_c": self.statutory_limit_per_c,
            "statutory_limit_in_e_per_c": self.statutory_limit_in_e_per_c,
            "passed": self.passed,
            "unit": self.unit,
        }


@dataclass
class TemperatureTestResult:
    """Overall result of static temperature test evaluation."""
    verdict: Verdict
    summary: str
    points: List[TemperatureChamberPoint]
    zero_drift_evaluations: List[ZeroDriftPairResult]
    temperatures_tested: List[float]
    max_weighing_error: float
    max_drift_rate_in_e: float
    unit: str = "kg"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "summary": self.summary,
            "points": [p.to_dict() for p in self.points],
            "zero_drift_evaluations": [z.to_dict() for z in self.zero_drift_evaluations],
            "temperatures_tested": self.temperatures_tested,
            "max_weighing_error": self.max_weighing_error,
            "max_drift_rate_in_e": self.max_drift_rate_in_e,
            "unit": self.unit,
            "metadata": self.metadata,
        }


class TemperatureCalculator:
    """
    Executes metrological calculations for NAWI Static Temperature tests.
    """

    @classmethod
    def get_statutory_zero_drift_limit_per_c(cls, accuracy_class: str, e: float) -> tuple[float, float]:
        """
        Returns (limit_in_engineering_units, limit_in_e_per_deg_c).
        Per OIML R 76-1 Clause 3.9.2.2:
        - Class I: 1e per 1 °C
        - Class II, III, IIII: 1e per 5 °C = 0.2e per °C
        """
        clean_class = str(accuracy_class).upper()
        if "CLASS_I" in clean_class and "CLASS_II" not in clean_class and "CLASS_III" not in clean_class and "CLASS_IIII" not in clean_class:
            limit_e = 1.0
        else:
            limit_e = 0.2  # 1e / 5°C

        return round(limit_e * e, 9), limit_e

    @classmethod
    def evaluate(
        cls,
        observations: List[Dict[str, Any]],
        accuracy_class: str,
        e: float,
        verification_type: str = "INITIAL",
        unit: str = "kg",
        partial_ranges: Optional[List[Dict[str, Any]]] = None,
    ) -> TemperatureTestResult:
        """
        Evaluates temperature chamber observations including weighing errors and zero drift rates.
        """
        if not observations:
            raise ValueError("Observations list cannot be empty for temperature test evaluation.")

        evaluated_points: List[TemperatureChamberPoint] = []
        zero_readings_by_temp: Dict[float, float] = {}
        all_passed = True
        max_error = 0.0

        # 1. Evaluate weighing and zero points across temperatures
        for obs in observations:
            raw_temp = obs.get("temperature_c")
            temp_c = float(raw_temp) if raw_temp is not None else 20.0
            raw_load = obs.get("applied_load")
            load = float(raw_load) if raw_load is not None else 0.0
            ind = float(obs["indicated_value"])
            dl = float(obs["turning_point_delta_l"]) if obs.get("turning_point_delta_l") is not None else None

            effective_e = MPEAdapter.get_effective_e(load, e, partial_ranges)
            if dl is not None:
                true_ind = round(ind + 0.5 * effective_e - dl, 9)
            else:
                true_ind = ind

            err = round(true_ind - load, 9)

            if load == 0.0:
                zero_readings_by_temp[temp_c] = true_ind

            # Retrieve statutory limit from Person 2
            mpe_limit = MPEAdapter.get_mpe(
                load=load,
                accuracy_class=accuracy_class,
                e=e,
                verification_type=verification_type,
                unit=unit,
                partial_ranges=partial_ranges,
            )

            abs_err = abs(err)
            pt_passed = abs_err <= (mpe_limit.mpe_absolute + 1e-9)
            margin = round(mpe_limit.mpe_absolute - abs_err, 9)

            if not pt_passed:
                all_passed = False

            if abs_err >= abs(max_error):
                max_error = err

            evaluated_points.append(
                TemperatureChamberPoint(
                    temperature_c=temp_c,
                    load=load,
                    indicated_value=ind,
                    turning_point_delta_l=dl,
                    true_indication=true_ind,
                    error=err,
                    mpe_limit=mpe_limit,
                    passed=pt_passed,
                    margin=margin,
                    unit=unit,
                )
            )

        # 2. Evaluate temperature zero drift between distinct temperature steps
        zero_evals: List[ZeroDriftPairResult] = []
        limit_units, limit_e_per_c = cls.get_statutory_zero_drift_limit_per_c(accuracy_class, e)
        temps = sorted(zero_readings_by_temp.keys())
        max_drift_rate_in_e = 0.0

        for i in range(len(temps) - 1):
            t1 = temps[i]
            t2 = temps[i + 1]
            z1 = zero_readings_by_temp[t1]
            z2 = zero_readings_by_temp[t2]
            delta_t = abs(t2 - t1)

            if delta_t > 0:
                shift = abs(round(z2 - z1, 9))
                rate_per_c = round(shift / delta_t, 9)
                rate_in_e = round(rate_per_c / e, 4)
                pair_passed = rate_per_c <= (limit_units + 1e-9)

                if not pair_passed:
                    all_passed = False

                if rate_in_e > max_drift_rate_in_e:
                    max_drift_rate_in_e = rate_in_e

                zero_evals.append(
                    ZeroDriftPairResult(
                        temp_1_c=t1,
                        zero_1=z1,
                        temp_2_c=t2,
                        zero_2=z2,
                        temp_diff_c=delta_t,
                        zero_shift=shift,
                        drift_rate_per_c=rate_per_c,
                        drift_rate_in_e_per_c=rate_in_e,
                        statutory_limit_per_c=limit_units,
                        statutory_limit_in_e_per_c=limit_e_per_c,
                        passed=pair_passed,
                        unit=unit,
                    )
                )

        verdict = Verdict.PASS if all_passed else Verdict.FAIL
        summary = (
            f"Temperature Effect {verdict.value}: evaluated across {len(temps)} temperatures {temps} °C. "
            f"Max weighing error = {max_error:+.4g} {unit}. "
            f"Max zero drift rate = {max_drift_rate_in_e:.4g}e / °C (statutory limit {limit_e_per_c}e / °C)."
        )

        return TemperatureTestResult(
            verdict=verdict,
            summary=summary,
            points=evaluated_points,
            zero_drift_evaluations=zero_evals,
            temperatures_tested=temps,
            max_weighing_error=max_error,
            max_drift_rate_in_e=max_drift_rate_in_e,
            unit=unit,
        )
