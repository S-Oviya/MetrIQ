"""
MetrIQ Regulatory Engine - Maximum Permissible Error (MPE) Calculation
Implements Table 6 of OIML R 76-1:2006 and Table 2 of Indian Legal Metrology (General)
Rules, 2011 for Initial Verification and In-Service Inspection.
"""

from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass

from .models import AccuracyClass, JobType, MassUnit, InstrumentProfile, MPEValue
from .sources import REGULATORY_REGISTRY
from .mpe_engine import (
    MPEBandDefinition,
    MPECalculationResult,
    MPEEngine,
    MPE_STATUTORY_TABLE,
    VerificationType,
    calculate_mpe_statutory,
)


@dataclass(frozen=True)
class MPEStep:
    """A range of load expressed in e with its corresponding base initial MPE in e."""
    min_e: float
    max_e: float
    base_mpe_e: float  # typically 0.5, 1.0, 1.5


# Statutory MPE step tables on Initial Verification (OIML R 76 Table 6 / IN LM 2011 Table 2)
MPE_STEPS_BY_CLASS: Dict[AccuracyClass, List[MPEStep]] = {
    AccuracyClass.CLASS_I: [
        MPEStep(0.0, 50000.0, 0.5),
        MPEStep(50000.0, 200000.0, 1.0),
        MPEStep(200000.0, float("inf"), 1.5),
    ],
    AccuracyClass.CLASS_II: [
        MPEStep(0.0, 5000.0, 0.5),
        MPEStep(5000.0, 20000.0, 1.0),
        MPEStep(20000.0, 100000.0, 1.5),
    ],
    AccuracyClass.CLASS_III: [
        MPEStep(0.0, 500.0, 0.5),
        MPEStep(500.0, 2000.0, 1.0),
        MPEStep(2000.0, 10000.0, 1.5),
    ],
    AccuracyClass.CLASS_IIII: [
        MPEStep(0.0, 50.0, 0.5),
        MPEStep(50.0, 200.0, 1.0),
        MPEStep(200.0, 1000.0, 1.5),
    ],
}


def get_effective_e_for_load(load: float, instrument: InstrumentProfile) -> float:
    """
    Returns the effective verification scale interval e for a given load,
    taking into account partial ranges for multi-interval instruments.
    """
    if not instrument.is_multi_interval or not instrument.partial_ranges:
        return instrument.e

    # Sorted by range_index
    sorted_ranges = sorted(instrument.partial_ranges, key=lambda r: r.range_index)
    for pr in sorted_ranges:
        if load <= pr.max_capacity + 1e-9:
            return pr.e

    # Default to last range if load exceeds last max
    return sorted_ranges[-1].e


def calculate_mpe_in_e(
    load_in_e: float,
    accuracy_class: AccuracyClass,
    is_in_service: bool = False,
    mpe_multiplier: Optional[float] = None,
) -> float:
    """
    Calculates Maximum Permissible Error expressed in multiples of e (+/- value).

    :param load_in_e: Load expressed as m / e.
    :param accuracy_class: Class I, II, III, or IIII.
    :param is_in_service: True if statutory re-verification / in-service inspection.
    :param mpe_multiplier: Custom multiplier (defaults to 2.0 for in-service, 1.0 for initial).
    :return: Float value of MPE in e (e.g. 0.5, 1.0, 1.5, 2.0, 3.0).
    """
    v_type = VerificationType.SUBSEQUENT if is_in_service else VerificationType.INITIAL
    res = MPEEngine.calculate(
        accuracy_class=accuracy_class,
        load=load_in_e,
        e=1.0,
        verification_type=v_type,
    )

    if mpe_multiplier is not None:
        initial_mpe = res.mpe_in_e / (2.0 if is_in_service else 1.0)
        return initial_mpe * mpe_multiplier

    return res.mpe_in_e


def get_mpe_breakpoints_for_instrument(
    instrument: InstrumentProfile,
    tare_load: float = 0.0,
) -> List[float]:
    """
    Returns the transition points (in instrument units) where the MPE steps change
    (e.g., 500e, 2000e for Class III). Useful for generating test load points.
    """
    acc_class = instrument.accuracy_class
    steps = MPE_STEPS_BY_CLASS.get(acc_class, MPE_STEPS_BY_CLASS[AccuracyClass.CLASS_III])

    breakpoints: List[float] = []
    for step in steps:
        if step.max_e != float("inf"):
            val = step.max_e * instrument.e
            if val < instrument.max_capacity:
                breakpoints.append(round(val, 6))

    return breakpoints


def calculate_mpe(
    load: float,
    instrument: InstrumentProfile,
    job_type: JobType = JobType.INITIAL_VERIFICATION,
    tare_load: float = 0.0,
    standard_id: str = "OIML_R76_2006",
    is_in_service: Optional[bool] = None,
) -> MPEValue:
    """
    Calculates full MPE specification for a specific test load.

    Handles:
    - Net vs Gross loads when tare is active
    - Multi-interval instruments (selecting applicable partial range e_i)
    - Initial Verification vs Periodic Re-verification / In-service
    - Unit consistency
    - Boundary clause citation

    :param load: Applied gross test load in instrument units.
    :param instrument: Instrument profile.
    :param job_type: MetrIQ test job type.
    :param tare_load: Tare load applied, if any.
    :param standard_id: Regulatory standard ID.
    :param is_in_service: Explicit override for in-service status.
    :return: MPEValue object with tolerances in e and engineering units.
    """
    source = REGULATORY_REGISTRY.get_or_default(standard_id)

    # In-service determination
    in_service = is_in_service if is_in_service is not None else job_type.is_in_service

    # Net load calculation
    effective_load = load
    net_load = None
    if tare_load > 0:
        net_load = max(0.0, load - tare_load)
        effective_load = net_load

    # Effective scale interval
    eff_e = get_effective_e_for_load(effective_load, instrument)
    load_in_e = effective_load / eff_e if eff_e > 0 else 0.0

    # Calculate MPE in e
    multiplier = source.default_mpe_multiplier_in_service if in_service else 1.0
    mpe_e = calculate_mpe_in_e(
        load_in_e=load_in_e,
        accuracy_class=instrument.accuracy_class,
        is_in_service=in_service,
        mpe_multiplier=multiplier,
    )

    # Convert to physical units
    mpe_units = round(mpe_e * eff_e, 9)

    verification_type_label = "IN_SERVICE" if in_service else "INITIAL"
    ref_clause = (
        f"{source.short_title} Clause 3.5.2 (Table 6 in-service, multiplier {multiplier})"
        if in_service
        else f"{source.short_title} Clause 3.5.1 (Table 6 initial verification)"
    )

    return MPEValue(
        load=load,
        load_unit=instrument.unit,
        load_in_e=round(load_in_e, 4),
        mpe_in_e=mpe_e,
        mpe_in_units=mpe_units,
        lower_limit_error=-mpe_units,
        upper_limit_error=mpe_units,
        verification_type=verification_type_label,
        accuracy_class=instrument.accuracy_class,
        reference_clause=ref_clause,
        net_load=net_load,
        tare_load=tare_load if tare_load > 0 else None,
    )


def is_error_within_mpe(
    observed_error: float,
    load: float,
    instrument: InstrumentProfile,
    job_type: JobType = JobType.INITIAL_VERIFICATION,
    tare_load: float = 0.0,
    standard_id: str = "OIML_R76_2006",
) -> Tuple[bool, MPEValue]:
    """
    Evaluates whether an observed error (e.g. Indication - ReferenceLoad)
    is within the statutory Maximum Permissible Error.

    :return: Tuple of (is_pass: bool, mpe_spec: MPEValue)
    """
    mpe = calculate_mpe(
        load=load,
        instrument=instrument,
        job_type=job_type,
        tare_load=tare_load,
        standard_id=standard_id,
    )

    tol = 1e-9
    is_pass = (mpe.lower_limit_error - tol) <= observed_error <= (mpe.upper_limit_error + tol)
    return is_pass, mpe
