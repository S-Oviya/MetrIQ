"""
MetrIQ Regulatory Engine - Maximum Permissible Error (MPE) Calculation Engine
=============================================================================

Statutory & Technical Basis:
- OIML R 76-1:2006 Clause 3.5 & Table 6
- Indian Legal Metrology (General) Rules, 2011:
  * Seventh Schedule (Part I, Table 2) - Non-Automatic Weighing Instruments
  * Seventh Schedule (Part I, Clause 4) - Maximum Permissible Errors on Verification

This module implements the complete, structured MPE engine utilizing high-precision
exact decimal arithmetic (via decimal.Decimal) to prevent binary floating-point drift,
preserve exact statutory boundary transitions, and eliminate arbitrary tolerances that
could alter regulatory outcomes.

Key Capabilities:
1. Initial Verification MPE (+/- 0.5e, +/- 1.0e, +/- 1.5e).
2. Subsequent / In-Service Verification MPE (+/- 1.0e, +/- 2.0e, +/- 3.0e; exactly 2 x initial).
3. Dual-Unit Representation: MPE in scale intervals (e) and measurement units (kg, g, etc.).
4. Exact Boundary Evaluation: Strict discrimination between boundary value (e.g. 5000e)
   and just-over-boundary (e.g. 5000.001e).
5. Observed Error Assessment: Strict statutory tolerance check (|observed_error| <= MPE)
   with precise margin reporting (pass, fail, margin).
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from .models import AccuracyClass, JobType, MassUnit


class VerificationType(str, Enum):
    """Statutory verification classification."""
    INITIAL = "INITIAL"
    SUBSEQUENT = "SUBSEQUENT"

    @classmethod
    def from_value(cls, val: Union[str, bool, "VerificationType", JobType, None]) -> "VerificationType":
        """
        Parses and normalizes verification type from string, boolean, or JobType.
        - True / 'in_service' / 'subsequent' / 're_verification' -> SUBSEQUENT
        - False / 'initial' / 'initial_verification' / 'model_approval' -> INITIAL
        """
        if val is None:
            return cls.INITIAL
        if isinstance(val, VerificationType):
            return val
        if isinstance(val, bool):
            return cls.SUBSEQUENT if val else cls.INITIAL
        if isinstance(val, JobType):
            return cls.SUBSEQUENT if val.is_in_service else cls.INITIAL

        clean = str(val).strip().upper().replace("-", "_")
        if clean in ("SUBSEQUENT", "IN_SERVICE", "RE_VERIFICATION", "POST_REPAIR", "POST_RELOCATION", "PERIODIC"):
            return cls.SUBSEQUENT
        if clean in ("INITIAL", "INITIAL_VERIFICATION", "MODEL_APPROVAL", "TYPE_APPROVAL", "FACTORY"):
            return cls.INITIAL

        raise ValueError(
            f"Invalid verification type '{val}'. Supported types: 'INITIAL' or 'SUBSEQUENT' "
            "(or aliases 'in_service', 'initial_verification', etc.)."
        )

    @property
    def multiplier(self) -> Decimal:
        """Statutory MPE multiplier relative to initial verification."""
        return Decimal("1.0") if self == self.INITIAL else Decimal("2.0")


@dataclass(frozen=True)
class MPEBandDefinition:
    """
    Structured definition for an MPE load band per OIML R 76-1 Table 6 / IN LM 2011 Table 2.
    
    Attributes:
        band_index: Band identifier (1, 2, or 3).
        min_load_e: Minimum load for this band expressed in e.
        max_load_e: Maximum load for this band expressed in e.
        mpe_initial_e: Initial verification MPE in e (0.5, 1.0, or 1.5).
        mpe_subsequent_e: Subsequent verification MPE in e (1.0, 2.0, or 3.0; 2x initial).
        inclusive_lower: True if lower boundary is inclusive (m >= min_e). False if exclusive (m > min_e).
        inclusive_upper: True if upper boundary is inclusive (m <= max_e).
        description: Standard readable description of the interval.
    """
    band_index: int
    min_load_e: Decimal
    max_load_e: Decimal
    mpe_initial_e: Decimal
    mpe_subsequent_e: Decimal
    inclusive_lower: bool
    inclusive_upper: bool = True
    description: str = ""

    def matches(self, load_e: Decimal) -> bool:
        """Evaluates whether load_e falls within this band without arbitrary tolerances."""
        if self.inclusive_lower:
            lower_ok = load_e >= self.min_load_e
        else:
            lower_ok = load_e > self.min_load_e

        if self.inclusive_upper:
            upper_ok = load_e <= self.max_load_e
        else:
            upper_ok = load_e < self.max_load_e

        return lower_ok and upper_ok


# Statutory lookup tables structured strictly according to OIML R 76-1 Table 6
# and Indian Legal Metrology (General) Rules, 2011 Seventh Schedule Table 2
MPE_STATUTORY_TABLE: Dict[AccuracyClass, List[MPEBandDefinition]] = {
    AccuracyClass.CLASS_I: [
        MPEBandDefinition(
            band_index=1,
            min_load_e=Decimal("0"),
            max_load_e=Decimal("50000"),
            mpe_initial_e=Decimal("0.5"),
            mpe_subsequent_e=Decimal("1.0"),
            inclusive_lower=True,
            inclusive_upper=True,
            description="0 <= m <= 50,000 e",
        ),
        MPEBandDefinition(
            band_index=2,
            min_load_e=Decimal("50000"),
            max_load_e=Decimal("200000"),
            mpe_initial_e=Decimal("1.0"),
            mpe_subsequent_e=Decimal("2.0"),
            inclusive_lower=False,
            inclusive_upper=True,
            description="50,000 e < m <= 200,000 e",
        ),
        MPEBandDefinition(
            band_index=3,
            min_load_e=Decimal("200000"),
            max_load_e=Decimal("1000000"),
            mpe_initial_e=Decimal("1.5"),
            mpe_subsequent_e=Decimal("3.0"),
            inclusive_lower=False,
            inclusive_upper=True,
            description="200,000 e < m <= 1,000,000 e",
        ),
    ],
    AccuracyClass.CLASS_II: [
        MPEBandDefinition(
            band_index=1,
            min_load_e=Decimal("0"),
            max_load_e=Decimal("5000"),
            mpe_initial_e=Decimal("0.5"),
            mpe_subsequent_e=Decimal("1.0"),
            inclusive_lower=True,
            inclusive_upper=True,
            description="0 <= m <= 5,000 e",
        ),
        MPEBandDefinition(
            band_index=2,
            min_load_e=Decimal("5000"),
            max_load_e=Decimal("20000"),
            mpe_initial_e=Decimal("1.0"),
            mpe_subsequent_e=Decimal("2.0"),
            inclusive_lower=False,
            inclusive_upper=True,
            description="5,000 e < m <= 20,000 e",
        ),
        MPEBandDefinition(
            band_index=3,
            min_load_e=Decimal("20000"),
            max_load_e=Decimal("100000"),
            mpe_initial_e=Decimal("1.5"),
            mpe_subsequent_e=Decimal("3.0"),
            inclusive_lower=False,
            inclusive_upper=True,
            description="20,000 e < m <= 100,000 e",
        ),
    ],
    AccuracyClass.CLASS_III: [
        MPEBandDefinition(
            band_index=1,
            min_load_e=Decimal("0"),
            max_load_e=Decimal("500"),
            mpe_initial_e=Decimal("0.5"),
            mpe_subsequent_e=Decimal("1.0"),
            inclusive_lower=True,
            inclusive_upper=True,
            description="0 <= m <= 500 e",
        ),
        MPEBandDefinition(
            band_index=2,
            min_load_e=Decimal("500"),
            max_load_e=Decimal("2000"),
            mpe_initial_e=Decimal("1.0"),
            mpe_subsequent_e=Decimal("2.0"),
            inclusive_lower=False,
            inclusive_upper=True,
            description="500 e < m <= 2,000 e",
        ),
        MPEBandDefinition(
            band_index=3,
            min_load_e=Decimal("2000"),
            max_load_e=Decimal("10000"),
            mpe_initial_e=Decimal("1.5"),
            mpe_subsequent_e=Decimal("3.0"),
            inclusive_lower=False,
            inclusive_upper=True,
            description="2,000 e < m <= 10,000 e",
        ),
    ],
    AccuracyClass.CLASS_IIII: [
        MPEBandDefinition(
            band_index=1,
            min_load_e=Decimal("0"),
            max_load_e=Decimal("50"),
            mpe_initial_e=Decimal("0.5"),
            mpe_subsequent_e=Decimal("1.0"),
            inclusive_lower=True,
            inclusive_upper=True,
            description="0 <= m <= 50 e",
        ),
        MPEBandDefinition(
            band_index=2,
            min_load_e=Decimal("50"),
            max_load_e=Decimal("200"),
            mpe_initial_e=Decimal("1.0"),
            mpe_subsequent_e=Decimal("2.0"),
            inclusive_lower=False,
            inclusive_upper=True,
            description="50 e < m <= 200 e",
        ),
        MPEBandDefinition(
            band_index=3,
            min_load_e=Decimal("200"),
            max_load_e=Decimal("1000"),
            mpe_initial_e=Decimal("1.5"),
            mpe_subsequent_e=Decimal("3.0"),
            inclusive_lower=False,
            inclusive_upper=True,
            description="200 e < m <= 1,000 e",
        ),
    ],
}


def _to_decimal(value: Any, param_name: str = "value") -> Decimal:
    """Converts input safely to Decimal via string representation to preserve decimal accuracy."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, str)):
        try:
            return Decimal(str(value).strip())
        except InvalidOperation as e:
            raise ValueError(f"Invalid numeric format for '{param_name}': {value}") from e
    if isinstance(value, float):
        # Using str(float) in Python guarantees the exact shortest representation that round-trips
        return Decimal(str(value))
    try:
        return Decimal(str(value))
    except InvalidOperation as e:
        raise ValueError(f"Could not convert '{param_name}' to exact Decimal: {value}") from e


@dataclass
class MPECalculationResult:
    """
    Structured, comprehensive result of an MPE determination.
    
    Attributes:
        load: Applied load in instrument measurement units.
        e: Verification scale interval in instrument measurement units.
        load_in_e: Calculated load ratio (load / e).
        accuracy_class: Class identifier ("I", "II", "III", "IIII").
        verification_type: "INITIAL" or "SUBSEQUENT".
        mpe_in_e: Maximum permissible error in multiples of e (e.g. 0.5, 1.0, 1.5, 2.0, 3.0).
        mpe_absolute: Maximum permissible error in instrument measurement units (mpe_in_e * e).
        applicable_rule: Textual description of the statutory clause and applied band.
        source: Statutory citation.
        band_index: Identified band index (1, 2, or 3).
        band_description: Load range description (e.g. "0 <= m <= 500 e").
        is_within_statutory_capacity: True if load <= statutory n_max for the class.
        observed_error: Evaluated error indication (if supplied).
        passed: True if abs(observed_error) <= mpe_absolute; False if exceeded; None if not evaluated.
        fail: True if abs(observed_error) > mpe_absolute; False if within; None if not evaluated.
        margin: Remaining tolerance margin (mpe_absolute - abs(observed_error)).
        margin_in_e: Remaining margin expressed in e.
    """
    load: float
    e: float
    load_in_e: float
    accuracy_class: str
    verification_type: str
    mpe_in_e: float
    mpe_absolute: float
    applicable_rule: str
    source: str
    band_index: int
    band_description: str
    is_within_statutory_capacity: bool = True
    observed_error: Optional[float] = None
    passed: Optional[bool] = None
    fail: Optional[bool] = None
    margin: Optional[float] = None
    margin_in_e: Optional[float] = None

    @property
    def is_pass(self) -> Optional[bool]:
        """Convenience alias for passed."""
        return self.passed

    def to_dict(self) -> Dict[str, Any]:
        """Returns structured dictionary conforming to MetrIQ API requirements."""
        data: Dict[str, Any] = {
            "load": self.load,
            "e": self.e,
            "load_in_e": self.load_in_e,
            "accuracy_class": self.accuracy_class,
            "verification_type": self.verification_type,
            "mpe_in_e": self.mpe_in_e,
            "mpe_absolute": self.mpe_absolute,
            "applicable_rule": self.applicable_rule,
            "source": self.source,
            "band_index": self.band_index,
            "band_description": self.band_description,
            "is_within_statutory_capacity": self.is_within_statutory_capacity,
        }

        # Include evaluation fields if observed_error was evaluated
        if self.observed_error is not None:
            data["observed_error"] = self.observed_error
            data["pass"] = self.passed
            data["fail"] = self.fail
            data["margin"] = self.margin
            data["margin_in_e"] = self.margin_in_e

        return data


class MPEEngine:
    """
    High-precision statutory MPE Engine for NAWI.
    
    Provides structured table lookups, exact decimal boundary evaluation,
    dual-unit error bounds, and compliance verification for observed errors.
    """

    SOURCE_INITIAL = (
        "OIML R 76-1:2006 Clause 3.5.1 (Table 6) / "
        "Indian Legal Metrology (General) Rules, 2011 Seventh Schedule (Part I, Table 2)"
    )
    SOURCE_SUBSEQUENT = (
        "OIML R 76-1:2006 Clause 3.5.2 (Table 6 in-service, multiplier 2.0) / "
        "Indian Legal Metrology (General) Rules, 2011 Seventh Schedule (Part I, Clause 4)"
    )

    @classmethod
    def lookup_band(
        cls,
        accuracy_class: AccuracyClass,
        load_in_e: Decimal,
    ) -> Tuple[MPEBandDefinition, bool]:
        """
        Identifies the statutory MPE band for a given class and load_in_e using exact decimal comparisons.
        
        Returns:
            Tuple of (matched_band: MPEBandDefinition, is_within_statutory_capacity: bool).
        """
        bands = MPE_STATUTORY_TABLE.get(accuracy_class)
        if not bands:
            raise ValueError(f"No statutory MPE bands registered for Accuracy Class {accuracy_class}.")

        abs_load_e = abs(load_in_e)

        # 1. Match against configured statutory bands
        for band in bands:
            if band.matches(abs_load_e):
                return band, True

        # 2. If load exceeds the upper limit of Band 3 (e.g. > 10,000e for Class III or > 1,000,000e for Class I):
        # In metrological law (OIML R 76 Clause 3.5), loads in the highest interval remain at the
        # highest MPE step (1.5e initial / 3.0e subsequent), but exceed statutory capacity n_max.
        highest_band = bands[-1]
        if abs_load_e > highest_band.max_load_e:
            return highest_band, False

        # Fallback: if load is 0, Band 1 handles it via inclusive_lower=True
        return bands[0], True

    @classmethod
    def calculate(
        cls,
        accuracy_class: Union[str, AccuracyClass],
        load: Union[float, int, str, Decimal],
        e: Union[float, int, str, Decimal],
        verification_type: Union[str, bool, VerificationType, JobType] = VerificationType.INITIAL,
        observed_error: Optional[Union[float, int, str, Decimal]] = None,
        observed_error_in_e: Optional[Union[float, int, str, Decimal]] = None,
    ) -> MPECalculationResult:
        """
        Calculates Maximum Permissible Error and optionally evaluates observed error.

        :param accuracy_class: Accuracy class ('I', 'II', 'III', 'IIII' or AccuracyClass enum).
        :param load: Applied test load in instrument measurement units (e.g. kg, g).
        :param e: Verification scale interval in instrument measurement units.
        :param verification_type: 'INITIAL' or 'SUBSEQUENT' (also accepts aliases or booleans).
        :param observed_error: Observed indication error in instrument measurement units (e.g. kg).
        :param observed_error_in_e: Observed indication error expressed in multiples of e.
        :return: MPECalculationResult with complete statutory breakdown.
        """
        # 1. Parse and validate accuracy class
        if isinstance(accuracy_class, AccuracyClass):
            acc_class = accuracy_class
        else:
            acc_class = AccuracyClass.from_string(str(accuracy_class))

        # 2. Parse verification type
        v_type = VerificationType.from_value(verification_type)

        # 3. Convert inputs to high-precision Decimal
        d_load = _to_decimal(load, "load")
        d_e = _to_decimal(e, "e")

        if d_e <= Decimal("0"):
            raise ValueError(f"Verification scale interval e must be strictly positive (> 0). Received: {e}")

        # 4. Calculate exact load_in_e
        # Note: We take absolute load for band calculation while keeping original load sign in metadata
        d_abs_load = abs(d_load)
        d_load_in_e = d_abs_load / d_e

        # 5. Lookup statutory band using exact Decimal logic (zero arbitrary tolerances)
        band, is_within_capacity = cls.lookup_band(acc_class, d_load_in_e)

        # 6. Determine MPE in e
        if v_type == VerificationType.INITIAL:
            d_mpe_in_e = band.mpe_initial_e
            source_citation = cls.SOURCE_INITIAL
            type_label = "INITIAL"
        else:
            d_mpe_in_e = band.mpe_subsequent_e
            source_citation = cls.SOURCE_SUBSEQUENT
            type_label = "SUBSEQUENT"

        # 7. Calculate MPE in instrument measurement units
        d_mpe_absolute = d_mpe_in_e * d_e

        # 8. Build applicable rule string
        applicable_rule = (
            f"Table 6 (Class {acc_class.roman}, Band {band.band_index}: {band.description}) -> "
            f"MPE = +/-{d_mpe_in_e} e"
        )
        if not is_within_capacity:
            applicable_rule += f" [Note: Load exceeds statutory n_max of {band.max_load_e:,.0f} e]"
        if v_type == VerificationType.SUBSEQUENT:
            applicable_rule += " (Subsequent Verification: 2 x Initial MPE)"

        # 9. Evaluate observed error if provided
        passed = None
        fail = None
        margin = None
        margin_in_e = None
        eval_error_float = None

        if observed_error is not None or observed_error_in_e is not None:
            if observed_error is not None:
                d_obs = _to_decimal(observed_error, "observed_error")
                eval_error_float = float(d_obs)
            else:
                d_obs_e = _to_decimal(observed_error_in_e, "observed_error_in_e")
                d_obs = d_obs_e * d_e
                eval_error_float = float(d_obs)

            d_abs_obs = abs(d_obs)

            # Strict statutory verification: |observed_error| <= MPE
            # Evaluated with exact Decimal arithmetic — zero tolerance fudge!
            passed = d_abs_obs <= d_mpe_absolute
            fail = not passed

            # Margin calculation: positive when within tolerance, negative when exceeding tolerance
            d_margin = d_mpe_absolute - d_abs_obs
            d_margin_e = d_margin / d_e

            margin = float(d_margin)
            margin_in_e = float(d_margin_e)

        return MPECalculationResult(
            load=float(d_load),
            e=float(d_e),
            load_in_e=float(d_load_in_e),
            accuracy_class=acc_class.roman,
            verification_type=type_label,
            mpe_in_e=float(d_mpe_in_e),
            mpe_absolute=float(d_mpe_absolute),
            applicable_rule=applicable_rule,
            source=source_citation,
            band_index=band.band_index,
            band_description=band.description,
            is_within_statutory_capacity=is_within_capacity,
            observed_error=eval_error_float,
            passed=passed,
            fail=fail,
            margin=margin,
            margin_in_e=margin_in_e,
        )


def calculate_mpe_statutory(
    accuracy_class: Union[str, AccuracyClass],
    load: Union[float, int, str, Decimal],
    e: Union[float, int, str, Decimal],
    verification_type: Union[str, bool, VerificationType, JobType] = VerificationType.INITIAL,
    observed_error: Optional[Union[float, int, str, Decimal]] = None,
    observed_error_in_e: Optional[Union[float, int, str, Decimal]] = None,
) -> MPECalculationResult:
    """Convenience function calling MPEEngine.calculate."""
    return MPEEngine.calculate(
        accuracy_class=accuracy_class,
        load=load,
        e=e,
        verification_type=verification_type,
        observed_error=observed_error,
        observed_error_in_e=observed_error_in_e,
    )
