"""
MetrIQ P4: Regulatory MPE Adapter
=================================
Person 4: Rachitha (Test Engine + Calculations Lead)

Adapter consuming Maximum Permissible Error (MPE) calculations strictly
from Person 2's Regulatory Engine (app.regulatory.mpe_engine.MPEEngine
and app.regulatory.mpe).

CRITICAL REQUIREMENT:
Zero duplicate regulatory tables or statutory constants are defined here.
All statutory limits, bands, and verification multipliers are delegated to P2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

# Consume Person 2 canonical types and engines
from app.regulatory.models import (
    AccuracyClass,
    InstrumentProfile,
    JobType,
    MassUnit,
    MPEValue,
    WeighingRange,
)
from app.regulatory.mpe_engine import (
    MPECalculationResult,
    MPEEngine,
    VerificationType,
)
from app.regulatory.mpe import (
    calculate_mpe as p2_calculate_mpe,
    get_effective_e_for_load,
)


@dataclass(frozen=True)
class RegulatoryMPELimit:
    """
    Typed MPE specification retrieved from Person 2 Regulatory Engine.
    """
    load: float
    load_in_e: float
    e: float
    accuracy_class: str
    verification_type: str
    mpe_in_e: float
    mpe_absolute: float
    lower_limit: float
    upper_limit: float
    band_description: str
    reference_clause: str
    unit: str = "kg"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "load": self.load,
            "load_in_e": self.load_in_e,
            "e": self.e,
            "accuracy_class": self.accuracy_class,
            "verification_type": self.verification_type,
            "mpe_in_e": self.mpe_in_e,
            "mpe_absolute": self.mpe_absolute,
            "lower_limit": self.lower_limit,
            "upper_limit": self.upper_limit,
            "band_description": self.band_description,
            "reference_clause": self.reference_clause,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class MPEEvaluationResult:
    """
    Result of evaluating an observed error against the P2 statutory MPE limit.
    """
    limit: RegulatoryMPELimit
    observed_error: float
    passed: bool
    margin: float
    margin_in_e: float
    remarks: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "limit": self.limit.to_dict(),
            "observed_error": self.observed_error,
            "passed": self.passed,
            "margin": self.margin,
            "margin_in_e": self.margin_in_e,
            "remarks": self.remarks,
        }


class MPEAdapter:
    """
    Clean adapter layer that delegates all MPE determination to Person 2.
    """

    @classmethod
    def normalize_verification_type(
        cls, verification_type: Union[str, bool, VerificationType, JobType, None]
    ) -> VerificationType:
        """Normalizes verification type using P2's canonical converter."""
        return VerificationType.from_value(verification_type)

    @classmethod
    def get_effective_e(
        cls,
        load: float,
        base_e: float,
        partial_ranges: Optional[List[Dict[str, Any]]] = None,
    ) -> float:
        """
        Determines the effective e for multi-interval instruments at a given load.
        """
        if not partial_ranges:
            return base_e

        # Sort partial ranges by range_index or max_capacity
        sorted_ranges = sorted(partial_ranges, key=lambda r: float(r.get("max_capacity", 0)))
        for pr in sorted_ranges:
            cap = float(pr.get("max_capacity", 0))
            if load <= cap + 1e-9:
                return float(pr.get("e", base_e))

        return float(sorted_ranges[-1].get("e", base_e))

    @classmethod
    def get_mpe(
        cls,
        load: float,
        accuracy_class: Union[str, AccuracyClass],
        e: float,
        verification_type: Union[str, bool, VerificationType, JobType] = "INITIAL",
        unit: str = "kg",
        partial_ranges: Optional[List[Dict[str, Any]]] = None,
        tare_load: float = 0.0,
    ) -> RegulatoryMPELimit:
        """
        Retrieves the statutory MPE directly from P2 MPEEngine.
        """
        effective_load = max(0.0, load - tare_load) if tare_load > 0 else load
        effective_e = cls.get_effective_e(effective_load, e, partial_ranges)
        v_type = cls.normalize_verification_type(verification_type)

        # Delegate calculation to P2 MPEEngine
        p2_res: MPECalculationResult = MPEEngine.calculate(
            accuracy_class=accuracy_class,
            load=effective_load,
            e=effective_e,
            verification_type=v_type,
        )

        return RegulatoryMPELimit(
            load=load,
            load_in_e=p2_res.load_in_e,
            e=effective_e,
            accuracy_class=p2_res.accuracy_class,
            verification_type=v_type.value,
            mpe_in_e=p2_res.mpe_in_e,
            mpe_absolute=p2_res.mpe_absolute,
            lower_limit=-p2_res.mpe_absolute,
            upper_limit=p2_res.mpe_absolute,
            band_description=p2_res.band_description,
            reference_clause=p2_res.source or p2_res.applicable_rule,
            unit=unit,
        )

    @classmethod
    def evaluate_error(
        cls,
        observed_error: float,
        load: float,
        accuracy_class: Union[str, AccuracyClass],
        e: float,
        verification_type: Union[str, bool, VerificationType, JobType] = "INITIAL",
        unit: str = "kg",
        partial_ranges: Optional[List[Dict[str, Any]]] = None,
        tare_load: float = 0.0,
    ) -> MPEEvaluationResult:
        """
        Evaluates an observed error against the P2 MPE limit.
        """
        effective_load = max(0.0, load - tare_load) if tare_load > 0 else load
        effective_e = cls.get_effective_e(effective_load, e, partial_ranges)
        v_type = cls.normalize_verification_type(verification_type)

        # Delegate calculation to P2 MPEEngine with observed_error
        p2_res: MPECalculationResult = MPEEngine.calculate(
            accuracy_class=accuracy_class,
            load=effective_load,
            e=effective_e,
            verification_type=v_type,
            observed_error=observed_error,
        )

        limit = RegulatoryMPELimit(
            load=load,
            load_in_e=p2_res.load_in_e,
            e=effective_e,
            accuracy_class=p2_res.accuracy_class,
            verification_type=v_type.value,
            mpe_in_e=p2_res.mpe_in_e,
            mpe_absolute=p2_res.mpe_absolute,
            lower_limit=-p2_res.mpe_absolute,
            upper_limit=p2_res.mpe_absolute,
            band_description=p2_res.band_description,
            reference_clause=p2_res.source or p2_res.applicable_rule,
            unit=unit,
        )

        passed = bool(p2_res.passed)
        margin = float(p2_res.margin) if p2_res.margin is not None else (limit.mpe_absolute - abs(observed_error))
        margin_in_e = float(p2_res.margin_in_e) if p2_res.margin_in_e is not None else (margin / effective_e)

        if passed:
            remarks = (
                f"Compliant: observed error {observed_error:+.4g} {unit} is within "
                f"MPE ±{limit.mpe_absolute:.4g} {unit} (±{limit.mpe_in_e}e). Margin: {margin:+.4g} {unit}."
            )
        else:
            remarks = (
                f"Non-compliant: observed error {observed_error:+.4g} {unit} exceeds "
                f"MPE ±{limit.mpe_absolute:.4g} {unit} (±{limit.mpe_in_e}e). Margin: {margin:+.4g} {unit}."
            )

        return MPEEvaluationResult(
            limit=limit,
            observed_error=observed_error,
            passed=passed,
            margin=margin,
            margin_in_e=margin_in_e,
            remarks=remarks,
        )

    @classmethod
    def get_zero_drift_limit(cls, e: float) -> float:
        """
        Statutory zero return limit per OIML R 76-1 Clause 4.1.2.2 / A.4.4.2:
        The zero indication shall not vary by more than 0.5e after unloading.
        """
        return 0.5 * e

    @classmethod
    def get_creep_limits(cls, e: float) -> Dict[str, float]:
        """
        Statutory creep limits per OIML R 76-1 Clause 4.1.2.1 / A.4.4.1:
        - Total creep (30 min): <= 0.5e
        - Transient creep (15 to 30 min): <= 0.2e
        """
        return {
            "total_creep_limit_e": 0.5,
            "total_creep_limit": 0.5 * e,
            "transient_creep_limit_e": 0.2,
            "transient_creep_limit": 0.2 * e,
        }

    @classmethod
    def get_tare_setting_limit(cls, e: float) -> float:
        """
        Statutory tare setting error limit per OIML R 76-1 Clause 4.6.3:
        The zero indication with tare set shall not exceed +/- 0.25e.
        """
        return 0.25 * e
