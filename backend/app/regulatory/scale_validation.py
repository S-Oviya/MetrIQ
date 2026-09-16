"""
MetrIQ Regulatory Engine - Scale Interval & Capacity Validation
Validates e, d, Max, Min, and n relationships for single-range, multi-interval,
and multi-range Non-Automatic Weighing Instruments (NAWI) per OIML R 76-1:2006
and Indian Legal Metrology Rules, 2011.
"""

import math
from typing import List, Tuple, Optional
from decimal import Decimal, InvalidOperation

from .models import InstrumentProfile, AccuracyClass, MassUnit, WeighingRange
from .errors import ValidationResult, RegulatoryErrorCode, IssueSeverity
from .sources import REGULATORY_REGISTRY
from .accuracy_class import validate_accuracy_class, get_class_boundary


def is_valid_scale_interval_form(e: float) -> Tuple[bool, Optional[str]]:
    """
    Verifies that the verification scale interval e is strictly of the form:
    1 * 10^k, 2 * 10^k, or 5 * 10^k units of mass, where k is an integer.
    (OIML R 76-1:2006 Clause 3.2.1 / IN LM 2011 Seventh Schedule Part I).
    """
    if e <= 0:
        return False, "Scale interval must be strictly positive."

    try:
        # Use scientific notation formatting to reliably extract mantissa
        # e.g., 0.02 -> 2.000000e-02, 5000 -> 5.000000e+03
        sci = f"{e:.8e}"
        mantissa_str, exp_str = sci.split("e")
        mantissa = round(float(mantissa_str), 4)

        # The mantissa should be close to 1.0, 2.0, or 5.0
        allowed_mantissas = {1.0, 2.0, 5.0}
        for allowed in allowed_mantissas:
            if abs(mantissa - allowed) < 1e-4:
                return True, None

        return (
            False,
            f"Verification scale interval e={e} has normalized mantissa {mantissa:.4g}. "
            f"Statutory rules require e = 1*10^k, 2*10^k, or 5*10^k."
        )
    except Exception as exc:
        return False, f"Could not parse scale interval form: {exc}"


def validate_auxiliary_device(
    instrument: InstrumentProfile,
    standard_id: str = "OIML_R76_2006",
) -> ValidationResult:
    """
    Validates actual scale interval d vs verification scale interval e.
    Per OIML R 76-1 Clause 3.4.1 & 3.4.2:
    - If d is specified and d < e:
      * Auxiliary indicating devices are permitted ONLY for Class I and Class II.
      * Permitted relationship: d < e <= 10d.
      * For Class III and Class IIII, auxiliary indicating devices are not permitted (d = e).
    - d can never exceed e (d <= e).
    """
    result = ValidationResult(is_valid=True)
    source = REGULATORY_REGISTRY.get_or_default(standard_id)

    if instrument.d is None:
        # No auxiliary indicating device specified; d = e by default
        return result

    d = instrument.d
    e = instrument.e

    if d <= 0:
        result.add_error(
            code=RegulatoryErrorCode.INVALID_SCALE_INTERVAL_FORM,
            message=f"Actual scale interval d must be strictly positive. Received {d}.",
            field="d",
            reference_clause=f"{source.short_title} Clause 3.4.1",
        )
        return result

    # Rule: d <= e
    tol = 1e-9
    if d > (e + tol):
        result.add_error(
            code=RegulatoryErrorCode.INVALID_AUXILIARY_DEVICE,
            message=(
                f"Actual scale interval d={d} {instrument.unit.value} cannot exceed "
                f"verification scale interval e={e} {instrument.unit.value}."
            ),
            field="d",
            reference_clause=f"{source.short_title} Clause 3.4.1",
            suggestion="Ensure d <= e. For standard commercial instruments without auxiliary devices, d = e.",
        )
        return result

    # If d < e, auxiliary device is in use
    if d < (e - tol):
        acc_class = instrument.accuracy_class
        # Auxiliary indicating devices are allowed only for Class I and Class II
        if acc_class in (AccuracyClass.CLASS_III, AccuracyClass.CLASS_IIII):
            if not source.allows_auxiliary_indicating_class_3:
                result.add_error(
                    code=RegulatoryErrorCode.INVALID_AUXILIARY_DEVICE,
                    message=(
                        f"Auxiliary indicating device with differentiated scale interval (d={d} < e={e}) "
                        f"is NOT permitted for {acc_class.roman}. Under {source.short_title} Clause 3.4.1, "
                        f"auxiliary devices are allowed only for Class I and Class II."
                    ),
                    field="d",
                    reference_clause=f"{source.short_title} Clause 3.4.1",
                    suggestion="Set actual scale interval d equal to verification scale interval e for Class III/IIII.",
                )

        # Rule: e <= 10d
        if e > (10 * d + tol):
            result.add_error(
                code=RegulatoryErrorCode.INVALID_AUXILIARY_DEVICE,
                message=(
                    f"Verification scale interval e={e} {instrument.unit.value} exceeds 10 * d "
                    f"(10 * {d} = {10*d} {instrument.unit.value}). OIML R 76 Clause 3.4.2 mandates d < e <= 10d."
                ),
                field="e",
                reference_clause=f"{source.short_title} Clause 3.4.2",
                suggestion="Adjust d or e so that e <= 10 * d.",
            )

        # Auxiliary devices cannot be used on multi-interval instruments
        if instrument.is_multi_interval:
            result.add_error(
                code=RegulatoryErrorCode.INVALID_AUXILIARY_DEVICE,
                message="Auxiliary indicating devices (d < e) are not permitted on multi-interval instruments.",
                field="is_multi_interval",
                reference_clause=f"{source.short_title} Clause 3.4.1",
                suggestion="For multi-interval instruments, set d_i = e_i for every partial range.",
            )

    return result


def validate_multi_interval(
    instrument: InstrumentProfile,
    standard_id: str = "OIML_R76_2006",
) -> ValidationResult:
    """
    Validates multi-interval instrument partial ranges per OIML R 76-1 Clause 3.3.
    Rules:
    - e_1 < e_2 < ... < e_r
    - Min_1 = Min of instrument
    - Max_r = Max of instrument
    - Max_i > Max_{i-1}
    - Each partial range must meet the statutory n_min and n_max requirements
    - Partial range scale intervals e_i must conform to 1, 2, 5 * 10^k
    """
    result = ValidationResult(is_valid=True)
    source = REGULATORY_REGISTRY.get_or_default(standard_id)

    if not instrument.is_multi_interval:
        return result

    ranges = instrument.partial_ranges
    if not ranges or len(ranges) < 2:
        result.add_error(
            code=RegulatoryErrorCode.MULTI_INTERVAL_INVALID,
            message="Multi-interval instrument must define at least two partial weighing ranges.",
            field="partial_ranges",
            reference_clause=f"{source.short_title} Clause 3.3",
        )
        return result

    # Sort or check order by range_index
    sorted_ranges = sorted(ranges, key=lambda r: r.range_index)

    tol = 1e-9
    for i, pr in enumerate(sorted_ranges):
        # Validate e form
        valid_form, msg = is_valid_scale_interval_form(pr.e)
        if not valid_form:
            result.add_error(
                code=RegulatoryErrorCode.INVALID_SCALE_INTERVAL_FORM,
                message=f"Partial range #{pr.range_index}: {msg}",
                field=f"partial_ranges[{i}].e",
                reference_clause=f"{source.short_title} Clause 3.2.1",
            )

        # Capacity check
        if pr.max_capacity <= pr.min_capacity:
            result.add_error(
                code=RegulatoryErrorCode.MAX_LESS_THAN_MIN,
                message=f"Partial range #{pr.range_index}: Max ({pr.max_capacity}) must be greater than Min ({pr.min_capacity}).",
                field=f"partial_ranges[{i}].max_capacity",
                reference_clause=f"{source.short_title} Clause 3.3",
            )

        # Successive range relationships
        if i > 0:
            prev = sorted_ranges[i - 1]
            if pr.e <= prev.e:
                result.add_error(
                    code=RegulatoryErrorCode.PARTIAL_RANGE_ORDERING,
                    message=(
                        f"Partial range #{pr.range_index} scale interval e={pr.e} must be strictly greater "
                        f"than previous range #{prev.range_index} scale interval e={prev.e}."
                    ),
                    field=f"partial_ranges[{i}].e",
                    reference_clause=f"{source.short_title} Clause 3.3.1",
                )

            if pr.max_capacity <= prev.max_capacity:
                result.add_error(
                    code=RegulatoryErrorCode.PARTIAL_RANGE_ORDERING,
                    message=(
                        f"Partial range #{pr.range_index} capacity Max={pr.max_capacity} must be strictly greater "
                        f"than previous range #{prev.range_index} capacity Max={prev.max_capacity}."
                    ),
                    field=f"partial_ranges[{i}].max_capacity",
                    reference_clause=f"{source.short_title} Clause 3.3.1",
                )

        # Validate n_i against accuracy class
        e_grams = pr.unit.to_grams(pr.e)
        boundary = get_class_boundary(instrument.accuracy_class, e_grams)
        if boundary:
            # For i=1, n1 = Max1 / e1
            # For i>1, OIML 3.3.2: n_i = Max_i / e_i
            n_i = pr.max_capacity / pr.e
            if n_i < boundary.n_min:
                result.add_error(
                    code=RegulatoryErrorCode.N_OUT_OF_BOUNDS,
                    message=(
                        f"Partial range #{pr.range_index} scale interval count n={n_i:,.1f} is below minimum "
                        f"{boundary.n_min:,} for {instrument.accuracy_class.roman}."
                    ),
                    field=f"partial_ranges[{i}].n",
                    reference_clause=boundary.reference_clause,
                )
            if boundary.n_max is not None and n_i > boundary.n_max:
                result.add_error(
                    code=RegulatoryErrorCode.N_OUT_OF_BOUNDS,
                    message=(
                        f"Partial range #{pr.range_index} scale interval count n={n_i:,.1f} exceeds maximum "
                        f"{boundary.n_max:,} for {instrument.accuracy_class.roman}."
                    ),
                    field=f"partial_ranges[{i}].n",
                    reference_clause=boundary.reference_clause,
                )

    # Check alignment with instrument total Max and Min
    first_range = sorted_ranges[0]
    last_range = sorted_ranges[-1]

    if abs(first_range.min_capacity - instrument.min_capacity) > tol:
        result.add_warning(
            code=RegulatoryErrorCode.PARTIAL_RANGE_ORDERING,
            message=(
                f"Instrument Min ({instrument.min_capacity} {instrument.unit.value}) does not match "
                f"partial range #1 Min ({first_range.min_capacity} {first_range.unit.value}). Synchronizing."
            ),
            field="min_capacity",
            reference_clause=f"{source.short_title} Clause 3.3.1",
        )

    if abs(last_range.max_capacity - instrument.max_capacity) > tol:
        result.add_warning(
            code=RegulatoryErrorCode.PARTIAL_RANGE_ORDERING,
            message=(
                f"Instrument Max ({instrument.max_capacity} {instrument.unit.value}) does not match "
                f"partial range #{last_range.range_index} Max ({last_range.max_capacity} {last_range.unit.value})."
            ),
            field="max_capacity",
            reference_clause=f"{source.short_title} Clause 3.3.1",
        )

    return result


def validate_instrument_scales(
    instrument: InstrumentProfile,
    standard_id: str = "OIML_R76_2006",
) -> ValidationResult:
    """
    Comprehensive metrological validation for all scale parameters of an instrument:
    1. Basic capacity relationships (Max > Min > 0)
    2. Verification scale interval form (e = 1, 2, 5 * 10^k)
    3. Auxiliary indicating device rules (d vs e)
    4. Accuracy class boundary validation (n_min, n_max, Min >= k * e)
    5. Multi-interval / multi-range architecture validation
    6. Tare and zero features validation
    """
    result = ValidationResult(is_valid=True)
    source = REGULATORY_REGISTRY.get_or_default(standard_id)

    # 1. Basic capacity sanity checks
    if instrument.max_capacity <= 0:
        result.add_error(
            code=RegulatoryErrorCode.INVALID_LOAD_VALUE,
            message=f"Maximum capacity Max must be strictly positive. Received {instrument.max_capacity}.",
            field="max_capacity",
            reference_clause=f"{source.short_title} Clause 3.1",
        )

    if instrument.min_capacity < 0:
        result.add_error(
            code=RegulatoryErrorCode.INVALID_LOAD_VALUE,
            message=f"Minimum capacity Min cannot be negative. Received {instrument.min_capacity}.",
            field="min_capacity",
            reference_clause=f"{source.short_title} Clause 3.1",
        )

    if instrument.max_capacity <= instrument.min_capacity:
        result.add_error(
            code=RegulatoryErrorCode.MAX_LESS_THAN_MIN,
            message=(
                f"Maximum capacity Max={instrument.max_capacity} {instrument.unit.value} must be strictly "
                f"greater than minimum capacity Min={instrument.min_capacity} {instrument.unit.value}."
            ),
            field="max_capacity",
            reference_clause=f"{source.short_title} Clause 3.1",
            suggestion="Ensure Max > Min.",
        )

    if instrument.e <= 0:
        result.add_error(
            code=RegulatoryErrorCode.INVALID_SCALE_INTERVAL_FORM,
            message=f"Verification scale interval e must be strictly positive. Received {instrument.e}.",
            field="e",
            reference_clause=f"{source.short_title} Clause 3.2.1",
        )
        return result

    # 2. Form of e (1, 2, 5 * 10^k)
    if source.strict_form_of_e:
        valid_form, form_msg = is_valid_scale_interval_form(instrument.e)
        if not valid_form:
            result.add_error(
                code=RegulatoryErrorCode.INVALID_SCALE_INTERVAL_FORM,
                message=form_msg or "Invalid form of verification scale interval e.",
                field="e",
                reference_clause=f"{source.short_title} Clause 3.2.1",
                suggestion="Use standard verification scale interval (e.g., 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, etc.).",
            )

    # 3. Auxiliary device (d vs e)
    aux_res = validate_auxiliary_device(instrument, standard_id=standard_id)
    for issue in aux_res.issues:
        result.add_issue(issue)

    # 4. Accuracy class statutory validation
    class_res = validate_accuracy_class(instrument, standard_id=standard_id)
    for issue in class_res.issues:
        result.add_issue(issue)

    # 5. Multi-interval validation
    if instrument.is_multi_interval:
        multi_res = validate_multi_interval(instrument, standard_id=standard_id)
        for issue in multi_res.issues:
            result.add_issue(issue)

    # 6. Tare validation
    if instrument.has_tare:
        if instrument.max_additive_tare is not None and instrument.max_additive_tare < 0:
            result.add_error(
                code=RegulatoryErrorCode.TARE_VALUE_INVALID,
                message="Additive tare maximum cannot be negative.",
                field="max_additive_tare",
                reference_clause=f"{source.short_title} Clause 3.5.3.3",
            )
        if instrument.max_subtractive_tare is not None and instrument.max_subtractive_tare > instrument.max_capacity:
            result.add_warning(
                code=RegulatoryErrorCode.TARE_VALUE_INVALID,
                message=f"Subtractive tare maximum ({instrument.max_subtractive_tare}) exceeds Max capacity ({instrument.max_capacity}).",
                field="max_subtractive_tare",
                reference_clause=f"{source.short_title} Clause 3.5.3.3",
            )

    # 7. Discretionary / Manual inspection warnings
    if instrument.temp_range_min_c is not None and instrument.temp_range_max_c is not None:
        temp_span = instrument.temp_range_max_c - instrument.temp_range_min_c
        # Standard default is -10 to +40 (50 deg C span), or special spans per Clause 3.9.2:
        # Class I: at least 5 deg C span
        # Class II: at least 15 deg C span
        # Class III/IIII: at least 30 deg C span
        min_spans = {
            AccuracyClass.CLASS_I: 5.0,
            AccuracyClass.CLASS_II: 15.0,
            AccuracyClass.CLASS_III: 30.0,
            AccuracyClass.CLASS_IIII: 30.0,
        }
        required_span = min_spans.get(instrument.accuracy_class, 30.0)
        if temp_span < required_span:
            result.add_warning(
                code=RegulatoryErrorCode.ENVIRONMENT_LIMIT_WARNING,
                message=(
                    f"Operating temperature span [{instrument.temp_range_min_c}°C to {instrument.temp_range_max_c}°C] "
                    f"is {temp_span}°C. Clause 3.9.2 requires at least {required_span}°C span for {instrument.accuracy_class.roman}."
                ),
                field="temp_range_min_c",
                reference_clause=f"{source.short_title} Clause 3.9.2",
            )

    # Attach summary metadata
    result.metadata = {
        "standard_id": standard_id,
        "standard_name": source.short_title,
        "accuracy_class": instrument.accuracy_class.roman if hasattr(instrument.accuracy_class, "roman") else str(instrument.accuracy_class),
        "n": instrument.n,
        "max": instrument.max_capacity,
        "min": instrument.min_capacity,
        "e": instrument.e,
        "d": instrument.actual_d,
        "unit": instrument.unit.value,
    }

    return result
