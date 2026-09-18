"""
MetrIQ Regulatory Engine - Core Domain Models
Data classes and enumerations representing NAWI metrological entities,
instruments, accuracy classes, test types, and test plans.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime, timezone


class MassUnit(str, Enum):
    MG = "mg"
    G = "g"
    KG = "kg"
    T = "t"
    CT = "ct"  # Metric carat: 1 ct = 0.2 g

    def to_grams(self, value: float) -> float:
        """Converts value in this unit to grams."""
        factors = {
            MassUnit.MG: 0.001,
            MassUnit.G: 1.0,
            MassUnit.KG: 1000.0,
            MassUnit.T: 1000000.0,
            MassUnit.CT: 0.2,
        }
        return value * factors[self]

    @classmethod
    def convert(cls, value: float, from_unit: "MassUnit", to_unit: "MassUnit") -> float:
        """Converts a mass value between any two supported units."""
        grams = from_unit.to_grams(value)
        to_gram_factors = {
            MassUnit.MG: 1000.0,
            MassUnit.G: 1.0,
            MassUnit.KG: 0.001,
            MassUnit.T: 0.000001,
            MassUnit.CT: 5.0,
        }
        return grams * to_gram_factors[to_unit]


class AccuracyClass(str, Enum):
    CLASS_I = "CLASS_I"
    CLASS_II = "CLASS_II"
    CLASS_III = "CLASS_III"
    CLASS_IIII = "CLASS_IIII"

    @property
    def roman(self) -> str:
        mapping = {
            AccuracyClass.CLASS_I: "I",
            AccuracyClass.CLASS_II: "II",
            AccuracyClass.CLASS_III: "III",
            AccuracyClass.CLASS_IIII: "IIII",
        }
        return mapping[self]

    @property
    def display_name(self) -> str:
        mapping = {
            AccuracyClass.CLASS_I: "Class I (Special Accuracy)",
            AccuracyClass.CLASS_II: "Class II (High Accuracy)",
            AccuracyClass.CLASS_III: "Class III (Medium Accuracy)",
            AccuracyClass.CLASS_IIII: "Class IIII (Ordinary Accuracy)",
        }
        return mapping[self]

    @classmethod
    def from_string(cls, val: Any) -> "AccuracyClass":
        if isinstance(val, AccuracyClass):
            return val
        clean = str(val).strip().upper().replace(" ", "_")
        aliases = {
            "I": cls.CLASS_I,
            "1": cls.CLASS_I,
            "CLASS_I": cls.CLASS_I,
            "SPECIAL": cls.CLASS_I,
            "II": cls.CLASS_II,
            "2": cls.CLASS_II,
            "CLASS_II": cls.CLASS_II,
            "HIGH": cls.CLASS_II,
            "III": cls.CLASS_III,
            "3": cls.CLASS_III,
            "CLASS_III": cls.CLASS_III,
            "MEDIUM": cls.CLASS_III,
            "IIII": cls.CLASS_IIII,
            "IV": cls.CLASS_IIII,
            "4": cls.CLASS_IIII,
            "CLASS_IIII": cls.CLASS_IIII,
            "CLASS_IV": cls.CLASS_IIII,
            "ORDINARY": cls.CLASS_IIII,
        }
        if clean in aliases:
            return aliases[clean]
        raise ValueError(f"Unknown accuracy class: {val}")

    @classmethod
    def from_value(cls, val: Any) -> "AccuracyClass":
        return cls.from_string(val)


class JobType(str, Enum):
    MODEL_APPROVAL = "MODEL_APPROVAL"               # Type Evaluation (OIML R 76-1 Annex A & B)
    INITIAL_VERIFICATION = "INITIAL_VERIFICATION"   # First statutory verification before service
    RE_VERIFICATION = "RE_VERIFICATION"             # Periodic statutory in-service verification
    POST_REPAIR = "POST_REPAIR"                     # Verification following repair/modification
    POST_RELOCATION = "POST_RELOCATION"             # Verification after relocation to new site
    RETEST = "RETEST"                               # Retest after failure rectification

    @property
    def is_in_service(self) -> bool:
        """Periodic re-verification operates under in-service MPE."""
        return self in (JobType.RE_VERIFICATION, JobType.POST_RELOCATION)


class ReceptorType(str, Enum):
    STANDARD_PLATTER = "STANDARD_PLATTER"           # Standard pan/platter <= 4 points of support
    FOUR_POINTS_OR_LESS = "FOUR_POINTS_OR_LESS"     # General receptor with <= 4 support points
    MORE_THAN_FOUR_POINTS = "MORE_THAN_FOUR_POINTS" # Large platform/weighbridge with N > 4 supports
    ROLLING_LOAD = "ROLLING_LOAD"                   # Vehicle weighbridge, rail weighbridge
    SUSPENDED_LOAD = "SUSPENDED_LOAD"               # Crane scale, hanging load receptor
    TANK_HOPPER = "TANK_HOPPER"                     # Hopper/tank scale with distributed load cells


class TestType(str, Enum):
    VISUAL_EXAMINATION = "VISUAL_EXAMINATION"
    WEIGHING_PERFORMANCE = "WEIGHING_PERFORMANCE"
    ECCENTRICITY = "ECCENTRICITY"
    REPEATABILITY = "REPEATABILITY"
    DISCRIMINATION = "DISCRIMINATION"
    TARE = "TARE"
    ZERO_SETTING_AND_TRACKING = "ZERO_SETTING_AND_TRACKING"
    CREEP_AND_ZERO_RETURN = "CREEP_AND_ZERO_RETURN"
    TEMPERATURE_EFFECT = "TEMPERATURE_EFFECT"
    VOLTAGE_VARIATION = "VOLTAGE_VARIATION"
    TILTING = "TILTING"
    SOFTWARE_EXAMINATION = "SOFTWARE_EXAMINATION"


@dataclass
class WeighingRange:
    """
    Sub-range definition for multi-interval or multiple-range instruments.
    """
    range_index: int                       # 1-indexed partial range
    max_capacity: float                    # Max_i
    min_capacity: float                    # Min_i
    e: float                               # e_i
    d: Optional[float] = None              # d_i
    unit: MassUnit = MassUnit.KG

    @property
    def n(self) -> float:
        """Number of verification scale intervals for this partial range."""
        return self.max_capacity / self.e if self.e > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "range_index": self.range_index,
            "max_capacity": self.max_capacity,
            "min_capacity": self.min_capacity,
            "e": self.e,
            "d": self.d,
            "unit": self.unit.value if isinstance(self.unit, Enum) else self.unit,
            "n": self.n,
        }


@dataclass
class InstrumentProfile:
    """
    Comprehensive metrological profile of a Non-Automatic Weighing Instrument (NAWI).
    """
    id: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    accuracy_class: AccuracyClass = AccuracyClass.CLASS_III
    max_capacity: float = 0.0              # Max
    min_capacity: float = 0.0              # Min
    e: float = 0.0                         # Verification scale interval
    d: Optional[float] = None              # Actual scale interval (d <= e)
    unit: MassUnit = MassUnit.KG

    # Architecture flags
    is_multi_interval: bool = False
    is_multi_range: bool = False
    partial_ranges: List[WeighingRange] = field(default_factory=list)

    # Tare features
    has_tare: bool = False
    max_additive_tare: Optional[float] = None
    max_subtractive_tare: Optional[float] = None

    # Zero features
    has_zero_tracking: bool = False
    zero_setting_range_percent: float = 4.0  # Typically 4% of Max for initial zero

    # Physical / Construction features
    is_electronic: bool = True
    has_software: bool = False
    software_version: Optional[str] = None
    receptor_type: ReceptorType = ReceptorType.STANDARD_PLATTER
    num_support_points: int = 4
    is_mobile: bool = False                  # Mobile/transportable (triggers tilt test)
    has_level_indicator: bool = True

    # Environmental operating limits
    temp_range_min_c: Optional[float] = None
    temp_range_max_c: Optional[float] = None

    # Regulatory tracking
    regulatory_standard: str = "OIML_R76_2006"
    approval_number: Optional[str] = None

    @property
    def n(self) -> float:
        """Total number of verification scale intervals n = Max / e."""
        return self.max_capacity / self.e if self.e > 0 else 0.0

    @property
    def actual_d(self) -> float:
        """Returns d if specified, otherwise e."""
        return self.d if self.d is not None and self.d > 0 else self.e

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial_number": self.serial_number,
            "accuracy_class": self.accuracy_class.value if isinstance(self.accuracy_class, Enum) else self.accuracy_class,
            "max_capacity": self.max_capacity,
            "min_capacity": self.min_capacity,
            "e": self.e,
            "d": self.d,
            "unit": self.unit.value if isinstance(self.unit, Enum) else self.unit,
            "n": self.n,
            "is_multi_interval": self.is_multi_interval,
            "is_multi_range": self.is_multi_range,
            "partial_ranges": [r.to_dict() for r in self.partial_ranges],
            "has_tare": self.has_tare,
            "max_additive_tare": self.max_additive_tare,
            "max_subtractive_tare": self.max_subtractive_tare,
            "has_zero_tracking": self.has_zero_tracking,
            "zero_setting_range_percent": self.zero_setting_range_percent,
            "is_electronic": self.is_electronic,
            "has_software": self.has_software,
            "software_version": self.software_version,
            "receptor_type": self.receptor_type.value if isinstance(self.receptor_type, Enum) else self.receptor_type,
            "num_support_points": self.num_support_points,
            "is_mobile": self.is_mobile,
            "has_level_indicator": self.has_level_indicator,
            "temp_range_min_c": self.temp_range_min_c,
            "temp_range_max_c": self.temp_range_max_c,
            "regulatory_standard": self.regulatory_standard,
            "approval_number": self.approval_number,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InstrumentProfile":
        ranges = []
        if "partial_ranges" in data and data["partial_ranges"]:
            for r in data["partial_ranges"]:
                unit = MassUnit(r.get("unit", "kg")) if isinstance(r.get("unit"), str) else r.get("unit", MassUnit.KG)
                ranges.append(
                    WeighingRange(
                        range_index=r["range_index"],
                        max_capacity=float(r["max_capacity"]),
                        min_capacity=float(r["min_capacity"]),
                        e=float(r["e"]),
                        d=float(r["d"]) if r.get("d") is not None else None,
                        unit=unit,
                    )
                )

        acc_class = data.get("accuracy_class", AccuracyClass.CLASS_III)
        if isinstance(acc_class, str):
            acc_class = AccuracyClass.from_string(acc_class)

        unit = data.get("unit", MassUnit.KG)
        if isinstance(unit, str):
            unit = MassUnit(unit.lower())

        receptor = data.get("receptor_type", ReceptorType.STANDARD_PLATTER)
        if isinstance(receptor, str):
            receptor = ReceptorType(receptor)

        return cls(
            id=data.get("id"),
            manufacturer=data.get("manufacturer"),
            model=data.get("model"),
            serial_number=data.get("serial_number"),
            accuracy_class=acc_class,
            max_capacity=float(data.get("max_capacity", 0.0)),
            min_capacity=float(data.get("min_capacity", 0.0)),
            e=float(data.get("e", 0.0)),
            d=float(data["d"]) if data.get("d") is not None else None,
            unit=unit,
            is_multi_interval=bool(data.get("is_multi_interval", False)),
            is_multi_range=bool(data.get("is_multi_range", False)),
            partial_ranges=ranges,
            has_tare=bool(data.get("has_tare", False)),
            max_additive_tare=float(data["max_additive_tare"]) if data.get("max_additive_tare") is not None else None,
            max_subtractive_tare=float(data["max_subtractive_tare"]) if data.get("max_subtractive_tare") is not None else None,
            has_zero_tracking=bool(data.get("has_zero_tracking", False)),
            zero_setting_range_percent=float(data.get("zero_setting_range_percent", 4.0)),
            is_electronic=bool(data.get("is_electronic", True)),
            has_software=bool(data.get("has_software", False)),
            software_version=data.get("software_version"),
            receptor_type=receptor,
            num_support_points=int(data.get("num_support_points", 4)),
            is_mobile=bool(data.get("is_mobile", False)),
            has_level_indicator=bool(data.get("has_level_indicator", True)),
            temp_range_min_c=float(data["temp_range_min_c"]) if data.get("temp_range_min_c") is not None else None,
            temp_range_max_c=float(data["temp_range_max_c"]) if data.get("temp_range_max_c") is not None else None,
            regulatory_standard=data.get("regulatory_standard", "OIML_R76_2006"),
            approval_number=data.get("approval_number"),
        )


@dataclass
class MPEValue:
    """
    Maximum Permissible Error specification for a given test load.
    """
    load: float                            # Applied test load
    load_unit: MassUnit                    # Unit of load (kg, g, etc.)
    load_in_e: float                       # Load expressed in multiples of e (m / e)
    mpe_in_e: float                        # MPE expressed in e (+/- value, e.g. 0.5, 1.0, 1.5, 2.0)
    mpe_in_units: float                    # MPE in physical units (mpe_in_e * e)
    lower_limit_error: float               # -mpe_in_units
    upper_limit_error: float               # +mpe_in_units
    verification_type: str                 # "INITIAL" or "IN_SERVICE"
    accuracy_class: AccuracyClass
    reference_clause: str
    net_load: Optional[float] = None
    tare_load: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "load": self.load,
            "load_unit": self.load_unit.value if isinstance(self.load_unit, Enum) else self.load_unit,
            "load_in_e": self.load_in_e,
            "mpe_in_e": self.mpe_in_e,
            "mpe_in_units": self.mpe_in_units,
            "lower_limit_error": self.lower_limit_error,
            "upper_limit_error": self.upper_limit_error,
            "verification_type": self.verification_type,
            "accuracy_class": self.accuracy_class.value if isinstance(self.accuracy_class, Enum) else self.accuracy_class,
            "reference_clause": self.reference_clause,
            "net_load": self.net_load,
            "tare_load": self.tare_load,
        }


@dataclass
class ApplicableTest:
    """
    Regulatory test applicability declaration for a test job.
    """
    test_type: TestType
    title: str
    applicable: bool
    justification: str
    standard_reference: str
    priority: int = 1
    mandatory: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_type": self.test_type.value if isinstance(self.test_type, Enum) else self.test_type,
            "title": self.title,
            "applicable": self.applicable,
            "justification": self.justification,
            "standard_reference": self.standard_reference,
            "priority": self.priority,
            "mandatory": self.mandatory,
        }


@dataclass
class TestPoint:
    """
    Individual test step within a test suite.
    """
    step_number: int
    test_type: TestType
    description: str
    target_load: float
    unit: MassUnit
    load_in_e: float
    direction: str = "STATIC"               # "INCREASING", "DECREASING", "STATIC"
    position: str = "CENTER"                # "CENTER", "CORNER_1", "CORNER_2", etc.
    expected_mpe: Optional[MPEValue] = None
    tare_load: Optional[float] = None
    mandatory: bool = True
    reference_clause: str = ""
    remarks: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "test_type": self.test_type.value if isinstance(self.test_type, Enum) else self.test_type,
            "description": self.description,
            "target_load": self.target_load,
            "unit": self.unit.value if isinstance(self.unit, Enum) else self.unit,
            "load_in_e": self.load_in_e,
            "direction": self.direction,
            "position": self.position,
            "expected_mpe": self.expected_mpe.to_dict() if self.expected_mpe else None,
            "tare_load": self.tare_load,
            "mandatory": self.mandatory,
            "reference_clause": self.reference_clause,
            "remarks": self.remarks,
        }


@dataclass
class TestPlan:
    """
    Complete, automatically generated test plan for a test job.
    Provides Person 4 (Test Engine) with all required test points and regulatory limits.
    """
    plan_id: str
    generated_at: str
    regulatory_standard: str
    job_type: JobType
    instrument_summary: Dict[str, Any]
    applicable_tests: List[ApplicableTest] = field(default_factory=list)
    test_suites: Dict[str, List[TestPoint]] = field(default_factory=dict)
    total_test_points: int = 0
    manual_review_items: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        suites_dict = {}
        for k, pts in self.test_suites.items():
            suites_dict[k] = [p.to_dict() for p in pts]

        return {
            "plan_id": self.plan_id,
            "generated_at": self.generated_at,
            "regulatory_standard": self.regulatory_standard,
            "job_type": self.job_type.value if isinstance(self.job_type, Enum) else self.job_type,
            "instrument_summary": self.instrument_summary,
            "applicable_tests": [t.to_dict() for t in self.applicable_tests],
            "test_suites": suites_dict,
            "total_test_points": self.total_test_points,
            "manual_review_items": self.manual_review_items,
        }
