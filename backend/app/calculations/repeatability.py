"""
MetrIQ P4: Repeatability Test Calculation
=========================================
Person 4: Rachitha (Test Engine + Calculations Lead)

Statutory Reference:
- OIML R 76-1:2006 Clause A.4.10 (Repeatability Test)
- Indian Legal Metrology (General) Rules, 2011 Seventh Schedule

Evaluates repeatability by computing the range (max - min) and sample
standard deviation across repeated weighings of the same test load.
Enforces the statutory requirement:
  (I_max - I_min) <= |MPE(L)|
where MPE is retrieved strictly from Person 2 Regulatory Engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Union

from app.calculations.models import TestType, Verdict
from app.calculations.mpe import MPEAdapter, RegulatoryMPELimit


@dataclass
class RepeatabilitySeriesResult:
    """
    Result of a repeatability series at a single test load.
    """
    series_index: int
    load: float
    repetitions: int
    indications: List[float]
    min_indication: float
    max_indication: float
    range_span: float
    mean_indication: float
    standard_deviation: float
    mpe_limit: RegulatoryMPELimit
    passed: bool
    margin: float
    unit: str = "kg"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "series_index": self.series_index,
            "load": self.load,
            "repetitions": self.repetitions,
            "indications": self.indications,
            "min_indication": self.min_indication,
            "max_indication": self.max_indication,
            "range_span": self.range_span,
            "mean_indication": self.mean_indication,
            "standard_deviation": self.standard_deviation,
            "mpe_limit": self.mpe_limit.to_dict(),
            "passed": self.passed,
            "margin": self.margin,
            "unit": self.unit,
        }


@dataclass
class RepeatabilityTestResult:
    """
    Overall result of all repeatability series in a test run.
    """
    verdict: Verdict
    summary: str
    series_results: List[RepeatabilitySeriesResult]
    worst_span: float
    worst_span_load: float
    unit: str = "kg"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "summary": self.summary,
            "series_results": [s.to_dict() for s in self.series_results],
            "worst_span": self.worst_span,
            "worst_span_load": self.worst_span_load,
            "unit": self.unit,
            "metadata": self.metadata,
        }


class RepeatabilityCalculator:
    """
    Executes metrological calculations for NAWI Repeatability tests.
    """

    @classmethod
    def evaluate_series(
        cls,
        load: float,
        indications: List[float],
        accuracy_class: str,
        e: float,
        verification_type: str = "INITIAL",
        unit: str = "kg",
        series_index: int = 1,
        partial_ranges: Optional[List[Dict[str, Any]]] = None,
    ) -> RepeatabilitySeriesResult:
        """
        Evaluates a single repeatability series of repeated weighings.
        """
        if len(indications) < 2:
            raise ValueError(
                f"Repeatability series {series_index} must contain at least 2 indications; received {len(indications)}."
            )

        n = len(indications)
        min_ind = min(indications)
        max_ind = max(indications)
        span = round(max_ind - min_ind, 9)
        mean_ind = round(sum(indications) / n, 9)

        variance = sum((x - mean_ind) ** 2 for x in indications) / (n - 1)
        std_dev = round(math.sqrt(variance), 9)

        # Retrieve statutory limit from Person 2 for the applied load
        mpe_limit = MPEAdapter.get_mpe(
            load=load,
            accuracy_class=accuracy_class,
            e=e,
            verification_type=verification_type,
            unit=unit,
            partial_ranges=partial_ranges,
        )

        # Statutory rule: (I_max - I_min) <= |MPE|
        passed = span <= (mpe_limit.mpe_absolute + 1e-9)
        margin = round(mpe_limit.mpe_absolute - span, 9)

        return RepeatabilitySeriesResult(
            series_index=series_index,
            load=load,
            repetitions=n,
            indications=indications,
            min_indication=min_ind,
            max_indication=max_ind,
            range_span=span,
            mean_indication=mean_ind,
            standard_deviation=std_dev,
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
    ) -> RepeatabilityTestResult:
        """
        Groups observations by load into series and evaluates repeatability.
        """
        if not observations:
            raise ValueError("Observations list cannot be empty for repeatability evaluation.")

        # Group indications by load
        grouped: Dict[float, List[float]] = {}
        for obs in observations:
            ld = float(obs["applied_load"])
            ind = float(obs["indicated_value"])
            grouped.setdefault(ld, []).append(ind)

        series_results: List[RepeatabilitySeriesResult] = []
        all_passed = True
        worst_span = 0.0
        worst_load = 0.0

        for idx, (load_val, ind_list) in enumerate(grouped.items(), start=1):
            res = cls.evaluate_series(
                load=load_val,
                indications=ind_list,
                accuracy_class=accuracy_class,
                e=e,
                verification_type=verification_type,
                unit=unit,
                series_index=idx,
                partial_ranges=partial_ranges,
            )
            series_results.append(res)
            if not res.passed:
                all_passed = False
            if res.range_span >= worst_span:
                worst_span = res.range_span
                worst_load = load_val

        verdict = Verdict.PASS if all_passed else Verdict.FAIL
        summary = (
            f"Repeatability {verdict.value}: {len(series_results)} series evaluated. "
            f"Worst range span = {worst_span:.4g} {unit} at {worst_load} {unit}."
        )

        return RepeatabilityTestResult(
            verdict=verdict,
            summary=summary,
            series_results=series_results,
            worst_span=worst_span,
            worst_span_load=worst_load,
            unit=unit,
        )
