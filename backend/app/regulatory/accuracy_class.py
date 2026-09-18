"""
MetrIQ Regulatory Engine - Accuracy Class Specifications & Validation
Implements Table 3 of OIML R 76-1:2006 and Table 1 of Indian Legal Metrology (General)
Rules, 2011 for NAWI accuracy classification and parameter boundary limits.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
from decimal import Decimal

from .models import AccuracyClass, MassUnit, InstrumentProfile
from .errors import ValidationResult, RegulatoryErrorCode, IssueSeverity
from .sources import REGULATORY_REGISTRY


@dataclass(frozen=True)
class ClassBoundary:
    """
    Statutory bounds for an accuracy class given a specific range of verification scale interval (e).
    """
    accuracy_class: AccuracyClass
    e_min_grams: float                    # Minimum allowed e (in grams)
    e_max_grams: Optional[float]          # Maximum allowed e (in grams), or None if unbounded
    n_min: int                            # Minimum number of scale intervals (n = Max / e)
    n_max: Optional[int]                  # Maximum number of scale intervals, or None if unbounded
    min_capacity_factor: int              # Factor k such that Min = k * e (e.g. 100, 50, 20, 10)
    reference_clause: str

    def matches_e(self, e_grams: float) -> bool:
        """Determines if the verification scale interval e falls into this classification band."""
        # Use a small tolerance for floating point comparisons
        tol = 1e-9
        if e_grams < (self.e_min_grams - tol):
            return False
        if self.e_max_grams is not None and e_grams > (self.e_max_grams + tol):
            return False
        return True


# Statutory classification matrix per Table 3 of OIML R 76-1:2006 / Table 1 Indian LM Rules
CLASS_BOUNDARIES: List[ClassBoundary] = [
    # Class I: Special Accuracy
    ClassBoundary(
        accuracy_class=AccuracyClass.CLASS_I,
        e_min_grams=0.001,      # 1 mg
        e_max_grams=None,
        n_min=50000,
        n_max=None,             # No upper limit
        min_capacity_factor=100,# Min = 100 e
        reference_clause="OIML R 76-1:2006 Table 3 / IN LM 2011 Table 1 (Class I)",
    ),

    # Class II: High Accuracy - Band A (0.001 g <= e <= 0.05 g)
    ClassBoundary(
        accuracy_class=AccuracyClass.CLASS_II,
        e_min_grams=0.001,      # 1 mg
        e_max_grams=0.05,       # 50 mg
        n_min=100,
        n_max=100000,
        min_capacity_factor=20, # Min = 20 e
        reference_clause="OIML R 76-1:2006 Table 3 / IN LM 2011 Table 1 (Class II, e <= 0.05g)",
    ),

    # Class II: High Accuracy - Band B (0.1 g <= e)
    ClassBoundary(
        accuracy_class=AccuracyClass.CLASS_II,
        e_min_grams=0.1,        # 100 mg
        e_max_grams=None,
        n_min=5000,
        n_max=100000,
        min_capacity_factor=50, # Min = 50 e
        reference_clause="OIML R 76-1:2006 Table 3 / IN LM 2011 Table 1 (Class II, e >= 0.1g)",
    ),

    # Class III: Medium Accuracy - Band A (0.1 g <= e <= 2 g)
    ClassBoundary(
        accuracy_class=AccuracyClass.CLASS_III,
        e_min_grams=0.1,        # 100 mg
        e_max_grams=2.0,        # 2 g
        n_min=100,
        n_max=10000,
        min_capacity_factor=20, # Min = 20 e
        reference_clause="OIML R 76-1:2006 Table 3 / IN LM 2011 Table 1 (Class III, 0.1g <= e <= 2g)",
    ),

    # Class III: Medium Accuracy - Band B (5 g <= e)
    ClassBoundary(
        accuracy_class=AccuracyClass.CLASS_III,
        e_min_grams=5.0,        # 5 g
        e_max_grams=None,
        n_min=500,
        n_max=10000,
        min_capacity_factor=20, # Min = 20 e
        reference_clause="OIML R 76-1:2006 Table 3 / IN LM 2011 Table 1 (Class III, e >= 5g)",
    ),

    # Class IIII: Ordinary Accuracy (5 g <= e)
    ClassBoundary(
        accuracy_class=AccuracyClass.CLASS_IIII,
        e_min_grams=5.0,        # 5 g
        e_max_grams=None,
        n_min=100,
        n_max=1000,
        min_capacity_factor=10, # Min = 10 e
        reference_clause="OIML R 76-1:2006 Table 3 / IN LM 2011 Table 1 (Class IIII)",
    ),
]


def get_class_boundary(accuracy_class: AccuracyClass, e_in_grams: float) -> Optional[ClassBoundary]:
    """
    Finds the statutory boundary specification for the given accuracy class and verification scale interval (in grams).
    """
    for boundary in CLASS_BOUNDARIES:
        if boundary.accuracy_class == accuracy_class and boundary.matches_e(e_in_grams):
            return boundary
    return None


def determine_eligible_classes(
    e: float,
    max_capacity: float,
    min_capacity: float,
    unit: MassUnit = MassUnit.KG,
) -> List[Tuple[AccuracyClass, str]]:
    """
    Evaluates an instrument's parameters against all statutory accuracy classes and returns
    a list of eligible accuracy classes along with justification.
    """
    e_grams = unit.to_grams(e)
    max_grams = unit.to_grams(max_capacity)
    min_grams = unit.to_grams(min_capacity)
    n = max_capacity / e if e > 0 else 0

    eligible: List[Tuple[AccuracyClass, str]] = []

    for boundary in CLASS_BOUNDARIES:
        if not boundary.matches_e(e_grams):
            continue

        # Check n bounds
        if n < boundary.n_min:
            continue
        if boundary.n_max is not None and n > boundary.n_max:
            continue

        # Check Min capacity
        required_min = boundary.min_capacity_factor * e
        if min_capacity < (required_min - 1e-9):
            continue

        justification = (
            f"Conforms to {boundary.accuracy_class.roman}: "
            f"e={e}{unit.value} ({e_grams:.4g}g), n={int(round(n)):,} in [{boundary.n_min:,}, {boundary.n_max or 'inf'}], "
            f"Min >= {boundary.min_capacity_factor}e"
        )
        eligible.append((boundary.accuracy_class, justification))

    return eligible


def validate_accuracy_class(
    instrument: InstrumentProfile,
    standard_id: str = "OIML_R76_2006",
) -> ValidationResult:
    """
    Validates the instrument's declared accuracy class against statutory table rules.
    Verifies e range, n bounds, and Min capacity.
    """
    result = ValidationResult(is_valid=True)
    source = REGULATORY_REGISTRY.get_or_default(standard_id)

    if not isinstance(instrument.accuracy_class, AccuracyClass):
        try:
            acc_class = AccuracyClass.from_string(str(instrument.accuracy_class))
        except ValueError:
            result.add_error(
                code=RegulatoryErrorCode.INVALID_ACCURACY_CLASS,
                message=f"Invalid or unrecognized accuracy class '{instrument.accuracy_class}'",
                field="accuracy_class",
                reference_clause=f"{source.short_title} Clause 3.2",
            )
            return result
    else:
        acc_class = instrument.accuracy_class

    e_grams = instrument.unit.to_grams(instrument.e)
    boundary = get_class_boundary(acc_class, e_grams)

    if not boundary:
        # Check why boundary was not found
        # Did e fall outside the allowed values for this class?
        if acc_class == AccuracyClass.CLASS_I and e_grams < 0.001:
            result.add_error(
                code=RegulatoryErrorCode.CLASS_CAPACITY_INCOMPATIBLE,
                message=f"For Class I, verification scale interval e must be >= 0.001 g (1 mg). Received {e_grams:.4g} g.",
                field="e",
                reference_clause=f"{source.short_title} Table 3 / Class I",
                suggestion="Increase verification scale interval e to at least 1 mg.",
            )
        elif acc_class in (AccuracyClass.CLASS_III, AccuracyClass.CLASS_IIII) and e_grams < 0.1:
            result.add_error(
                code=RegulatoryErrorCode.CLASS_CAPACITY_INCOMPATIBLE,
                message=f"For {acc_class.roman}, verification scale interval e must be >= 0.1 g (5 g for IIII). Received {e_grams:.4g} g.",
                field="e",
                reference_clause=f"{source.short_title} Table 3",
                suggestion=f"Increase e or consider Class I or II for precision below 0.1 g.",
            )
        else:
            result.add_error(
                code=RegulatoryErrorCode.CLASS_CAPACITY_INCOMPATIBLE,
                message=f"Verification scale interval e={instrument.e} {instrument.unit.value} ({e_grams:.4g} g) is outside permitted range for {acc_class.display_name}.",
                field="e",
                reference_clause=f"{source.short_title} Table 3",
            )
        return result

    # Check n = Max / e
    n = instrument.n
    if n < boundary.n_min:
        result.add_error(
            code=RegulatoryErrorCode.N_OUT_OF_BOUNDS,
            message=(
                f"Number of scale intervals n = {n:,.1f} is below minimum {boundary.n_min:,} "
                f"required for {acc_class.roman} (e={instrument.e} {instrument.unit.value})."
            ),
            field="n",
            reference_clause=boundary.reference_clause,
            suggestion=f"Increase Max capacity or select an accuracy class with lower minimum n.",
        )

    if boundary.n_max is not None and n > boundary.n_max:
        result.add_error(
            code=RegulatoryErrorCode.N_OUT_OF_BOUNDS,
            message=(
                f"Number of scale intervals n = {n:,.1f} exceeds maximum {boundary.n_max:,} "
                f"permitted for {acc_class.roman} (e={instrument.e} {instrument.unit.value})."
            ),
            field="n",
            reference_clause=boundary.reference_clause,
            suggestion=f"Select a higher accuracy class (e.g., Class II or Class I) capable of handling n > {boundary.n_max:,}.",
        )

    # Check Min capacity
    required_min = boundary.min_capacity_factor * instrument.e
    tol = 1e-7
    if instrument.min_capacity < (required_min - tol):
        result.add_error(
            code=RegulatoryErrorCode.MIN_CAPACITY_VIOLATION,
            message=(
                f"Minimum capacity Min = {instrument.min_capacity} {instrument.unit.value} is below statutory limit "
                f"{required_min} {instrument.unit.value} ({boundary.min_capacity_factor} * e) for {acc_class.roman}."
            ),
            field="min_capacity",
            reference_clause=boundary.reference_clause,
            suggestion=f"Set Min capacity to at least {required_min} {instrument.unit.value}.",
        )

    return result
