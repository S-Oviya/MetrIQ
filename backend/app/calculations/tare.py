"""
MetrIQ P4: Tare Test Calculation
================================
Person 4: Rachitha (Test Engine + Calculations Lead)

Statutory Reference:
- OIML R 76-1:2006 Clause 4.6 & Clause A.4.6 (Tare Test)
- Indian Legal Metrology (General) Rules, 2011 Seventh Schedule

Evaluates:
1. Tare setting accuracy: zero setting error with tare activated shall not exceed +/- 0.25e.
2. Net weighing performance: errors on net loads (E_net = I_net - L_net) evaluated
   against statutory net MPE limits obtained strictly from Person 2 Regulatory Engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from app.calculations.models import TestType, Verdict
from app.calculations.mpe import MPEAdapter, RegulatoryMPELimit


@dataclass
class TareSettingResult:
    """Evaluation of tare device balancing / setting operation."""
    tare_load: float
    indicated_zero: float
    turning_point_delta_l: Optional[float]
    true_zero_indication: float
    tare_setting_error: float
    statutory_limit: float
    statutory_limit_e: float
    passed: bool
    margin: float
    unit: str = "kg"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tare_load": self.tare_load,
            "indicated_zero": self.indicated_zero,
            "turning_point_delta_l": self.turning_point_delta_l,
            "true_zero_indication": self.true_zero_indication,
            "tare_setting_error": self.tare_setting_error,
            "statutory_limit": self.statutory_limit,
            "statutory_limit_e": self.statutory_limit_e,
            "passed": self.passed,
            "margin": self.margin,
            "unit": self.unit,
        }


@dataclass
class NetWeighingPointResult:
    """Evaluation of a net weighing load point with tare active."""
    step_number: int
    tare_load: float
    net_load: float
    gross_load: float
    net_indication: float
    turning_point_delta_l: Optional[float]
    true_net_indication: float
    net_error: float
    mpe_limit: RegulatoryMPELimit
    passed: bool
    margin: float
    unit: str = "kg"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "tare_load": self.tare_load,
            "net_load": self.net_load,
            "gross_load": self.gross_load,
            "net_indication": self.net_indication,
            "turning_point_delta_l": self.turning_point_delta_l,
            "true_net_indication": self.true_net_indication,
            "net_error": self.net_error,
            "mpe_limit": self.mpe_limit.to_dict(),
            "passed": self.passed,
            "margin": self.margin,
            "unit": self.unit,
        }


@dataclass
class TareTestResult:
    """Comprehensive result of tare setting and net weighing tests."""
    verdict: Verdict
    summary: str
    tare_setting: TareSettingResult
    net_points: List[NetWeighingPointResult]
    max_net_error: float
    unit: str = "kg"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "summary": self.summary,
            "tare_setting": self.tare_setting.to_dict(),
            "net_points": [p.to_dict() for p in self.net_points],
            "max_net_error": self.max_net_error,
            "unit": self.unit,
            "metadata": self.metadata,
        }


class TareCalculator:
    """
    Executes metrological calculations for NAWI Tare tests.
    """

    @classmethod
    def evaluate_tare_setting(
        cls,
        tare_load: float,
        indicated_zero: float,
        e: float,
        unit: str = "kg",
        turning_point_delta_l: Optional[float] = None,
        partial_ranges: Optional[List[Dict[str, Any]]] = None,
    ) -> TareSettingResult:
        """
        Evaluates tare setting accuracy against statutory +/- 0.25e limit.
        """
        if tare_load < 0:
            raise ValueError(f"Tare load cannot be negative: {tare_load}")
        if e <= 0:
            raise ValueError(f"Scale interval e must be strictly positive: {e}")

        effective_e = MPEAdapter.get_effective_e(tare_load, e, partial_ranges)
        if turning_point_delta_l is not None:
            true_zero = round(indicated_zero + 0.5 * effective_e - turning_point_delta_l, 9)
        else:
            true_zero = indicated_zero

        error = round(true_zero, 9)
        abs_err = abs(error)

        # Statutory limit: +/- 0.25e per OIML R 76-1 Clause 4.6.3
        limit = MPEAdapter.get_tare_setting_limit(effective_e)
        passed = abs_err <= (limit + 1e-9)
        margin = round(limit - abs_err, 9)

        return TareSettingResult(
            tare_load=tare_load,
            indicated_zero=indicated_zero,
            turning_point_delta_l=turning_point_delta_l,
            true_zero_indication=true_zero,
            tare_setting_error=error,
            statutory_limit=limit,
            statutory_limit_e=0.25,
            passed=passed,
            margin=margin,
            unit=unit,
        )

    @classmethod
    def evaluate_run(
        cls,
        tare_load: float,
        tare_setting_observation: Dict[str, Any],
        net_observations: List[Dict[str, Any]],
        accuracy_class: str,
        e: float,
        verification_type: str = "INITIAL",
        unit: str = "kg",
        partial_ranges: Optional[List[Dict[str, Any]]] = None,
    ) -> TareTestResult:
        """
        Evaluates both tare setting accuracy and net weighing points.
        """
        # 1. Evaluate tare setting
        ind_zero = float(tare_setting_observation.get("indicated_value", 0.0))
        dl_zero = (
            float(tare_setting_observation["turning_point_delta_l"])
            if tare_setting_observation.get("turning_point_delta_l") is not None
            else None
        )
        setting_res = cls.evaluate_tare_setting(
            tare_load=tare_load,
            indicated_zero=ind_zero,
            e=e,
            unit=unit,
            turning_point_delta_l=dl_zero,
            partial_ranges=partial_ranges,
        )

        # 2. Evaluate net points
        evaluated_points: List[NetWeighingPointResult] = []
        all_passed = setting_res.passed
        max_net_err = 0.0

        for idx, obs in enumerate(net_observations, start=1):
            net_ld = float(obs["applied_load"])
            gross_ld = round(tare_load + net_ld, 9)
            net_ind = float(obs["indicated_value"])
            dl = float(obs["turning_point_delta_l"]) if obs.get("turning_point_delta_l") is not None else None

            effective_e = MPEAdapter.get_effective_e(net_ld, e, partial_ranges)
            if dl is not None:
                true_net_ind = round(net_ind + 0.5 * effective_e - dl, 9)
            else:
                true_net_ind = net_ind

            net_err = round(true_net_ind - net_ld, 9)

            # Retrieve statutory MPE for net load from Person 2
            mpe_limit = MPEAdapter.get_mpe(
                load=net_ld,
                accuracy_class=accuracy_class,
                e=e,
                verification_type=verification_type,
                unit=unit,
                partial_ranges=partial_ranges,
            )

            abs_err = abs(net_err)
            passed = abs_err <= (mpe_limit.mpe_absolute + 1e-9)
            margin = round(mpe_limit.mpe_absolute - abs_err, 9)

            if not passed:
                all_passed = False

            if abs_err >= abs(max_net_err):
                max_net_err = net_err

            evaluated_points.append(
                NetWeighingPointResult(
                    step_number=obs.get("step_number", idx),
                    tare_load=tare_load,
                    net_load=net_ld,
                    gross_load=gross_ld,
                    net_indication=net_ind,
                    turning_point_delta_l=dl,
                    true_net_indication=true_net_ind,
                    net_error=net_err,
                    mpe_limit=mpe_limit,
                    passed=passed,
                    margin=margin,
                    unit=unit,
                )
            )

        verdict = Verdict.PASS if all_passed else Verdict.FAIL
        summary = (
            f"Tare Test {verdict.value}: tare setting error = {setting_res.tare_setting_error:+.4g} {unit} "
            f"(limit ±{setting_res.statutory_limit:.4g} {unit}). "
            f"{len(evaluated_points)} net points evaluated, max net error = {max_net_err:+.4g} {unit}."
        )

        return TareTestResult(
            verdict=verdict,
            summary=summary,
            tare_setting=setting_res,
            net_points=evaluated_points,
            max_net_error=max_net_err,
            unit=unit,
        )
