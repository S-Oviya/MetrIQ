"""
MetrIQ Regulatory Engine - Regulatory Instrument Classification Validator
Provides strict, detailed, non-rounding statutory validation of NAWI classification parameters
against OIML R 76-1:2006 (Table 3) and Indian Legal Metrology (General) Rules, 2011 (Table 1).
"""

from dataclasses import dataclass, field as dc_field
from decimal import Decimal, InvalidOperation
from enum import Enum
import math
from typing import Dict, List, Any, Optional, Union, Tuple

try:
    from .models import AccuracyClass, MassUnit, ReceptorType
    from .knowledge import KNOWLEDGE_BASE
except ImportError:
    from app.regulatory.models import AccuracyClass, MassUnit, ReceptorType
    from app.regulatory.knowledge import KNOWLEDGE_BASE


@dataclass
class ClassificationValidationIssue:
    """
    Detailed, actionable diagnostic issue identifying why a validation rule failed.
    """
    rule_id: str
    field: str
    actual_value: Any
    expected_condition: str
    source: str
    severity: str  # "ERROR", "WARNING", "MANUAL_REVIEW"
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "field": self.field,
            "actual_value": self.actual_value,
            "expected_condition": self.expected_condition,
            "source": self.source,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass
class ClassificationValidationResult:
    """
    Structured outcome of the Instrument Classification Validator.
    Tells the caller exactly if, why, and where an instrument conforms or fails.
    """
    valid: bool
    errors: List[ClassificationValidationIssue] = dc_field(default_factory=list)
    warnings: List[ClassificationValidationIssue] = dc_field(default_factory=list)
    manual_review_required: bool = False
    manual_review_reasons: List[str] = dc_field(default_factory=list)
    instrument_summary: Dict[str, Any] = dc_field(default_factory=dict)
    ranges_evaluated: List[Dict[str, Any]] = dc_field(default_factory=list)

    def add_error(
        self,
        rule_id: str,
        field: str,
        actual_value: Any,
        expected_condition: str,
        source: str,
        message: str,
    ) -> None:
        self.valid = False
        self.errors.append(
            ClassificationValidationIssue(
                rule_id=rule_id,
                field=field,
                actual_value=actual_value,
                expected_condition=expected_condition,
                source=source,
                severity="ERROR",
                message=message,
            )
        )

    def add_warning(
        self,
        rule_id: str,
        field: str,
        actual_value: Any,
        expected_condition: str,
        source: str,
        message: str,
    ) -> None:
        self.warnings.append(
            ClassificationValidationIssue(
                rule_id=rule_id,
                field=field,
                actual_value=actual_value,
                expected_condition=expected_condition,
                source=source,
                severity="WARNING",
                message=message,
            )
        )

    def flag_manual_review(self, reason: str) -> None:
        self.manual_review_required = True
        if reason not in self.manual_review_reasons:
            self.manual_review_reasons.append(reason)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "manual_review_required": self.manual_review_required,
            "manual_review_reasons": self.manual_review_reasons,
            "instrument_summary": self.instrument_summary,
            "ranges_evaluated": self.ranges_evaluated,
        }


def _safe_float(val: Any) -> Tuple[Optional[float], Optional[str]]:
    """
    Safely converts input value to float without silent rounding.
    Returns (float_value, error_message).
    """
    if val is None:
        return None, "Value cannot be null/None."
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None, "Value cannot be NaN or Infinite."
        return f, None
    except (ValueError, TypeError):
        return None, f"Expected numeric value, received '{val}' of type {type(val).__name__}."


def _check_form_of_e(e: float) -> Tuple[bool, str]:
    """
    Validates that verification scale interval e is strictly 1, 2, or 5 * 10^k units of mass.
    Does NOT silently round.
    """
    if e <= 0:
        return False, f"Scale interval must be strictly positive (> 0). Received {e}."

    sci = f"{e:.12e}"
    parts = sci.split("e")
    try:
        mantissa = round(float(parts[0]), 6)
    except (ValueError, IndexError):
        return False, f"Unable to parse scale interval mantissa for {e}."

    allowed = {1.0, 2.0, 5.0}
    for a in allowed:
        if abs(mantissa - a) < 1e-5:
            return True, ""

    return (
        False,
        f"Verification scale interval e={e} has normalized mantissa {mantissa:.4g}. "
        f"Statutory rule mandates e = 1*10^k, 2*10^k, or 5*10^k (OIML R 76-1 Clause 3.2.1 / IN LM 2011)."
    )


class RegulatoryClassificationValidator:
    """
    Authoritative classification validator for Non-Automatic Weighing Instruments.
    Validates accuracy class, e, d, Max, Min, n, multi-interval, and multi-range relationships.
    """

    SOURCE_INDIAN = "Legal Metrology (General) Rules, 2011 (Seventh Schedule Table 1)"
    SOURCE_OIML = "OIML R 76-1:2006 (Table 3 & Clause 3.2 - 3.4)"

    @classmethod
    def validate(cls, spec: Union[Dict[str, Any], Any]) -> ClassificationValidationResult:
        """
        Main validation entrypoint. Accepts dictionary or object specification.
        """
        # 1. Normalize input to dictionary
        if hasattr(spec, "to_dict") and callable(spec.to_dict):
            data = spec.to_dict()
        elif isinstance(spec, dict):
            data = dict(spec)
        else:
            # Try grabbing public attributes
            data = {k: getattr(spec, k) for k in dir(spec) if not k.startswith("_")}

        result = ClassificationValidationResult(valid=True)

        # 2. Extract and validate unit
        unit_str = str(data.get("unit", "kg")).lower().strip()
        try:
            unit = MassUnit(unit_str)
        except ValueError:
            result.add_error(
                rule_id="RULE_UNIT_INVALID",
                field="unit",
                actual_value=unit_str,
                expected_condition="Must be a valid mass unit: 'mg', 'g', 'kg', 't', or 'ct'",
                source=cls.SOURCE_INDIAN,
                message=f"Unsupported unit '{unit_str}'. Legal units are mg, g, kg, t, ct.",
            )
            return result

        # 3. Extract and validate Accuracy Class
        raw_class = data.get("accuracy_class") or data.get("class")
        if not raw_class:
            result.add_error(
                rule_id="RULE_ACCURACY_CLASS_MISSING",
                field="accuracy_class",
                actual_value=None,
                expected_condition="One of 'I', 'II', 'III', 'IIII'",
                source=cls.SOURCE_INDIAN,
                message="Accuracy class is missing. Allowed statutory classes are I, II, III, IIII.",
            )
            return result

        try:
            acc_class = AccuracyClass.from_string(str(raw_class))
        except ValueError:
            result.add_error(
                rule_id="RULE_ACCURACY_CLASS_INVALID",
                field="accuracy_class",
                actual_value=raw_class,
                expected_condition="Must be one of: 'I', 'II', 'III', 'IIII'",
                source=cls.SOURCE_INDIAN,
                message=f"Invalid accuracy class '{raw_class}'. Must be Class I, II, III, or IIII.",
            )
            return result

        # 4. Check architecture flags
        is_multi_interval = bool(
            data.get("multi_interval_status")
            or data.get("is_multi_interval")
            or False
        )
        is_multi_range = bool(
            data.get("multi_range_status")
            or data.get("is_multi_range")
            or False
        )
        is_electronic = bool(
            data.get("electronic_status")
            if data.get("electronic_status") is not None
            else data.get("is_electronic", True)
        )
        instrument_type = str(data.get("instrument_type") or "STANDARD_NAWI").upper()

        # Multi-interval and multi-range cannot be simultaneously enabled on the same weighing range
        if is_multi_interval and is_multi_range:
            result.add_warning(
                rule_id="RULE_MULTI_INTERVAL_RANGE_HYBRID",
                field="multi_interval_status",
                actual_value="both multi_interval and multi_range true",
                expected_condition="Instrument is typically either multi-interval or multi-range",
                source=cls.SOURCE_OIML,
                message="Instrument declares both multi-interval and multi-range architecture; requires manual technical dossier review.",
            )
            result.flag_manual_review("Hybrid multi-interval and multi-range design requires specialized technical examination.")

        # 5. Route to Range Validation
        # If multi-range, validate each range independently
        if is_multi_range:
            cls._validate_multi_range(data, acc_class, unit, result)
        elif is_multi_interval:
            cls._validate_multi_interval(data, acc_class, unit, result)
        else:
            cls._validate_single_range(data, acc_class, unit, result)

        # 6. Instrument type & electronic considerations
        if is_electronic:
            # Check warm-up and software provisions if specified
            if data.get("has_software"):
                if not data.get("software_version"):
                    result.add_warning(
                        rule_id="RULE_SOFTWARE_VERSION_REQUIRED",
                        field="software_version",
                        actual_value=None,
                        expected_condition="Software version identifier must be declared for software-equipped scales",
                        source=f"{cls.SOURCE_OIML} Clause 5.5",
                        message="Electronic scale has software enabled but lacks software version number.",
                    )
                    result.flag_manual_review("Verify software checksum and legally relevant firmware build in menu.")

        # 7. Zero-setting devices statutory checks (OIML R 76-1:2006 Clause 4.5.1 / Indian General Rules)
        # Initial zero-setting range shall not exceed 20% of Max
        initial_zs = (
            data.get("initial_zero_setting_range_percent")
            or data.get("initial_zero_setting_range_pct")
            or data.get("initial_zero_setting_pct")
        )
        if initial_zs is not None:
            try:
                izs_val = float(initial_zs)
                if izs_val > 20.0 + 1e-6:
                    result.add_warning(
                        rule_id="RULE_INITIAL_ZERO_SETTING_RANGE_EXCEEDED",
                        field="initial_zero_setting_range_percent",
                        actual_value=f"{izs_val}%",
                        expected_condition="<= 20% of Max",
                        source=f"{cls.SOURCE_OIML} Clause 4.5.1",
                        message=(
                            f"Initial zero-setting range of {izs_val}% exceeds statutory limit of 20% of Max. "
                            f"Requires manual regulatory examination to ensure non-intended zero manipulation is prevented."
                        ),
                    )
                    result.flag_manual_review(f"Initial zero-setting range ({izs_val}%) exceeds statutory 20% of Max limit.")
            except (ValueError, TypeError):
                pass

        # Non-automatic / Semi-automatic zero-setting range shall not exceed 4% of Max (+/- 2% of Max)
        zs_range = (
            data.get("zero_setting_range_percent")
            or data.get("zero_setting_range_pct")
            or data.get("zero_setting_pct")
        )
        if zs_range is not None:
            try:
                zs_val = float(zs_range)
                if zs_val > 4.0 + 1e-6:
                    result.add_warning(
                        rule_id="RULE_ZERO_SETTING_RANGE_EXCEEDED",
                        field="zero_setting_range_percent",
                        actual_value=f"{zs_val}%",
                        expected_condition="<= 4% of Max (+/- 2% of Max)",
                        source=f"{cls.SOURCE_OIML} Clause 4.5.1",
                        message=(
                            f"Non-automatic / semi-automatic zero-setting range of {zs_val}% exceeds statutory limit of 4% of Max. "
                            f"Requires manual technical review."
                        ),
                    )
                    result.flag_manual_review(f"Zero-setting range ({zs_val}%) exceeds statutory 4% of Max limit.")
            except (ValueError, TypeError):
                pass

        # Build summary
        result.instrument_summary = {
            "accuracy_class": acc_class.roman,
            "accuracy_class_name": acc_class.display_name,
            "unit": unit.value,
            "is_electronic": is_electronic,
            "is_multi_interval": is_multi_interval,
            "is_multi_range": is_multi_range,
            "instrument_type": instrument_type,
            "total_errors": len(result.errors),
            "total_warnings": len(result.warnings),
            "manual_review_required": result.manual_review_required,
        }

        return result

    @classmethod
    def _validate_single_range(
        cls,
        data: Dict[str, Any],
        acc_class: AccuracyClass,
        unit: MassUnit,
        result: ClassificationValidationResult,
    ) -> None:
        """Validates a single-range weighing instrument."""
        max_raw = data.get("Max") if data.get("Max") is not None else data.get("max_capacity")
        max_val, err = _safe_float(max_raw)
        if err:
            result.add_error("RULE_MAX_INVALID", "Max", max_raw, "Strictly positive number", cls.SOURCE_INDIAN, err)
            return

        min_raw = data.get("Min") if data.get("Min") is not None else data.get("min_capacity")
        min_val, err = _safe_float(min_raw)
        if err:
            result.add_error("RULE_MIN_INVALID", "Min", min_raw, "Strictly positive number", cls.SOURCE_INDIAN, err)
            return

        e_raw = data.get("e") if data.get("e") is not None else data.get("verification_scale_interval")
        e_val, err = _safe_float(e_raw)
        if err:
            result.add_error("RULE_E_INVALID", "e", e_raw, "Strictly positive number", cls.SOURCE_INDIAN, err)
            return

        d_raw = data.get("d") if data.get("d") is not None else data.get("actual_scale_interval")
        d_val = None
        if d_raw is not None:
            d_val, err = _safe_float(d_raw)
            if err:
                result.add_error("RULE_D_INVALID", "d", d_raw, "Positive number or None", cls.SOURCE_INDIAN, err)
                return

        calculated_n_raw = data.get("calculated_n") if data.get("calculated_n") is not None else data.get("n")
        user_n = None
        if calculated_n_raw is not None:
            user_n, err = _safe_float(calculated_n_raw)
            if err:
                result.add_error("RULE_N_INVALID", "calculated_n", calculated_n_raw, "Positive integer", cls.SOURCE_INDIAN, err)

        # Run core single-range checks
        range_summary = cls._validate_capacity_and_intervals(
            max_val=max_val,
            min_val=min_val,
            e_val=e_val,
            d_val=d_val,
            user_n=user_n,
            acc_class=acc_class,
            unit=unit,
            result=result,
            field_prefix="",
            is_multi_interval=False,
            check_min_capacity=True,
        )
        result.ranges_evaluated.append(range_summary)

    @classmethod
    def _validate_capacity_and_intervals(
        cls,
        max_val: float,
        min_val: float,
        e_val: float,
        d_val: Optional[float],
        user_n: Optional[float],
        acc_class: AccuracyClass,
        unit: MassUnit,
        result: ClassificationValidationResult,
        field_prefix: str = "",
        is_multi_interval: bool = False,
        check_min_capacity: bool = True,
    ) -> Dict[str, Any]:
        """Core mathematical & statutory validation of Max, Min, e, d, and n."""
        pfx = f"{field_prefix}." if field_prefix else ""

        # 1. Non-zero, strictly positive checks
        has_critical_error = False
        if max_val <= 0:
            result.add_error(
                rule_id="RULE_MAX_NON_POSITIVE",
                field=f"{pfx}Max",
                actual_value=max_val,
                expected_condition="Max > 0",
                source=f"{cls.SOURCE_INDIAN} / OIML Clause 3.1",
                message=f"Maximum capacity ({max_val} {unit.value}) must be strictly positive (> 0).",
            )
            has_critical_error = True

        if min_val < 0:
            result.add_error(
                rule_id="RULE_MIN_NEGATIVE",
                field=f"{pfx}Min",
                actual_value=min_val,
                expected_condition="Min >= 0",
                source=f"{cls.SOURCE_INDIAN} / OIML Clause 3.1",
                message=f"Minimum capacity ({min_val} {unit.value}) cannot be negative.",
            )
            has_critical_error = True

        if e_val <= 0:
            result.add_error(
                rule_id="RULE_E_NON_POSITIVE",
                field=f"{pfx}e",
                actual_value=e_val,
                expected_condition="e > 0",
                source=f"{cls.SOURCE_INDIAN} / OIML Clause 3.2.1",
                message=f"Verification scale interval e ({e_val} {unit.value}) must be strictly positive.",
            )
            has_critical_error = True

        if has_critical_error:
            return {"range": field_prefix or "main", "valid": False}

        # 2. Min must not exceed Max
        if min_val >= max_val:
            result.add_error(
                rule_id="RULE_MIN_EXCEEDS_MAX",
                field=f"{pfx}Min",
                actual_value=f"Min={min_val}, Max={max_val}",
                expected_condition="Min < Max",
                source=f"{cls.SOURCE_INDIAN} Part I",
                message=f"Minimum capacity ({min_val} {unit.value}) must be strictly less than maximum capacity ({max_val} {unit.value}).",
            )

        # 3. Strict form of e (1, 2, 5 * 10^k)
        valid_form, form_err = _check_form_of_e(e_val)
        if not valid_form:
            result.add_error(
                rule_id="RULE_SCALE_INTERVAL_FORM",
                field=f"{pfx}e",
                actual_value=e_val,
                expected_condition="e = 1*10^k, 2*10^k, or 5*10^k",
                source=f"{cls.SOURCE_OIML} Clause 3.2.1",
                message=form_err,
            )

        # 4. Compute n = Max / e
        n = max_val / e_val
        # Do NOT silently round!
        # Check if n is an integer or has fractional part
        if abs(n - round(n)) > 1e-4:
            result.add_error(
                rule_id="RULE_N_NON_INTEGER",
                field=f"{pfx}n",
                actual_value=f"{n:.6f}",
                expected_condition="n = Max / e must be an exact integer",
                source=f"{cls.SOURCE_INDIAN} Table 1",
                message=(
                    f"Number of scale intervals n = Max / e = {max_val} / {e_val} = {n:.6f} "
                    f"is not an integer. Verification scale intervals represent discrete counts."
                ),
            )

        # 5. Check calculated n against user provided calculated_n
        if user_n is not None:
            if abs(user_n - n) > 1e-4:
                result.add_error(
                    rule_id="RULE_N_CALCULATION_MISMATCH",
                    field=f"{pfx}calculated_n",
                    actual_value=user_n,
                    expected_condition=f"Must equal Max / e = {n:,.1f}",
                    source=f"{cls.SOURCE_INDIAN} Table 1",
                    message=(
                        f"Provided calculated_n ({user_n}) does not match exact ratio "
                        f"Max / e ({max_val} / {e_val} = {n:,.1f}). Do not round regulatory values."
                    ),
                )

        # 6. Check auxiliary device (d vs e)
        actual_d = d_val if d_val is not None and d_val > 0 else e_val
        if d_val is not None:
            if d_val <= 0:
                result.add_error(
                    rule_id="RULE_D_NON_POSITIVE",
                    field=f"{pfx}d",
                    actual_value=d_val,
                    expected_condition="d > 0",
                    source=f"{cls.SOURCE_OIML} Clause 3.4",
                    message=f"Actual scale interval d ({d_val}) must be strictly positive.",
                )
            elif d_val > e_val + 1e-9:
                result.add_error(
                    rule_id="RULE_D_EXCEEDS_E",
                    field=f"{pfx}d",
                    actual_value=d_val,
                    expected_condition=f"d <= e (e={e_val})",
                    source=f"{cls.SOURCE_OIML} Clause 3.4.1",
                    message=f"Actual scale interval d={d_val} {unit.value} cannot exceed verification scale interval e={e_val} {unit.value}.",
                )
            elif d_val < e_val - 1e-9:
                # Auxiliary indicating device in use (d < e)
                if acc_class in (AccuracyClass.CLASS_III, AccuracyClass.CLASS_IIII):
                    result.add_error(
                        rule_id="RULE_AUXILIARY_DEVICE_PROHIBITED",
                        field=f"{pfx}d",
                        actual_value=f"d={d_val} < e={e_val}",
                        expected_condition=f"d must equal e for {acc_class.roman}",
                        source=f"{cls.SOURCE_OIML} Clause 3.4.1 / {cls.SOURCE_INDIAN}",
                        message=(
                            f"Auxiliary indicating devices with differentiated scale interval (d < e) "
                            f"are strictly PROHIBITED for {acc_class.roman}. d must equal e."
                        ),
                    )
                if is_multi_interval:
                    result.add_error(
                        rule_id="RULE_AUXILIARY_DEVICE_MULTI_INTERVAL",
                        field=f"{pfx}d",
                        actual_value=f"d={d_val} < e={e_val}",
                        expected_condition="d_i = e_i on multi-interval instruments",
                        source=f"{cls.SOURCE_OIML} Clause 3.4.1",
                        message="Auxiliary indicating devices (d < e) are strictly prohibited on multi-interval instruments.",
                    )
                if e_val > 10 * d_val + 1e-9:
                    result.add_error(
                        rule_id="RULE_E_EXCEEDS_10D",
                        field=f"{pfx}e",
                        actual_value=f"e={e_val} > 10*d ({10*d_val})",
                        expected_condition="d < e <= 10d",
                        source=f"{cls.SOURCE_OIML} Clause 3.4.2",
                        message=f"Verification scale interval e={e_val} exceeds 10 * d (10 * {d_val} = {10*d_val}).",
                    )

        # 7. Accuracy Class Specific Statutory Limits (OIML Table 3 / IN LM Table 1)
        e_grams = unit.to_grams(e_val)
        cls._validate_class_statutory_table(
            acc_class=acc_class,
            e_val=e_val,
            e_grams=e_grams,
            min_val=min_val,
            n=n,
            unit=unit,
            result=result,
            field_prefix=field_prefix,
            check_min_capacity=check_min_capacity,
        )

        return {
            "range": field_prefix or "main",
            "Max": f"{max_val} {unit.value}",
            "Min": f"{min_val} {unit.value}",
            "e": f"{e_val} {unit.value}",
            "d": f"{actual_d} {unit.value}",
            "n": round(n, 4),
            "e_in_grams": round(e_grams, 6),
        }

    @classmethod
    def _validate_class_statutory_table(
        cls,
        acc_class: AccuracyClass,
        e_val: float,
        e_grams: float,
        min_val: float,
        n: float,
        unit: MassUnit,
        result: ClassificationValidationResult,
        field_prefix: str = "",
        check_min_capacity: bool = True,
    ) -> None:
        """Validates e in grams, n_min, n_max, and Min capacity factor against Table 3 / Table 1."""
        pfx = f"{field_prefix}." if field_prefix else ""
        tol = 1e-9

        # CLASS I (Special Accuracy)
        if acc_class == AccuracyClass.CLASS_I:
            # Rule: e >= 0.001 g (1 mg)
            if e_grams < (0.001 - tol):
                result.add_error(
                    rule_id="RULE_CLASS_I_E_MIN",
                    field=f"{pfx}e",
                    actual_value=f"{e_val} {unit.value} ({e_grams:.4g} g)",
                    expected_condition="e >= 0.001 g (1 mg)",
                    source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class I)",
                    message=f"For Class I, verification scale interval e must be >= 0.001 g (1 mg). Received {e_grams:.4g} g.",
                )

            # Rule: n_min = 50,000; no n_max
            if n < (50000.0 - tol):
                result.add_error(
                    rule_id="RULE_CLASS_I_N_MIN",
                    field=f"{pfx}n",
                    actual_value=f"{n:,.1f}",
                    expected_condition="n >= 50,000",
                    source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class I)",
                    message=f"For Class I, scale interval count n must be >= 50,000. Received n = {n:,.1f}.",
                )

            # Rule: Min >= 100e
            if check_min_capacity:
                req_min = 100.0 * e_val
                if min_val < (req_min - tol):
                    result.add_error(
                        rule_id="RULE_CLASS_I_MIN_CAPACITY",
                        field=f"{pfx}Min",
                        actual_value=f"{min_val} {unit.value}",
                        expected_condition=f"Min >= 100 * e ({req_min} {unit.value})",
                        source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class I)",
                        message=f"For Class I, minimum capacity Min must be >= 100e ({req_min} {unit.value}). Received {min_val} {unit.value}.",
                    )

        # CLASS II (High Accuracy)
        elif acc_class == AccuracyClass.CLASS_II:
            # Band A: 0.001 g <= e <= 0.05 g
            # Band B: e >= 0.1 g
            if e_grams < (0.001 - tol):
                result.add_error(
                    rule_id="RULE_CLASS_II_E_MIN",
                    field=f"{pfx}e",
                    actual_value=f"{e_val} {unit.value} ({e_grams:.4g} g)",
                    expected_condition="e >= 0.001 g (1 mg)",
                    source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class II)",
                    message=f"For Class II, verification scale interval e must be >= 0.001 g (1 mg). Received {e_grams:.4g} g.",
                )
            elif (0.05 + tol) < e_grams < (0.1 - tol):
                result.add_error(
                    rule_id="RULE_CLASS_II_E_GAP",
                    field=f"{pfx}e",
                    actual_value=f"{e_val} {unit.value} ({e_grams:.4g} g)",
                    expected_condition="e in [0.001 g, 0.05 g] or e >= 0.1 g",
                    source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class II)",
                    message=(
                        f"Verification scale interval e={e_grams:.4g} g falls into the statutory gap "
                        f"between 0.05 g and 0.1 g. Table 1 only recognizes 0.001 g <= e <= 0.05 g or e >= 0.1 g."
                    ),
                )
            elif e_grams <= (0.05 + tol):
                # Band A: n in [100, 100,000], Min >= 20e
                if n < (100.0 - tol):
                    result.add_error(
                        rule_id="RULE_CLASS_II_N_MIN",
                        field=f"{pfx}n",
                        actual_value=f"{n:,.1f}",
                        expected_condition="n >= 100 (for e <= 0.05 g)",
                        source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class II)",
                        message=f"For Class II (e <= 0.05 g), n must be >= 100. Received n = {n:,.1f}.",
                    )
                if n > (100000.0 + tol):
                    result.add_error(
                        rule_id="RULE_CLASS_II_N_MAX",
                        field=f"{pfx}n",
                        actual_value=f"{n:,.1f}",
                        expected_condition="n <= 100,000",
                        source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class II)",
                        message=f"For Class II, n cannot exceed 100,000. Received n = {n:,.1f}.",
                    )
                if check_min_capacity:
                    req_min = 20.0 * e_val
                    if min_val < (req_min - tol):
                        result.add_error(
                            rule_id="RULE_CLASS_II_MIN_CAPACITY",
                            field=f"{pfx}Min",
                            actual_value=f"{min_val} {unit.value}",
                            expected_condition=f"Min >= 20 * e ({req_min} {unit.value})",
                            source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class II)",
                            message=f"For Class II (e <= 0.05 g), Min must be >= 20e ({req_min} {unit.value}). Received {min_val} {unit.value}.",
                        )
            else:
                # Band B: e >= 0.1 g: n in [5000, 100,000], Min >= 50e
                if n < (5000.0 - tol):
                    result.add_error(
                        rule_id="RULE_CLASS_II_N_MIN",
                        field=f"{pfx}n",
                        actual_value=f"{n:,.1f}",
                        expected_condition="n >= 5,000 (for e >= 0.1 g)",
                        source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class II)",
                        message=f"For Class II (e >= 0.1 g), n must be >= 5,000. Received n = {n:,.1f}.",
                    )
                if n > (100000.0 + tol):
                    result.add_error(
                        rule_id="RULE_CLASS_II_N_MAX",
                        field=f"{pfx}n",
                        actual_value=f"{n:,.1f}",
                        expected_condition="n <= 100,000",
                        source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class II)",
                        message=f"For Class II, n cannot exceed 100,000. Received n = {n:,.1f}.",
                    )
                if check_min_capacity:
                    req_min = 50.0 * e_val
                    if min_val < (req_min - tol):
                        result.add_error(
                            rule_id="RULE_CLASS_II_MIN_CAPACITY",
                            field=f"{pfx}Min",
                            actual_value=f"{min_val} {unit.value}",
                            expected_condition=f"Min >= 50 * e ({req_min} {unit.value})",
                            source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class II)",
                            message=f"For Class II (e >= 0.1 g), Min must be >= 50e ({req_min} {unit.value}). Received {min_val} {unit.value}.",
                        )

        # CLASS III (Medium Accuracy)
        elif acc_class == AccuracyClass.CLASS_III:
            # Band A: 0.1 g <= e <= 2 g (n in [100, 10,000], Min >= 20e)
            # Band B: e >= 5 g (n in [500, 10,000], Min >= 20e)
            if e_grams < (0.1 - tol):
                result.add_error(
                    rule_id="RULE_CLASS_III_E_MIN",
                    field=f"{pfx}e",
                    actual_value=f"{e_val} {unit.value} ({e_grams:.4g} g)",
                    expected_condition="e >= 0.1 g (100 mg)",
                    source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class III)",
                    message=f"For Class III, verification scale interval e must be >= 0.1 g. Received {e_grams:.4g} g.",
                )
            elif (2.0 + tol) < e_grams < (5.0 - tol):
                result.add_error(
                    rule_id="RULE_CLASS_III_E_GAP",
                    field=f"{pfx}e",
                    actual_value=f"{e_val} {unit.value} ({e_grams:.4g} g)",
                    expected_condition="e in [0.1 g, 2 g] or e >= 5 g",
                    source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class III)",
                    message=f"Verification scale interval e={e_grams:.4g} g falls into statutory gap between 2 g and 5 g.",
                )
            elif e_grams <= (2.0 + tol):
                # Band A: n in [100, 10000]
                if n < (100.0 - tol):
                    result.add_error(
                        rule_id="RULE_CLASS_III_N_MIN",
                        field=f"{pfx}n",
                        actual_value=f"{n:,.1f}",
                        expected_condition="n >= 100 (for 0.1 g <= e <= 2 g)",
                        source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class III)",
                        message=f"For Class III (0.1 g <= e <= 2 g), n must be >= 100. Received n = {n:,.1f}.",
                    )
                if n > (10000.0 + tol):
                    result.add_error(
                        rule_id="RULE_CLASS_III_N_MAX",
                        field=f"{pfx}n",
                        actual_value=f"{n:,.1f}",
                        expected_condition="n <= 10,000",
                        source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class III)",
                        message=f"For Class III, n cannot exceed 10,000. Received n = {n:,.1f}.",
                    )
            else:
                # Band B: e >= 5 g: n in [500, 10000]
                if n < (500.0 - tol):
                    result.add_error(
                        rule_id="RULE_CLASS_III_N_MIN",
                        field=f"{pfx}n",
                        actual_value=f"{n:,.1f}",
                        expected_condition="n >= 500 (for e >= 5 g)",
                        source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class III)",
                        message=f"For Class III (e >= 5 g), n must be >= 500. Received n = {n:,.1f}.",
                    )
                if n > (10000.0 + tol):
                    result.add_error(
                        rule_id="RULE_CLASS_III_N_MAX",
                        field=f"{pfx}n",
                        actual_value=f"{n:,.1f}",
                        expected_condition="n <= 10,000",
                        source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class III)",
                        message=f"For Class III, n cannot exceed 10,000. Received n = {n:,.1f}.",
                    )

            # Min >= 20e
            if check_min_capacity:
                req_min = 20.0 * e_val
                if min_val < (req_min - tol):
                    result.add_error(
                        rule_id="RULE_CLASS_III_MIN_CAPACITY",
                        field=f"{pfx}Min",
                        actual_value=f"{min_val} {unit.value}",
                        expected_condition=f"Min >= 20 * e ({req_min} {unit.value})",
                        source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class III)",
                        message=f"For Class III, Min must be >= 20e ({req_min} {unit.value}). Received {min_val} {unit.value}.",
                    )

        # CLASS IIII (Ordinary Accuracy)
        elif acc_class == AccuracyClass.CLASS_IIII:
            # Rule: e >= 5 g
            if e_grams < (5.0 - tol):
                result.add_error(
                    rule_id="RULE_CLASS_IIII_E_MIN",
                    field=f"{pfx}e",
                    actual_value=f"{e_val} {unit.value} ({e_grams:.4g} g)",
                    expected_condition="e >= 5 g",
                    source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class IIII)",
                    message=f"For Class IIII, verification scale interval e must be >= 5 g. Received {e_grams:.4g} g.",
                )

            # Rule: n in [100, 1000]
            if n < (100.0 - tol):
                result.add_error(
                    rule_id="RULE_CLASS_IIII_N_MIN",
                    field=f"{pfx}n",
                    actual_value=f"{n:,.1f}",
                    expected_condition="n >= 100",
                    source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class IIII)",
                    message=f"For Class IIII, scale interval count n must be >= 100. Received n = {n:,.1f}.",
                )
            if n > (1000.0 + tol):
                result.add_error(
                    rule_id="RULE_CLASS_IIII_N_MAX",
                    field=f"{pfx}n",
                    actual_value=f"{n:,.1f}",
                    expected_condition="n <= 1,000",
                    source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class IIII)",
                    message=f"For Class IIII, scale interval count n cannot exceed 1,000. Received n = {n:,.1f}.",
                )

            # Rule: Min >= 10e
            if check_min_capacity:
                req_min = 10.0 * e_val
                if min_val < (req_min - tol):
                    result.add_error(
                        rule_id="RULE_CLASS_IIII_MIN_CAPACITY",
                        field=f"{pfx}Min",
                        actual_value=f"{min_val} {unit.value}",
                        expected_condition=f"Min >= 10 * e ({req_min} {unit.value})",
                        source=f"{cls.SOURCE_INDIAN} Table 1 / OIML Table 3 (Class IIII)",
                        message=f"For Class IIII, minimum capacity Min must be >= 10e ({req_min} {unit.value}). Received {min_val} {unit.value}.",
                    )

    @classmethod
    def _validate_multi_interval(
        cls,
        data: Dict[str, Any],
        acc_class: AccuracyClass,
        unit: MassUnit,
        result: ClassificationValidationResult,
    ) -> None:
        """Validates multi-interval instruments and flags manual review requirements."""
        ranges = data.get("partial_ranges") or data.get("ranges") or []

        if not ranges or len(ranges) < 2:
            result.add_error(
                rule_id="RULE_MULTI_INTERVAL_MIN_RANGES",
                field="partial_ranges",
                actual_value=len(ranges),
                expected_condition="At least 2 partial weighing ranges",
                source=f"{cls.SOURCE_OIML} Clause 3.3",
                message="Multi-interval instruments must declare at least 2 partial weighing ranges.",
            )
            return

        # Multi-interval triggers mandatory manual review
        result.flag_manual_review(
            "Multi-interval scale requires physical verification of automatic scale interval changeover on increasing load."
        )
        result.flag_manual_review(
            "Inspect tare operation and zero-return behavior across partial weighing range boundaries."
        )

        # Validate each partial range
        prev_max = 0.0
        prev_e = 0.0

        for i, pr in enumerate(ranges):
            idx = pr.get("range_index", i + 1)
            pfx = f"partial_ranges[{idx}]"

            max_raw = pr.get("Max") if pr.get("Max") is not None else pr.get("max_capacity")
            max_val, err = _safe_float(max_raw)
            if err:
                result.add_error("RULE_MAX_INVALID", f"{pfx}.Max", max_raw, "Number", cls.SOURCE_INDIAN, err)
                continue

            min_raw = pr.get("Min") if pr.get("Min") is not None else pr.get("min_capacity")
            min_val, err = _safe_float(min_raw)
            if err:
                result.add_error("RULE_MIN_INVALID", f"{pfx}.Min", min_raw, "Number", cls.SOURCE_INDIAN, err)
                continue

            e_raw = pr.get("e") if pr.get("e") is not None else pr.get("verification_scale_interval")
            e_val, err = _safe_float(e_raw)
            if err:
                result.add_error("RULE_E_INVALID", f"{pfx}.e", e_raw, "Number", cls.SOURCE_INDIAN, err)
                continue

            d_val = pr.get("d")
            if d_val is not None:
                d_val, _ = _safe_float(d_val)

            # Ordering checks
            if i > 0:
                if e_val <= prev_e:
                    result.add_error(
                        rule_id="RULE_MULTI_INTERVAL_E_ORDER",
                        field=f"{pfx}.e",
                        actual_value=f"e_{idx}={e_val} <= e_{idx-1}={prev_e}",
                        expected_condition="e_1 < e_2 < ... < e_r",
                        source=f"{cls.SOURCE_OIML} Clause 3.3.1",
                        message=f"Partial range #{idx} scale interval ({e_val}) must be strictly greater than range #{idx-1} ({prev_e}).",
                    )
                if max_val <= prev_max:
                    result.add_error(
                        rule_id="RULE_MULTI_INTERVAL_MAX_ORDER",
                        field=f"{pfx}.Max",
                        actual_value=f"Max_{idx}={max_val} <= Max_{idx-1}={prev_max}",
                        expected_condition="Max_1 < Max_2 < ... < Max_r",
                        source=f"{cls.SOURCE_OIML} Clause 3.3.1",
                        message=f"Partial range #{idx} capacity ({max_val}) must be strictly greater than range #{idx-1} ({prev_max}).",
                    )

            prev_max = max_val
            prev_e = e_val

            # Validate partial range
            range_summary = cls._validate_capacity_and_intervals(
                max_val=max_val,
                min_val=min_val,
                e_val=e_val,
                d_val=d_val,
                user_n=pr.get("n"),
                acc_class=acc_class,
                unit=unit,
                result=result,
                field_prefix=pfx,
                is_multi_interval=True,
                check_min_capacity=(i == 0),
            )
            result.ranges_evaluated.append(range_summary)

    @classmethod
    def _validate_multi_range(
        cls,
        data: Dict[str, Any],
        acc_class: AccuracyClass,
        unit: MassUnit,
        result: ClassificationValidationResult,
    ) -> None:
        """Validates multi-range instruments where each range operates independently."""
        ranges = data.get("ranges") or data.get("partial_ranges") or []

        if not ranges or len(ranges) < 2:
            result.add_error(
                rule_id="RULE_MULTI_RANGE_MIN_RANGES",
                field="ranges",
                actual_value=len(ranges),
                expected_condition="At least 2 independent weighing ranges",
                source=f"{cls.SOURCE_OIML} Clause 3.2.2",
                message="Multi-range instruments must declare at least 2 independent weighing ranges.",
            )
            return

        result.flag_manual_review(
            "Multi-range instrument requires physical verification of manual/automatic range switching and indicator clarity."
        )

        for i, rng in enumerate(ranges):
            idx = rng.get("range_index", i + 1)
            pfx = f"ranges[{idx}]"

            max_raw = rng.get("Max") if rng.get("Max") is not None else rng.get("max_capacity")
            max_val, err = _safe_float(max_raw)
            if err:
                result.add_error("RULE_MAX_INVALID", f"{pfx}.Max", max_raw, "Number", cls.SOURCE_INDIAN, err)
                continue

            min_raw = rng.get("Min") if rng.get("Min") is not None else rng.get("min_capacity")
            min_val, err = _safe_float(min_raw)
            if err:
                result.add_error("RULE_MIN_INVALID", f"{pfx}.Min", min_raw, "Number", cls.SOURCE_INDIAN, err)
                continue

            e_raw = rng.get("e") if rng.get("e") is not None else rng.get("verification_scale_interval")
            e_val, err = _safe_float(e_raw)
            if err:
                result.add_error("RULE_E_INVALID", f"{pfx}.e", e_raw, "Number", cls.SOURCE_INDIAN, err)
                continue

            d_val = rng.get("d")
            if d_val is not None:
                d_val, _ = _safe_float(d_val)

            range_summary = cls._validate_capacity_and_intervals(
                max_val=max_val,
                min_val=min_val,
                e_val=e_val,
                d_val=d_val,
                user_n=rng.get("n"),
                acc_class=acc_class,
                unit=unit,
                result=result,
                field_prefix=pfx,
                is_multi_interval=False,
            )
            result.ranges_evaluated.append(range_summary)


def validate_classification(spec: Union[Dict[str, Any], Any]) -> ClassificationValidationResult:
    """Convenience functional wrapper for RegulatoryClassificationValidator.validate."""
    return RegulatoryClassificationValidator.validate(spec)
