"""
MetrIQ Regulatory Engine - Regulatory Test Applicability Engine
==============================================================

Statutory & Technical Basis:
- OIML R 76-1:2006 (Annex A: Testing Procedures, Annex B: Electronic Disturbance Tests)
- Legal Metrology (General) Rules, 2011 (Seventh Schedule, Sixth Schedule)
- Legal Metrology (Approval of Models) Rules, 2011

This engine evaluates the complete statutory and technical applicability of NAWI tests
based on comprehensive instrument characteristics (accuracy class, indication type,
electronic status, zero/tare facilities, rolling-load, printing/storage, tilting,
multi-range/multi-interval, and type-evaluation status).

Does NOT mark tests PASS/FAIL at this stage; instead determines whether a test is
APPLICABLE, NOT APPLICABLE, or requires MANUAL REVIEW, along with normative regulatory
citations and required test inputs.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .models import AccuracyClass, JobType, ReceptorType


class IndicationType(str, Enum):
    """Indication display mechanism."""
    DIGITAL = "DIGITAL"
    ANALOG = "ANALOG"
    BOTH = "BOTH"
    NON_INDICATING = "NON_INDICATING"


class InstrumentIndicationMode(str, Enum):
    """Self-indicating classification per OIML R 76-1 Clause 2.2."""
    SELF_INDICATING = "SELF_INDICATING"
    NON_SELF_INDICATING = "NON_SELF_INDICATING"
    SEMI_SELF_INDICATING = "SEMI_SELF_INDICATING"


@dataclass
class InstrumentCharacteristics:
    """
    Comprehensive characteristics of a weighing instrument for applicability evaluation.
    """
    accuracy_class: AccuracyClass = AccuracyClass.CLASS_III
    instrument_type: InstrumentIndicationMode = InstrumentIndicationMode.SELF_INDICATING
    indication_type: IndicationType = IndicationType.DIGITAL
    is_electronic: bool = True
    has_zero_setting: bool = True
    zero_setting_type: str = "SEMI_AUTOMATIC"  # NON_AUTOMATIC, SEMI_AUTOMATIC, AUTOMATIC, NONE
    has_tare: bool = True
    tare_type: str = "SUBTRACTIVE"  # SUBTRACTIVE, ADDITIVE, PRESET, NONE
    receptor_type: str = "STANDARD_PLATTER"
    has_rolling_load: bool = False
    has_printing_or_data_storage: bool = False
    is_tilting_susceptible: bool = False
    is_mobile: bool = False
    has_level_indicator: bool = True
    is_multi_range: bool = False
    is_multi_interval: bool = False
    is_type_evaluation: bool = False
    max_capacity: float = 15.0
    verification_scale_interval: float = 0.005
    software_version: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InstrumentCharacteristics":
        """Constructs and normalizes InstrumentCharacteristics from arbitrary dictionary."""
        # 1. Accuracy Class
        raw_class = data.get("accuracy_class") or data.get("class") or "III"
        try:
            acc_class = (
                raw_class if isinstance(raw_class, AccuracyClass)
                else AccuracyClass.from_string(str(raw_class))
            )
        except Exception:
            acc_class = AccuracyClass.CLASS_III

        # 2. Instrument Type (Self / Non-Self indicating)
        raw_inst_type = str(data.get("instrument_type") or "SELF_INDICATING").upper()
        if "NON_SELF" in raw_inst_type or "BEAM" in raw_inst_type or "COUNTER" in raw_inst_type:
            inst_type = InstrumentIndicationMode.NON_SELF_INDICATING
        elif "SEMI_SELF" in raw_inst_type:
            inst_type = InstrumentIndicationMode.SEMI_SELF_INDICATING
        else:
            inst_type = InstrumentIndicationMode.SELF_INDICATING

        # 3. Indication Type (Digital / Analog)
        raw_ind = data.get("digital_analog") or data.get("indication_type")
        is_digital = data.get("is_digital")
        is_analog = data.get("is_analog")

        if raw_ind:
            clean_ind = str(raw_ind).upper()
            if "DIGITAL" in clean_ind and "ANALOG" in clean_ind:
                ind_type = IndicationType.BOTH
            elif "ANALOG" in clean_ind:
                ind_type = IndicationType.ANALOG
            elif "NON" in clean_ind:
                ind_type = IndicationType.NON_INDICATING
            else:
                ind_type = IndicationType.DIGITAL
        elif is_analog and not is_digital:
            ind_type = IndicationType.ANALOG
        elif is_digital and is_analog:
            ind_type = IndicationType.BOTH
        elif inst_type == InstrumentIndicationMode.NON_SELF_INDICATING:
            ind_type = IndicationType.NON_INDICATING
        else:
            ind_type = IndicationType.DIGITAL

        # 4. Electronic status
        if data.get("electronic_status") is not None:
            is_elec = bool(data.get("electronic_status"))
        elif data.get("is_electronic") is not None:
            is_elec = bool(data.get("is_electronic"))
        else:
            is_elec = True

        # 5. Zero-setting device
        raw_zero = data.get("zero_setting_device")
        if raw_zero is not None:
            if isinstance(raw_zero, bool):
                has_zero = raw_zero
                zero_type = "SEMI_AUTOMATIC" if has_zero else "NONE"
            else:
                zero_str = str(raw_zero).upper()
                has_zero = zero_str not in ("NONE", "FALSE", "NO", "0")
                zero_type = zero_str if has_zero else "NONE"
        else:
            has_zero = bool(data.get("has_zero_setting", True))
            zero_type = "SEMI_AUTOMATIC" if has_zero else "NONE"

        # 6. Tare device
        raw_tare = data.get("tare_device")
        if raw_tare is not None:
            if isinstance(raw_tare, bool):
                has_tare = raw_tare
                tare_type = "SUBTRACTIVE" if has_tare else "NONE"
            else:
                tare_str = str(raw_tare).upper()
                has_tare = tare_str not in ("NONE", "FALSE", "NO", "0")
                tare_type = tare_str if has_tare else "NONE"
        else:
            has_tare = bool(data.get("has_tare", True))
            tare_type = "SUBTRACTIVE" if has_tare else "NONE"

        # 7. Load Receptor & Rolling load
        receptor = str(
            data.get("load_receptor")
            or data.get("receptor_type")
            or "STANDARD_PLATTER"
        ).upper()

        has_rolling = bool(
            data.get("rolling_load_capability")
            or data.get("has_rolling_load")
            or "ROLLING" in receptor
            or "WEIGHBRIDGE" in receptor
            or "CONVEYOR" in receptor
        )

        # 8. Printing & Data Storage
        has_print_storage = bool(
            data.get("printing_data_storage")
            or data.get("has_printing_or_data_storage")
            or data.get("has_printer")
            or data.get("has_data_storage")
            or data.get("has_memory")
        )

        # 9. Tilting susceptibility & mobility
        is_mobile = bool(data.get("is_mobile") or data.get("is_portable") or False)
        has_level = bool(data.get("has_level_indicator", True))
        if data.get("tilting_susceptibility") is not None:
            is_tilt_susceptible = bool(data.get("tilting_susceptibility"))
        elif data.get("is_tilting_susceptible") is not None:
            is_tilt_susceptible = bool(data.get("is_tilting_susceptible"))
        else:
            is_tilt_susceptible = is_mobile or not has_level

        # 10. Multi-range / Multi-interval
        is_mr = bool(data.get("multi_range") or data.get("is_multi_range") or data.get("multi_range_status") or False)
        is_mi = bool(data.get("multi_interval") or data.get("is_multi_interval") or data.get("multi_interval_status") or False)

        # 11. Type-evaluation status
        raw_type_eval = data.get("type_evaluation_status")
        if raw_type_eval is not None:
            is_type_eval = bool(raw_type_eval)
        elif data.get("is_type_evaluation") is not None:
            is_type_eval = bool(data.get("is_type_evaluation"))
        elif data.get("job_type") is not None:
            jt_str = str(data.get("job_type")).upper()
            is_type_eval = "MODEL_APPROVAL" in jt_str or "TYPE" in jt_str
        else:
            is_type_eval = False

        # 12. Capacity & Scale intervals
        max_cap = float(data.get("max_capacity") or data.get("Max") or 15.0)
        e_val = float(data.get("verification_scale_interval") or data.get("e") or 0.005)
        sw_ver = data.get("software_version")

        return cls(
            accuracy_class=acc_class,
            instrument_type=inst_type,
            indication_type=ind_type,
            is_electronic=is_elec,
            has_zero_setting=has_zero,
            zero_setting_type=zero_type,
            has_tare=has_tare,
            tare_type=tare_type,
            receptor_type=receptor,
            has_rolling_load=has_rolling,
            has_printing_or_data_storage=has_print_storage,
            is_tilting_susceptible=is_tilt_susceptible,
            is_mobile=is_mobile,
            has_level_indicator=has_level,
            is_multi_range=is_mr,
            is_multi_interval=is_mi,
            is_type_evaluation=is_type_eval,
            max_capacity=max_cap,
            verification_scale_interval=e_val,
            software_version=sw_ver,
        )


@dataclass
class TestEvaluationResult:
    """Individual test applicability assessment result."""
    test_id: str
    test_name: str
    source: str
    applicable: bool
    applicable_when: str
    not_applicable_when: str
    required_inputs: List[str]
    manual_review: bool
    priority: int
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "source": self.source,
            "applicable": self.applicable,
            "applicable_when": self.applicable_when,
            "not_applicable_when": self.not_applicable_when,
            "required_inputs": self.required_inputs,
            "manual_review": self.manual_review,
            "priority": self.priority,
            "reason": self.reason,
        }


@dataclass
class ApplicabilityReport:
    """Full structured report conforming to MetrIQ Regulatory Engine specification."""
    applicable_tests: List[Dict[str, Any]]
    not_applicable_tests: List[Dict[str, Any]]
    manual_review_tests: List[Dict[str, Any]]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "applicable_tests": self.applicable_tests,
            "not_applicable_tests": self.not_applicable_tests,
            "manual_review_tests": self.manual_review_tests,
            "warnings": self.warnings,
        }


class StatutoryTestDefinition:
    """Base class for structured regulatory test definitions."""

    def __init__(
        self,
        test_id: str,
        test_name: str,
        source: str,
        applicable_when: str,
        not_applicable_when: str,
        required_inputs: List[str],
        manual_review: bool,
        priority: int,
    ):
        self.test_id = test_id
        self.test_name = test_name
        self.source = source
        self.applicable_when = applicable_when
        self.not_applicable_when = not_applicable_when
        self.required_inputs = required_inputs
        self.manual_review = manual_review
        self.priority = priority

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        """
        Evaluates applicability against instrument characteristics.
        Returns (is_applicable: bool, reason: str, warning: Optional[str]).
        """
        raise NotImplementedError


# ============================================================================
# Individual Statutory Test Implementations
# ============================================================================

class TestA1Administrative(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="A.1",
            test_name="Administrative Examination",
            source="OIML R 76-1:2006 Clause A.1 / Legal Metrology (Approval of Models) Rules, 2011",
            applicable_when="Always applicable for all legal metrology verification and pattern approval jobs.",
            not_applicable_when="Never.",
            required_inputs=["manufacturer", "model_designation", "serial_number", "application_documents"],
            manual_review=True,
            priority=1,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        return True, "Mandatory statutory verification baseline across all instruments and jobs.", None


class TestA2ConstructionDocs(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="A.2",
            test_name="Comparison of Construction with Documentation",
            source="OIML R 76-1:2006 Clause A.2 / Legal Metrology (Approval of Models) Rules, 2011",
            applicable_when="Applicable during Type Evaluation / Pattern Approval to verify physical specimen against engineering drawings.",
            not_applicable_when="Routine field re-verification unless unauthorized structural modification is suspected.",
            required_inputs=["descriptive_markings", "technical_drawings", "component_schematics"],
            manual_review=True,
            priority=2,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        if c.is_type_evaluation:
            return True, "Mandatory for Type Evaluation / Model Approval to compare physical specimen against technical documentation.", None
        return False, "Routine initial or in-service verification does not repeat full technical drawing comparison.", None


class TestA3InitialExam(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="A.3",
            test_name="Initial Examination (Metrological Markings & Sealing)",
            source="OIML R 76-1:2006 Clause A.3 & Clause 7.1 / Legal Metrology (General) Rules, 2011 Seventh Schedule",
            applicable_when="Always applicable across all verification jobs.",
            not_applicable_when="Never.",
            required_inputs=["accuracy_class_marking", "Max_marking", "Min_marking", "e_marking", "sealing_provisions"],
            manual_review=True,
            priority=3,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        warning = None
        if c.is_electronic and not c.software_version:
            warning = "Electronic instrument lacks declared software version for statutory marking examination."
        return True, "Mandatory verification of legal markings (Max, Min, e, d, accuracy class) and physical sealing integrity.", warning


class TestA42ZeroSetting(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="A.4.2",
            test_name="Zero-Setting Accuracy Test",
            source="OIML R 76-1:2006 Clause A.4.2 & Clause 4.5 / Legal Metrology (General) Rules, 2011 Seventh Schedule Part I",
            applicable_when="Applicable when instrument is equipped with non-automatic, semi-automatic, or automatic zero-setting or zero-tracking devices.",
            not_applicable_when="Instrument does not possess any zero-setting device.",
            required_inputs=["verification_scale_interval_e", "zero_indication", "auxiliary_weights_0.1d"],
            manual_review=False,
            priority=4,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        if c.has_zero_setting:
            return True, f"Instrument is equipped with {c.zero_setting_type} zero-setting; requires zero error verification within +/- 0.25e.", None
        return False, "Instrument does not possess a zero-setting facility.", None


class TestA43Tare(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="A.4.3",
            test_name="Tare Accuracy & Net Weighing Test",
            source="OIML R 76-1:2006 Clause A.4.3 & Clause 4.6 / Legal Metrology (General) Rules, 2011 Seventh Schedule Part I",
            applicable_when="Applicable when instrument is equipped with a tare balancing, tare weighing, or preset tare device.",
            not_applicable_when="Instrument has no tare facility declared.",
            required_inputs=["tare_capacity", "test_tare_load", "verification_scale_interval_e", "net_test_loads"],
            manual_review=False,
            priority=5,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        if c.has_tare:
            return True, f"Instrument possesses a {c.tare_type} tare facility; requires tare balancing/setting accuracy and net load MPE verification.", None
        return False, "Instrument does not possess a tare balancing or tare weighing device.", None


class TestA44WeighingPerformance(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="A.4.4",
            test_name="Weighing Performance Test (Increasing & Decreasing Load)",
            source="OIML R 76-1:2006 Clause A.4.4 / Legal Metrology (General) Rules, 2011 Seventh Schedule Part II Table 1",
            applicable_when="Always applicable for all weighing instruments across all verification jobs.",
            not_applicable_when="Never.",
            required_inputs=["Max", "Min", "verification_scale_interval_e", "breakpoint_test_loads"],
            manual_review=False,
            priority=6,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        return True, "Core metrological test evaluating indication errors across load range against statutory MPE breakpoints.", None


class TestA47Eccentricity(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="A.4.7",
            test_name="Eccentricity (Off-Center Loading) Test",
            source="OIML R 76-1:2006 Clause A.4.7 / Legal Metrology (General) Rules, 2011 Seventh Schedule Part II Clause 3",
            applicable_when="Applicable to all instruments with a load receptor (corners on platter, multi-point supports, or tanks).",
            not_applicable_when="Suspended single-point hanging scales without platter or off-center displacement capability.",
            required_inputs=["receptor_type", "Max", "verification_scale_interval_e", "eccentric_test_load"],
            manual_review=False,
            priority=7,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        if "SUSPENDED_SINGLE_POINT" in c.receptor_type:
            return False, "Suspended single-point scale without load platform has no eccentric loading positions.", None
        return True, f"Applicable for {c.receptor_type} load receptor. Evaluates off-center loading to ensure error does not exceed MPE.", None


class TestA471RollingLoad(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="A.4.7.1",
            test_name="Rolling-Load Eccentricity Test",
            source="OIML R 76-1:2006 Clause A.4.7.4 / Legal Metrology (General) Rules, 2011 Seventh Schedule Part II",
            applicable_when="Applicable conditionally when instrument has rolling-load capability (e.g. vehicle weighbridges, rail tracks, roll conveyors).",
            not_applicable_when="Instrument has static platform or pan without rolling-load capability.",
            required_inputs=["rolling_test_load", "track_axle_positions", "Max", "verification_scale_interval_e"],
            manual_review=False,
            priority=8,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        if c.has_rolling_load:
            return True, "Instrument declares rolling-load capability (e.g. vehicle/rail/conveyor weighbridge); rolling load test is mandatory.", None
        return False, "Instrument has a static load platform without rolling-load capability.", None


class TestA48Discrimination(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="A.4.8",
            test_name="Discrimination Test",
            source="OIML R 76-1:2006 Clause A.4.8 & Clause 3.8 / Legal Metrology (General) Rules, 2011 Seventh Schedule Part I",
            applicable_when="Applicable to instruments with digital indication (1.4d test) or analog scale indication.",
            not_applicable_when="Non-indicating instruments (sensitivity test applies instead).",
            required_inputs=["actual_scale_interval_d", "indication_type", "extra_load_1.4d"],
            manual_review=False,
            priority=9,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        if c.instrument_type == InstrumentIndicationMode.NON_SELF_INDICATING:
            return False, "Discrimination test does not apply to non-self-indicating instruments (Sensitivity test A.4.9 applies instead).", None

        if c.indication_type in (IndicationType.DIGITAL, IndicationType.BOTH):
            return True, "Applicable as Digital Discrimination Test: an additional load of 1.4d placed smoothly on the loaded receptor must change the display.", None
        elif c.indication_type == IndicationType.ANALOG:
            return True, "Applicable as Analog Discrimination Test: extra load must cause a permanent displacement of the indicator of at least 0.7d.", None

        return False, "Instrument has no indicating mechanism.", None


class TestA49Sensitivity(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="A.4.9",
            test_name="Sensitivity Test for Non-Self-Indicating Instruments",
            source="OIML R 76-1:2006 Clause A.4.9 & Clause 3.7 / Legal Metrology (General) Rules, 2011 Seventh Schedule Part I",
            applicable_when="Applicable strictly to non-self-indicating or semi-self-indicating instruments (e.g. mechanical beam/counter scales).",
            not_applicable_when="Self-indicating instruments (electronic or digital NAWI).",
            required_inputs=["pointer_displacement_mm", "scale_divisions", "extra_load_at_min_and_max"],
            manual_review=False,
            priority=10,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        if c.instrument_type in (InstrumentIndicationMode.NON_SELF_INDICATING, InstrumentIndicationMode.SEMI_SELF_INDICATING):
            return True, "Instrument is non-self-indicating/semi-self-indicating; requires pointer displacement sensitivity evaluation under extra load.", None
        return False, "Sensitivity test applies strictly to non-self-indicating instruments. This instrument is self-indicating.", None


class TestA410Repeatability(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="A.4.10",
            test_name="Repeatability Test",
            source="OIML R 76-1:2006 Clause A.4.10 / Legal Metrology (General) Rules, 2011 Seventh Schedule Part II Clause 4",
            applicable_when="Always applicable across all accuracy classes and verification jobs.",
            not_applicable_when="Never.",
            required_inputs=["test_load_approx_0.5Max", "test_load_approx_Max", "number_of_weighings"],
            manual_review=False,
            priority=11,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        return True, "Mandatory repeatability evaluation (maximum difference between repeated results <= absolute MPE).", None


class TestA411ZeroReturn(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="A.4.11",
            test_name="Zero Return Test",
            source="OIML R 76-1:2006 Clause A.4.11 & Clause 3.9.4.2 / Legal Metrology (General) Rules, 2011 Seventh Schedule",
            applicable_when="Applicable during Type Evaluation and initial verification of electronic instruments.",
            not_applicable_when="Purely mechanical instruments without electronic zero recovery mechanism.",
            required_inputs=["Max", "duration_minutes", "zero_residual_indication"],
            manual_review=False,
            priority=12,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        if c.is_electronic and (c.is_type_evaluation or c.accuracy_class in (AccuracyClass.CLASS_I, AccuracyClass.CLASS_II)):
            return True, "Electronic scale requires zero-return drift evaluation after unloading from Max (drift <= 0.5e).", None
        elif not c.is_electronic:
            return False, "Zero-return drift test does not apply to purely mechanical instruments.", None
        return False, "Routine in-service verification of Class III/IIII NAWIs does not require isolated 30-minute zero-return test.", None


class TestA4111Creep(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="A.4.11.1",
            test_name="Creep Test (30-Minute Full-Load Drift)",
            source="OIML R 76-1:2006 Clause A.4.11.1 & Clause 3.9.4.1 / Legal Metrology (General) Rules, 2011 Seventh Schedule",
            applicable_when="Applicable during Type Evaluation or post-major load-cell repair on electronic instruments.",
            not_applicable_when="Routine in-service verification, or pure mechanical beam instruments.",
            required_inputs=["Max", "readings_at_0_5_15_30_min", "verification_scale_interval_e"],
            manual_review=False,
            priority=13,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        if c.is_electronic and c.is_type_evaluation:
            return True, "Mandatory for Type Evaluation of electronic instruments: evaluates continuous 30-minute load drift (<= 0.5e).", None
        elif not c.is_electronic:
            return False, "Creep test is not applicable to purely mechanical instruments.", None
        return False, "Creep test is strictly a Type Evaluation / Model Approval requirement, not applicable to field verification.", None


class TestA412StabilityEquilibrium(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="A.4.12",
            test_name="Stability of Equilibrium Test",
            source="OIML R 76-1:2006 Clause A.4.12 & Clause 4.4.2 / Legal Metrology (General) Rules, 2011 Seventh Schedule",
            applicable_when="Applicable conditionally when instrument is equipped with printing, automated data storage, or data transmission devices.",
            not_applicable_when="Instrument has no printing, data storage, or remote communication facilities.",
            required_inputs=["printer_interface", "storage_interface", "motion_trigger_attempt"],
            manual_review=True,
            priority=14,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        if c.has_printing_or_data_storage:
            return True, "Instrument declares printing/data-storage facility; requires physical verification that printing/storage is inhibited during motion.", None
        return False, "Instrument does not possess printing, automated data storage, or peripheral communication devices.", None


class TestA51Tilting(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="A.5.1",
            test_name="Tilting Susceptibility Test",
            source="OIML R 76-1:2006 Clause A.5.1 & Clause 3.9.1 / Legal Metrology (General) Rules, 2011 Seventh Schedule",
            applicable_when="Applicable conditionally if instrument is mobile, transportable, or not permanently leveled (Class II, III, IIII).",
            not_applicable_when="Class I instruments, or stationary instruments fixed to immovable foundations.",
            required_inputs=["tilt_angle_mrad", "level_indicator_type", "limiting_tilt_value"],
            manual_review=False,
            priority=15,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        if c.accuracy_class == AccuracyClass.CLASS_I:
            return False, "Class I instruments are exempt from tilting tests per OIML R 76-1 Clause 3.9.1.1 (must operate in temperature/level-controlled lab).", None

        if c.is_tilting_susceptible or c.is_mobile or not c.has_level_indicator or c.is_type_evaluation:
            reason = "Instrument is mobile/transportable or lacks self-leveling" if (c.is_mobile or not c.has_level_indicator) else "Mandatory tilt evaluation during Pattern Approval for Class II, III, IIII."
            return True, f"Applicable: {reason}. Evaluates no-load and load error under 50/1000 or limiting tilt.", None

        return False, "Stationary fixed instrument with verified level indicator is exempt from field tilt testing.", None


class TestA52WarmUp(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="A.5.2",
            test_name="Warm-Up Time Test",
            source="OIML R 76-1:2006 Clause A.5.2 & Clause 5.3.5 / Legal Metrology (General) Rules, 2011 Seventh Schedule",
            applicable_when="Applicable to electronic instruments powered by mains or rechargeable battery during type evaluation and initial commissioning.",
            not_applicable_when="Purely mechanical instruments, or non-electronic devices.",
            required_inputs=["manufacturer_warmup_minutes", "power_on_zero_indication", "post_warmup_zero_indication"],
            manual_review=False,
            priority=16,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        if c.is_electronic:
            return True, "Electronic instrument requires warm-up verification: error at power-on vs post-warmup must not exceed statutory limit.", None
        return False, "Warm-up test applies strictly to electronic instruments. This instrument is purely mechanical.", None


class TestA53TemperatureEffect(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="A.5.3",
            test_name="Temperature Effect on No-Load & Span Test",
            source="OIML R 76-1:2006 Clause A.5.3 & Clause 3.9.2 / Legal Metrology (General) Rules, 2011 Seventh Schedule",
            applicable_when="Applicable during Type Evaluation / Model Approval in environmental chamber (-10°C to +40°C).",
            not_applicable_when="Field initial or periodic verification (conducted at ambient site temperature).",
            required_inputs=["prescribed_temperature_range", "chamber_temp_steps", "thermal_equilibrium_hours"],
            manual_review=False,
            priority=17,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        if c.is_type_evaluation:
            return True, "Type Evaluation requirement: evaluates temperature coefficients and thermal span drift across -10°C to +40°C in test chamber.", None
        return False, "Climatic environmental chamber temperature test is strictly a Type Evaluation / Model Approval test.", None


class TestA54VoltageVariation(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="A.5.4",
            test_name="Voltage Variation Test",
            source="OIML R 76-1:2006 Clause A.5.4 & Clause 5.4.1 / Legal Metrology (General) Rules, 2011 Seventh Schedule",
            applicable_when="Applicable to electronic instruments connected to AC mains or battery during Type Evaluation.",
            not_applicable_when="Mechanical instruments, or routine in-service field verification.",
            required_inputs=["nominal_voltage", "voltage_upper_110pct", "voltage_lower_85pct"],
            manual_review=False,
            priority=18,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        if not c.is_electronic:
            return False, "Voltage variation test applies strictly to electronic instruments.", None
        if c.is_type_evaluation:
            return True, "Electronic instrument during Type Evaluation: verifies performance at 85% and 110% of nominal mains voltage or battery cut-off.", None
        return False, "Voltage variation test is strictly a Type Evaluation requirement, not conducted during routine field inspection.", None


class TestB1Disturbances(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="B.1",
            test_name="Electronic Disturbance Immunity Tests (ESD, Burst, Surge, Radiated RF)",
            source="OIML R 76-1:2006 Annex B / Legal Metrology (Approval of Models) Rules, 2011",
            applicable_when="Applicable to electronic instruments during Type Evaluation / Pattern Approval in EMC laboratory.",
            not_applicable_when="Mechanical non-electronic instruments, or routine field verification.",
            required_inputs=["esd_levels_6kv_8kv", "burst_transient_levels", "rf_field_3v_per_m"],
            manual_review=True,
            priority=19,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        if not c.is_electronic:
            return False, "Disturbance immunity tests apply strictly to electronic instruments.", None
        if c.is_type_evaluation:
            return True, "Electronic instrument during Type Evaluation: mandatory EMC laboratory tests for ESD, RF fields, bursts, and power dips.", None
        return False, "EMC electronic disturbance tests are strictly evaluated during Model Approval in specialized test labs.", None


class TestB2DampHeat(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="B.2",
            test_name="Damp Heat (Steady State / Cyclic) Test",
            source="OIML R 76-1:2006 Annex B.2 / Legal Metrology (Approval of Models) Rules, 2011",
            applicable_when="Applicable to electronic instruments during Type Evaluation (85% RH at 40°C for 48 hours).",
            not_applicable_when="Mechanical instruments, or routine field initial/re-verification.",
            required_inputs=["relative_humidity_85pct", "exposure_hours_48", "chamber_temp_40c"],
            manual_review=False,
            priority=20,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        if not c.is_electronic:
            return False, "Damp heat climatic test applies strictly to electronic instruments.", None
        if c.is_type_evaluation:
            return True, "Electronic instrument during Type Evaluation: mandatory 48-hour climatic damp heat exposure (85% RH at 40°C).", None
        return False, "Damp heat chamber testing is strictly a Type Evaluation / Model Approval requirement.", None


class TestB3SpanStability(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="B.3",
            test_name="Span Stability Test (28-Day Cycle)",
            source="OIML R 76-1:2006 Annex B.4 / Legal Metrology (Approval of Models) Rules, 2011",
            applicable_when="Applicable to electronic instruments during Type Evaluation / Pattern Approval.",
            not_applicable_when="Mechanical instruments, or routine field initial/re-verification.",
            required_inputs=["span_readings_28_days", "reference_mass_standard"],
            manual_review=False,
            priority=21,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        if not c.is_electronic:
            return False, "Span stability test applies strictly to electronic instruments.", None
        if c.is_type_evaluation:
            return True, "Electronic instrument during Type Evaluation: mandatory 28-day span drift tracking (drift <= 0.5e).", None
        return False, "28-day span stability test is strictly a Type Evaluation requirement.", None


class TestA6Endurance(StatutoryTestDefinition):
    def __init__(self):
        super().__init__(
            test_id="A.6",
            test_name="Endurance Test (100,000 Cycles)",
            source="OIML R 76-1:2006 Clause A.6 & Clause 3.9.4.3 / Legal Metrology (Approval of Models) Rules, 2011",
            applicable_when="Applicable during Type Evaluation / Pattern Approval for instruments with Max <= 100 kg.",
            not_applicable_when="Routine field initial/re-verification, or instruments with Max > 100 kg unless specifically required.",
            required_inputs=["endurance_cycles_100k", "pre_test_performance", "post_test_performance"],
            manual_review=False,
            priority=22,
        )

    def evaluate(self, c: InstrumentCharacteristics) -> Tuple[bool, str, Optional[str]]:
        if not c.is_type_evaluation:
            return False, "100,000-cycle endurance test is strictly a Type Evaluation requirement.", None
        if c.max_capacity <= 100.0:
            return True, f"Type Evaluation for instrument with Max <= 100 kg ({c.max_capacity} kg): mandatory 100,000 repetitive load cycles.", None
        return False, f"Endurance test applies to instruments with Max <= 100 kg. This instrument has Max = {c.max_capacity} kg.", None


# ============================================================================
# Engine Registry
# ============================================================================

ALL_STATUTORY_TESTS: List[StatutoryTestDefinition] = [
    TestA1Administrative(),
    TestA2ConstructionDocs(),
    TestA3InitialExam(),
    TestA42ZeroSetting(),
    TestA43Tare(),
    TestA44WeighingPerformance(),
    TestA47Eccentricity(),
    TestA471RollingLoad(),
    TestA48Discrimination(),
    TestA49Sensitivity(),
    TestA410Repeatability(),
    TestA411ZeroReturn(),
    TestA4111Creep(),
    TestA412StabilityEquilibrium(),
    TestA51Tilting(),
    TestA52WarmUp(),
    TestA53TemperatureEffect(),
    TestA54VoltageVariation(),
    TestB1Disturbances(),
    TestB2DampHeat(),
    TestB3SpanStability(),
    TestA6Endurance(),
]


class RegulatoryTestApplicabilityEngine:
    """
    Core Regulatory Engine for determining statutory test applicability.
    """

    @classmethod
    def evaluate(cls, spec: Union[Dict[str, Any], InstrumentCharacteristics]) -> ApplicabilityReport:
        """
        Determines applicable, not applicable, and manual review tests for an instrument.

        :param spec: Instrument specification dictionary or InstrumentCharacteristics instance.
        :return: ApplicabilityReport containing categorized test lists, citations, and warnings.
        """
        if isinstance(spec, InstrumentCharacteristics):
            characteristics = spec
        elif isinstance(spec, dict):
            characteristics = InstrumentCharacteristics.from_dict(spec)
        else:
            raise ValueError(f"Expected dict or InstrumentCharacteristics, received {type(spec).__name__}")

        applicable_list: List[Dict[str, Any]] = []
        not_applicable_list: List[Dict[str, Any]] = []
        manual_review_list: List[Dict[str, Any]] = []
        warnings_set: Set[str] = set()

        # Architecture checks & cross-feature warnings
        if characteristics.is_multi_interval:
            warnings_set.add("Multi-interval instrument: verify scale interval changeover during Weighing Performance test A.4.4.")
        if characteristics.is_multi_range:
            warnings_set.add("Multi-range instrument: each weighing range requires independent verification.")
        if characteristics.is_electronic and characteristics.has_printing_or_data_storage:
            warnings_set.add("Printing/Data-storage enabled: mandatory manual examination of printout lockout during motion (A.4.12).")
        if characteristics.has_rolling_load and "PLATTER" in characteristics.receptor_type:
            warnings_set.add("Rolling load declared on standard platter: verify structural rating for dynamic axle crossing.")

        # Evaluate each statutory test
        sorted_tests = sorted(ALL_STATUTORY_TESTS, key=lambda t: t.priority)

        for test_def in sorted_tests:
            is_app, reason, warn = test_def.evaluate(characteristics)
            if warn:
                warnings_set.add(warn)

            item = TestEvaluationResult(
                test_id=test_def.test_id,
                test_name=test_def.test_name,
                source=test_def.source,
                applicable=is_app,
                applicable_when=test_def.applicable_when,
                not_applicable_when=test_def.not_applicable_when,
                required_inputs=test_def.required_inputs,
                manual_review=test_def.manual_review,
                priority=test_def.priority,
                reason=reason,
            ).to_dict()

            if is_app:
                applicable_list.append(item)
                if test_def.manual_review:
                    manual_review_list.append(item)
            else:
                not_applicable_list.append(item)

        return ApplicabilityReport(
            applicable_tests=applicable_list,
            not_applicable_tests=not_applicable_list,
            manual_review_tests=manual_review_list,
            warnings=sorted(list(warnings_set)),
        )


def evaluate_test_applicability(spec: Union[Dict[str, Any], InstrumentCharacteristics]) -> Dict[str, Any]:
    """Convenience functional wrapper returning structured dictionary."""
    return RegulatoryTestApplicabilityEngine.evaluate(spec).to_dict()
