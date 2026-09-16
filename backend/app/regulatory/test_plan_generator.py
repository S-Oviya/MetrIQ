"""
MetrIQ Regulatory Engine - Regulatory Test Plan Generator
=========================================================

Statutory & Technical Basis:
- OIML R 76-1:2006 (Annex A: Testing Procedures, Clause 3.5: MPE, Clause 3.6: Eccentricity)
- Indian Legal Metrology (General) Rules, 2011 (Seventh Schedule, Sixth Schedule)
- Indian Legal Metrology (Approval of Models) Rules, 2011

Pipeline:
1. Instrument Specification
   ↓
2. Classification Validation (app.regulatory.classification_validator)
   ↓
3. Regulatory Applicability (app.regulatory.test_applicability_engine)
   ↓
4. Test Load Calculation (MPE, Eccentricity, Repeatability, Discrimination, Creep, Temperature)
   ↓
5. Generated Test Plan (Structured object for Person 4 Test Engine)

Ambiguous / Complex Cases:
For multi-interval instruments or instruments with critical validation issues,
a partial plan is safely generated with manual_review flagged and detailed statutory explanations.
"""

import math
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .models import AccuracyClass, JobType, MassUnit, ReceptorType
from .classification_validator import RegulatoryClassificationValidator
from .test_applicability_engine import (
    RegulatoryTestApplicabilityEngine,
    InstrumentCharacteristics,
)
from .mpe_engine import MPEEngine, VerificationType
from .profile import RegulatoryProfile, PROFILE_REGISTRY, ProfileStatus


def _round_to_e(val: float, e: float) -> float:
    """Rounds a calculated test load to the nearest valid scale interval e."""
    if e <= 0:
        return val
    steps = round(val / e)
    return round(steps * e, 6)


@dataclass
class TestLoadPoint:
    """Single discrete test point within a test procedure."""
    step_number: int
    load: float
    direction: str  # INCREASING, DECREASING, STATIC
    load_in_e: float
    mpe_in_e: float
    mpe_absolute: float
    lower_limit_error: float
    upper_limit_error: float
    tolerance_rule: str
    position: str = "CENTER"
    extra_load: Optional[float] = None
    observation_period_minutes: Optional[int] = None
    remarks: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "step_number": self.step_number,
            "load": self.load,
            "direction": self.direction,
            "load_in_e": self.load_in_e,
            "mpe_in_e": self.mpe_in_e,
            "mpe_absolute": self.mpe_absolute,
            "lower_limit_error": self.lower_limit_error,
            "upper_limit_error": self.upper_limit_error,
            "tolerance_rule": self.tolerance_rule,
            "position": self.position,
        }
        if self.extra_load is not None:
            data["extra_load"] = self.extra_load
        if self.observation_period_minutes is not None:
            data["observation_period_minutes"] = self.observation_period_minutes
        if self.remarks:
            data["remarks"] = self.remarks
        return data


@dataclass
class ExecutableTestItem:
    """Structured test procedure block consumable by Person 4 Test Engine."""
    test_id: str
    test_name: str
    applicable: bool
    manual_review: bool
    test_loads: List[Dict[str, Any]]
    acceptance_criteria: str
    required_equipment: List[str]
    source: str
    priority: int = 10
    special_conditions: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "applicable": self.applicable,
            "manual_review": self.manual_review,
            "test_loads": self.test_loads,
            "acceptance_criteria": self.acceptance_criteria,
            "required_equipment": self.required_equipment,
            "source": self.source,
            "priority": self.priority,
        }
        if self.special_conditions:
            data["special_conditions"] = self.special_conditions
        return data


@dataclass
class GeneratedTestPlan:
    """Complete statutory test plan object produced by the Regulatory Engine."""
    test_plan_id: str
    job_id: Optional[str]
    instrument_id: Optional[str]
    regulatory_profile: str
    accuracy_class: str
    max_capacity: float
    min_capacity: float
    e: float
    d: float
    n: int
    unit: str
    verification_type: str
    is_partial_plan: bool
    partial_plan_reasons: List[str]
    applicable_tests: List[str]
    not_applicable_tests: List[str]
    manual_review_items: List[Dict[str, Any]]
    calculated_test_loads: List[float]
    required_equipment: List[str]
    required_environmental_conditions: Dict[str, Any]
    mpe_reference: str
    tests: List[Dict[str, Any]]
    profile_id: str = "IN_LM_2011_ACTIVE"
    profile_status: str = "ACTIVE"
    is_authoritative: bool = True
    statutory_fee_inr: Optional[float] = None
    test_weight_substitution_limit: float = 0.50
    re_verification_period_months: int = 12
    gatc_eligible: bool = True
    gatc_remarks: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_plan_id": self.test_plan_id,
            "job_id": self.job_id,
            "instrument_id": self.instrument_id,
            "regulatory_profile": self.regulatory_profile,
            "profile_id": self.profile_id,
            "profile_status": self.profile_status,
            "is_authoritative": self.is_authoritative,
            "statutory_fee_inr": self.statutory_fee_inr,
            "test_weight_substitution_limit": self.test_weight_substitution_limit,
            "re_verification_period_months": self.re_verification_period_months,
            "gatc_eligible": self.gatc_eligible,
            "gatc_remarks": self.gatc_remarks,
            "accuracy_class": self.accuracy_class,
            "max_capacity": self.max_capacity,
            "min_capacity": self.min_capacity,
            "e": self.e,
            "d": self.d,
            "n": self.n,
            "unit": self.unit,
            "verification_type": self.verification_type,
            "is_partial_plan": self.is_partial_plan,
            "partial_plan_reasons": self.partial_plan_reasons,
            "applicable_tests": self.applicable_tests,
            "not_applicable_tests": self.not_applicable_tests,
            "manual_review_items": self.manual_review_items,
            "calculated_test_loads": self.calculated_test_loads,
            "required_equipment": self.required_equipment,
            "required_environmental_conditions": self.required_environmental_conditions,
            "mpe_reference": self.mpe_reference,
            "tests": self.tests,
            "generated_at": self.generated_at,
        }


class RegulatoryTestPlanGenerator:
    """
    Automatic Regulatory Test Plan Generator for MetrIQ.
    Executes the complete 5-stage regulatory pipeline.
    """

    DEFAULT_PROFILE = "OIML R 76-1:2006 / Indian Legal Metrology (General) Rules, 2011"

    @classmethod
    def generate(cls, spec: Dict[str, Any]) -> GeneratedTestPlan:
        """
        Executes pipeline:
        Specification -> Classification Validation -> Applicability -> Load Calculation -> Test Plan
        """
        # Unwrap nested instrument dict if passed
        if "instrument" in spec and isinstance(spec["instrument"], dict):
            flat_spec = dict(spec["instrument"])
            for k, v in spec.items():
                if k != "instrument" and k not in flat_spec:
                    flat_spec[k] = v
            spec = flat_spec

        # Extract base identifiers
        job_id = spec.get("job_id")
        instrument_id = spec.get("instrument_id") or spec.get("serial_number")
        test_plan_id = f"PLAN-{uuid.uuid4().hex[:8].upper()}"

        # -------------------------------------------------------------
        # Step 0: Resolve Data-Driven Regulatory Profile
        # -------------------------------------------------------------
        prof: Optional[RegulatoryProfile] = None
        if "profile" in spec and hasattr(spec["profile"], "profile_id"):
            prof = spec["profile"]
        elif "profile_id" in spec and spec["profile_id"]:
            prof = PROFILE_REGISTRY.get_profile(str(spec["profile_id"]))
        elif "regulatory_profile" in spec and isinstance(spec["regulatory_profile"], str):
            prof = PROFILE_REGISTRY.get_profile(spec["regulatory_profile"])

        if prof is None:
            prof = PROFILE_REGISTRY.get_default_profile()

        reg_profile = (
            spec.get("regulatory_profile")
            or (cls.DEFAULT_PROFILE if (prof and prof.profile_id == "IN_LM_2011_ACTIVE") else (prof.regulation_name if prof else cls.DEFAULT_PROFILE))
        )
        prof_id = prof.profile_id if prof else "IN_LM_2011_ACTIVE"
        prof_status = prof.verification_status.value if prof else "ACTIVE"
        is_authoritative = prof.is_authoritative if prof else True

        # -------------------------------------------------------------
        # Step 1: Classification Validation
        # -------------------------------------------------------------
        val_result = RegulatoryClassificationValidator.validate(spec)

        # -------------------------------------------------------------
        # Step 2: Regulatory Applicability
        # -------------------------------------------------------------
        char = InstrumentCharacteristics.from_dict(spec)
        app_report = RegulatoryTestApplicabilityEngine.evaluate(char)

        # Verification type
        raw_v_type = spec.get("verification_type") or spec.get("job_type", "INITIAL")
        v_type = VerificationType.from_value(raw_v_type)

        # Accuracy class and scale intervals
        acc_class = char.accuracy_class
        max_cap = char.max_capacity
        min_cap = float(spec.get("Min") or spec.get("min_capacity") or (20.0 * char.verification_scale_interval))
        e_val = char.verification_scale_interval
        d_val = float(spec.get("d") or spec.get("actual_scale_interval") or e_val)
        n_val = int(round(max_cap / e_val)) if e_val > 0 else 0
        unit_str = str(spec.get("unit") or "kg").lower()

        # Dynamic profile parameters
        fee_inr = prof.get_fee("VERIFICATION", max_cap) if prof else None
        sub_limit = prof.get_max_substitution_ratio() if prof else 0.50
        inst_type_name = str(spec.get("instrument_type") or "COMMERCIAL_NAWI")
        rev_period = prof.get_re_verification_period_months(inst_type_name) if prof else 12
        gatc_ok, gatc_msg = prof.is_gatc_eligible(acc_class, max_cap) if prof else (True, "Eligible")

        # Check for complex / ambiguous multi-interval, profile review, or validation errors
        is_partial = False
        partial_reasons: List[str] = []

        if char.is_multi_interval:
            is_partial = True
            partial_reasons.append(
                "Multi-interval scale has discontinuous scale intervals (e1, e2, ...) and automatic changeover points. "
                "Requires on-site manual verification of changeover thresholds on increasing load and tare deduction across "
                "range boundaries per OIML R 76-1 Clause 3.3. A partial safe test plan is generated."
            )

        if not val_result.valid:
            is_partial = True
            err_msgs = "; ".join(e.message for e in val_result.errors)
            partial_reasons.append(f"Classification validation failed with regulatory errors: {err_msgs}")

        if prof and prof.verification_status == ProfileStatus.MANUAL_REVIEW:
            is_partial = True
            partial_reasons.append(
                f"Regulatory profile '{prof.profile_id}' is marked {prof.verification_status.value} / UNVERIFIED. "
                f"Secondary-source claims require explicit legal metrology officer confirmation prior to stamping."
            )

        # -------------------------------------------------------------
        # Step 3: Test Load Calculations
        # -------------------------------------------------------------
        executable_tests: List[ExecutableTestItem] = []
        all_test_loads_set: Set[float] = set()

        # Equipment determination based on Accuracy Class
        standard_weights_class = cls._resolve_standard_weights_class(acc_class)
        required_equipment_list = [
            f"Class {standard_weights_class} Reference Standard Weights (Maximum permissible error <= 1/3 instrument MPE)",
            f"Calibrated auxiliary fractional weights ({0.1 * d_val:.4g} {unit_str} for turning-point determination)",
            "Precision digital thermo-hygrometer for ambient temperature and relative humidity logging",
            "Stop watch / calibrated digital timer (+/- 0.1s resolution)",
        ]

        # Environmental conditions
        env_conditions = cls._resolve_environmental_conditions(acc_class, char.is_type_evaluation)

        # Process each applicable test
        applicable_test_ids = [t["test_id"] for t in app_report.applicable_tests]
        not_applicable_test_ids = [t["test_id"] for t in app_report.not_applicable_tests]

        for app_test_dict in app_report.applicable_tests:
            tid = app_test_dict["test_id"]
            tname = app_test_dict["test_name"]
            source = app_test_dict["source"]
            is_manual = app_test_dict["manual_review"]
            priority = app_test_dict["priority"]

            # Dispatch to specific test load calculations
            if tid == "A.4.4":
                item = cls._calculate_weighing_performance(
                    acc_class=acc_class,
                    max_cap=max_cap,
                    min_cap=min_cap,
                    e_val=e_val,
                    unit_str=unit_str,
                    v_type=v_type,
                    source=source,
                    weights_class=standard_weights_class,
                    is_multi_interval=char.is_multi_interval,
                    profile=prof,
                )
                for pt in item.test_loads:
                    all_test_loads_set.add(pt["load"])
                executable_tests.append(item)

            elif tid == "A.4.7":
                item = cls._calculate_eccentricity(
                    acc_class=acc_class,
                    max_cap=max_cap,
                    e_val=e_val,
                    unit_str=unit_str,
                    v_type=v_type,
                    source=source,
                    receptor_type=char.receptor_type,
                    weights_class=standard_weights_class,
                    additive_tare=float(spec.get("additive_tare", 0.0)),
                    profile=prof,
                )
                for pt in item.test_loads:
                    all_test_loads_set.add(pt["load"])
                executable_tests.append(item)

            elif tid == "A.4.10":
                item = cls._calculate_repeatability(
                    acc_class=acc_class,
                    max_cap=max_cap,
                    e_val=e_val,
                    unit_str=unit_str,
                    v_type=v_type,
                    source=source,
                    is_type_evaluation=char.is_type_evaluation,
                    weights_class=standard_weights_class,
                    profile=prof,
                )
                for pt in item.test_loads:
                    all_test_loads_set.add(pt["load"])
                executable_tests.append(item)

            elif tid == "A.4.8":
                item = cls._calculate_digital_discrimination(
                    acc_class=acc_class,
                    max_cap=max_cap,
                    min_cap=min_cap,
                    e_val=e_val,
                    d_val=d_val,
                    unit_str=unit_str,
                    v_type=v_type,
                    source=source,
                    weights_class=standard_weights_class,
                    profile=prof,
                )
                for pt in item.test_loads:
                    all_test_loads_set.add(pt["load"])
                executable_tests.append(item)

            elif tid == "A.4.3":
                item = cls._calculate_tare_accuracy(
                    acc_class=acc_class,
                    max_cap=max_cap,
                    min_cap=min_cap,
                    e_val=e_val,
                    unit_str=unit_str,
                    v_type=v_type,
                    source=source,
                    weights_class=standard_weights_class,
                    max_tare=float(spec.get("max_subtractive_tare") or (0.33 * max_cap)),
                    profile=prof,
                )
                for pt in item.test_loads:
                    all_test_loads_set.add(pt["load"])
                executable_tests.append(item)

            elif tid == "A.4.11.1":
                item = cls._calculate_creep(
                    acc_class=acc_class,
                    max_cap=max_cap,
                    e_val=e_val,
                    unit_str=unit_str,
                    v_type=v_type,
                    source=source,
                    weights_class=standard_weights_class,
                    profile=prof,
                )
                for pt in item.test_loads:
                    all_test_loads_set.add(pt["load"])
                executable_tests.append(item)

            elif tid == "A.5.3":
                item = cls._calculate_temperature_effect(
                    acc_class=acc_class,
                    max_cap=max_cap,
                    e_val=e_val,
                    unit_str=unit_str,
                    source=source,
                )
                executable_tests.append(item)

            else:
                # Other statutory tests (A.1, A.2, A.3, A.4.2, A.4.12, A.5.1, A.5.2, A.5.4, B.1, B.2, B.3, A.6)
                item = ExecutableTestItem(
                    test_id=tid,
                    test_name=tname,
                    applicable=True,
                    manual_review=is_manual,
                    test_loads=[],
                    acceptance_criteria=app_test_dict["reason"],
                    required_equipment=app_test_dict["required_inputs"],
                    source=source,
                    priority=priority,
                )
                executable_tests.append(item)

        # Manual review items list
        manual_review_items: List[Dict[str, Any]] = []
        for t in app_report.manual_review_tests:
            manual_review_items.append({
                "test_id": t["test_id"],
                "test_name": t["test_name"],
                "source": t["source"],
                "action_required": f"Inspector physical review: {t['applicable_when']}",
            })

        if is_partial:
            for reason in partial_reasons:
                manual_review_items.append({
                    "test_id": "PARTIAL_PLAN_ALERT",
                    "test_name": "Complex/Multi-Interval Partial Plan Verification",
                    "source": "OIML R 76-1:2006 Clause 3.3",
                    "action_required": reason,
                })

        if prof and prof.verification_status == ProfileStatus.MANUAL_REVIEW:
            manual_review_items.append({
                "test_id": "PROFILE_MANUAL_REVIEW_REQUIRED",
                "test_name": f"Regulatory Profile Manual Review ({prof.profile_id})",
                "source": prof.source,
                "action_required": (
                    f"Profile '{prof.profile_id}' is in {prof.verification_status.value} status. "
                    f"{prof.notes} Verification by Legal Metrology Officer is mandatory before stamping."
                ),
            })

        # Sort executable tests by priority
        executable_tests.sort(key=lambda t: t.priority)

        # Build final plan
        return GeneratedTestPlan(
            test_plan_id=test_plan_id,
            job_id=job_id,
            instrument_id=instrument_id,
            regulatory_profile=reg_profile,
            profile_id=prof_id,
            profile_status=prof_status,
            is_authoritative=is_authoritative,
            statutory_fee_inr=fee_inr,
            test_weight_substitution_limit=sub_limit,
            re_verification_period_months=rev_period,
            gatc_eligible=gatc_ok,
            gatc_remarks=gatc_msg,
            accuracy_class=acc_class.roman,
            max_capacity=max_cap,
            min_capacity=min_cap,
            e=e_val,
            d=d_val,
            n=n_val,
            unit=unit_str,
            verification_type=v_type.value,
            is_partial_plan=is_partial,
            partial_plan_reasons=partial_reasons,
            applicable_tests=applicable_test_ids,
            not_applicable_tests=not_applicable_test_ids,
            manual_review_items=manual_review_items,
            calculated_test_loads=sorted(list(all_test_loads_set)),
            required_equipment=required_equipment_list,
            required_environmental_conditions=env_conditions,
            mpe_reference=f"OIML R 76-1:2006 Table 6 / Seventh Schedule Table 2 ({v_type.value} verification)",
            tests=[t.to_dict() for t in executable_tests],
        )

    # =========================================================================
    # Test-Specific Load Calculations
    # =========================================================================

    @classmethod
    def _calculate_weighing_performance(
        cls,
        acc_class: AccuracyClass,
        max_cap: float,
        min_cap: float,
        e_val: float,
        unit_str: str,
        v_type: VerificationType,
        source: str,
        weights_class: str,
        is_multi_interval: bool = False,
        profile: Optional[Any] = None,
    ) -> ExecutableTestItem:
        """Generates load points based on capacity and MPE transition bands."""
        loads_set: Set[float] = {0.0}

        if min_cap > 0:
            loads_set.add(round(min_cap, 6))

        # Add MPE transition breakpoints for this class (or from custom bands in profile)
        breakpoints_in_e: List[float] = []
        if profile is not None and hasattr(profile, "get_mpe_bands_for_class"):
            custom_bands = profile.get_mpe_bands_for_class(acc_class)
            if custom_bands:
                breakpoints_in_e = [float(b.max_load_e) for b in custom_bands[:-1]]

        if not breakpoints_in_e:
            if acc_class == AccuracyClass.CLASS_I:
                breakpoints_in_e = [50000.0, 200000.0]
            elif acc_class == AccuracyClass.CLASS_II:
                breakpoints_in_e = [5000.0, 20000.0]
            elif acc_class == AccuracyClass.CLASS_III:
                breakpoints_in_e = [500.0, 2000.0]
            elif acc_class == AccuracyClass.CLASS_IIII:
                breakpoints_in_e = [50.0, 200.0]

        for bp_e in breakpoints_in_e:
            bp_val = round(bp_e * e_val, 6)
            if min_cap < bp_val < max_cap:
                loads_set.add(bp_val)

        # 50% Max point
        half_max = _round_to_e(max_cap * 0.5, e_val)
        if min_cap < half_max < max_cap:
            loads_set.add(half_max)

        # Max capacity
        loads_set.add(round(max_cap, 6))

        # Ensure at least 5 discrete load steps
        sorted_inc = sorted(list(loads_set))
        if len(sorted_inc) < 5:
            step = (max_cap - min_cap) / 4.0
            for i in range(1, 4):
                loads_set.add(_round_to_e(min_cap + i * step, e_val))
            sorted_inc = sorted(list(loads_set))

        # Build increasing and decreasing load schedule
        test_points: List[Dict[str, Any]] = []
        step_no = 1

        # Increasing
        for l_val in sorted_inc:
            res = MPEEngine.calculate(acc_class, l_val, e_val, verification_type=v_type, profile=profile)
            test_points.append(
                TestLoadPoint(
                    step_number=step_no,
                    load=l_val,
                    direction="INCREASING",
                    load_in_e=res.load_in_e,
                    mpe_in_e=res.mpe_in_e,
                    mpe_absolute=res.mpe_absolute,
                    lower_limit_error=-res.mpe_absolute,
                    upper_limit_error=res.mpe_absolute,
                    tolerance_rule=res.applicable_rule,
                    position="CENTER",
                    remarks="Zero load check" if l_val == 0 else f"Apply {l_val} {unit_str} increasing progressively.",
                ).to_dict()
            )
            step_no += 1

        # Decreasing (descending order, excluding duplicate Max)
        sorted_dec = list(reversed(sorted_inc[:-1]))
        for l_val in sorted_dec:
            res = MPEEngine.calculate(acc_class, l_val, e_val, verification_type=v_type, profile=profile)
            test_points.append(
                TestLoadPoint(
                    step_number=step_no,
                    load=l_val,
                    direction="DECREASING",
                    load_in_e=res.load_in_e,
                    mpe_in_e=res.mpe_in_e,
                    mpe_absolute=res.mpe_absolute,
                    lower_limit_error=-res.mpe_absolute,
                    upper_limit_error=res.mpe_absolute,
                    tolerance_rule=res.applicable_rule,
                    position="CENTER",
                    remarks="Zero return check" if l_val == 0 else f"Remove test load to {l_val} {unit_str} progressively.",
                ).to_dict()
            )
            step_no += 1

        return ExecutableTestItem(
            test_id="A.4.4",
            test_name="Weighing Performance Test",
            applicable=True,
            manual_review=is_multi_interval,
            test_loads=test_points,
            acceptance_criteria=(
                f"Indication error at each load point must not exceed the statutory MPE (+/- {v_type.value} MPE). "
                f"On returning to zero, residual zero error must be <= 0.5e."
            ),
            required_equipment=[f"Class {weights_class} standard weights"],
            source=source,
            priority=6,
        )

    @classmethod
    def _calculate_eccentricity(
        cls,
        acc_class: AccuracyClass,
        max_cap: float,
        e_val: float,
        unit_str: str,
        v_type: VerificationType,
        source: str,
        receptor_type: str,
        weights_class: str,
        additive_tare: float = 0.0,
        profile: Optional[Any] = None,
    ) -> ExecutableTestItem:
        """
        Eccentricity test load = (Max + additive_tare) / 3 per OIML R 76-1 Clause 3.6.2.4.
        """
        raw_load = (max_cap + additive_tare) / 3.0
        ecc_load = _round_to_e(raw_load, e_val)

        res = MPEEngine.calculate(acc_class, ecc_load, e_val, verification_type=v_type, profile=profile)

        positions = [
            ("CENTER", "Center of load receptor"),
            ("CORNER_1_FRONT_LEFT", "Front-Left Corner (1/4 quadrant)"),
            ("CORNER_2_BACK_LEFT", "Back-Left Corner (1/4 quadrant)"),
            ("CORNER_3_BACK_RIGHT", "Back-Right Corner (1/4 quadrant)"),
            ("CORNER_4_FRONT_RIGHT", "Front-Right Corner (1/4 quadrant)"),
        ]

        test_points: List[Dict[str, Any]] = []
        for idx, (pos_id, pos_name) in enumerate(positions, start=1):
            test_points.append(
                TestLoadPoint(
                    step_number=idx,
                    load=ecc_load,
                    direction="STATIC",
                    load_in_e=res.load_in_e,
                    mpe_in_e=res.mpe_in_e,
                    mpe_absolute=res.mpe_absolute,
                    lower_limit_error=-res.mpe_absolute,
                    upper_limit_error=res.mpe_absolute,
                    tolerance_rule=f"Eccentric load MPE: +/-{res.mpe_in_e}e ({res.applicable_rule})",
                    position=pos_id,
                    remarks=f"Place test load {ecc_load} {unit_str} in {pos_name}. Zero instrument between positions if necessary.",
                ).to_dict()
            )

        return ExecutableTestItem(
            test_id="A.4.7",
            test_name="Eccentricity (Off-Center Loading) Test",
            applicable=True,
            manual_review=False,
            test_loads=test_points,
            acceptance_criteria=(
                f"Indication error at each eccentric position must not exceed statutory MPE "
                f"(+/- {res.mpe_absolute} {unit_str} / +/- {res.mpe_in_e}e) for test load = (Max + AdditiveTare) / 3 = {ecc_load} {unit_str}."
            ),
            required_equipment=[f"Class {weights_class} test weights totalling {ecc_load} {unit_str}"],
            source=source,
            priority=7,
        )

    @classmethod
    def _calculate_repeatability(
        cls,
        acc_class: AccuracyClass,
        max_cap: float,
        e_val: float,
        unit_str: str,
        v_type: VerificationType,
        source: str,
        is_type_evaluation: bool,
        weights_class: str,
        profile: Optional[Any] = None,
    ) -> ExecutableTestItem:
        """Repeatability: 2 load levels (~50% Max and 100% Max) with 3 or 10 weighings."""
        load_half = _round_to_e(max_cap * 0.5, e_val)
        load_max = _round_to_e(max_cap, e_val)

        cycles = 10 if is_type_evaluation else 3

        res_half = MPEEngine.calculate(acc_class, load_half, e_val, verification_type=v_type, profile=profile)
        res_max = MPEEngine.calculate(acc_class, load_max, e_val, verification_type=v_type, profile=profile)

        test_points: List[Dict[str, Any]] = []
        step_no = 1

        for lvl_name, l_val, mpe_res in [("Level 1 (50% Max)", load_half, res_half), ("Level 2 (100% Max)", load_max, res_max)]:
            for c in range(1, cycles + 1):
                test_points.append(
                    TestLoadPoint(
                        step_number=step_no,
                        load=l_val,
                        direction="STATIC",
                        load_in_e=mpe_res.load_in_e,
                        mpe_in_e=mpe_res.mpe_in_e,
                        mpe_absolute=mpe_res.mpe_absolute,
                        lower_limit_error=-mpe_res.mpe_absolute,
                        upper_limit_error=mpe_res.mpe_absolute,
                        tolerance_rule=f"Repeatability spread <= |MPE| ({mpe_res.mpe_absolute} {unit_str})",
                        position="CENTER",
                        remarks=f"{lvl_name}: Run #{c} of {cycles}. Reset zero before loading.",
                    ).to_dict()
                )
                step_no += 1

        return ExecutableTestItem(
            test_id="A.4.10",
            test_name="Repeatability Test",
            applicable=True,
            manual_review=False,
            test_loads=test_points,
            acceptance_criteria=(
                f"The difference between the maximum and minimum results obtained in {cycles} repeated weighings "
                f"of the same load must not exceed the absolute MPE for that load (Spread <= {res_half.mpe_absolute} {unit_str} "
                f"at 50% Max, and Spread <= {res_max.mpe_absolute} {unit_str} at Max)."
            ),
            required_equipment=[f"Class {weights_class} standard weights"],
            source=source,
            priority=11,
        )

    @classmethod
    def _calculate_digital_discrimination(
        cls,
        acc_class: AccuracyClass,
        max_cap: float,
        min_cap: float,
        e_val: float,
        d_val: float,
        unit_str: str,
        v_type: VerificationType,
        source: str,
        weights_class: str,
        profile: Optional[Any] = None,
    ) -> ExecutableTestItem:
        """Digital Discrimination: base load + additional load of 1.4d per OIML R 76-1 Clause A.4.8."""
        extra_load = round(1.4 * d_val, 6)

        base_loads = [
            ("Min Capacity", min_cap),
            ("50% Max Capacity", _round_to_e(max_cap * 0.5, e_val)),
            ("Max Capacity", max_cap),
        ]

        test_points: List[Dict[str, Any]] = []
        for idx, (name, b_load) in enumerate(base_loads, start=1):
            res = MPEEngine.calculate(acc_class, b_load, e_val, verification_type=v_type, profile=profile)
            test_points.append(
                TestLoadPoint(
                    step_number=idx,
                    load=b_load,
                    direction="STATIC",
                    load_in_e=res.load_in_e,
                    mpe_in_e=res.mpe_in_e,
                    mpe_absolute=res.mpe_absolute,
                    lower_limit_error=-res.mpe_absolute,
                    upper_limit_error=res.mpe_absolute,
                    tolerance_rule="Display must change unequivocally by +1d (+ {d_val} {unit_str})",
                    position="CENTER",
                    extra_load=extra_load,
                    remarks=f"Apply base load {b_load} {unit_str}. Gently add +{extra_load} {unit_str} (1.4d). Indication must step up by +{d_val} {unit_str}.",
                ).to_dict()
            )

        return ExecutableTestItem(
            test_id="A.4.8",
            test_name="Digital Discrimination Test",
            applicable=True,
            manual_review=False,
            test_loads=test_points,
            acceptance_criteria=(
                f"An extra load of 1.4d ({extra_load} {unit_str}) placed smoothly on the load receptor "
                f"must unequivocally change the display reading from I to I + d (an increase of +{d_val} {unit_str})."
            ),
            required_equipment=[
                f"Class {weights_class} base standard weights",
                f"Calibrated fractional 1.4d test weight ({extra_load} {unit_str})",
            ],
            source=source,
            priority=9,
        )

    @classmethod
    def _calculate_tare_accuracy(
        cls,
        acc_class: AccuracyClass,
        max_cap: float,
        min_cap: float,
        e_val: float,
        unit_str: str,
        v_type: VerificationType,
        source: str,
        weights_class: str,
        max_tare: float,
        profile: Optional[Any] = None,
    ) -> ExecutableTestItem:
        """Tare device test: Net load performance under preset/subtractive tare."""
        t_load = _round_to_e(max_tare, e_val)
        max_net = max_cap - t_load

        net_loads = [
            ("Min Net", min_cap),
            ("50% Max Net", _round_to_e(max_net * 0.5, e_val)),
            ("Max Net", _round_to_e(max_net, e_val)),
        ]

        test_points: List[Dict[str, Any]] = []
        for idx, (n_name, n_load) in enumerate(net_loads, start=1):
            res = MPEEngine.calculate(acc_class, n_load, e_val, verification_type=v_type, profile=profile)
            test_points.append(
                TestLoadPoint(
                    step_number=idx,
                    load=round(t_load + n_load, 6),
                    direction="STATIC",
                    load_in_e=res.load_in_e,
                    mpe_in_e=res.mpe_in_e,
                    mpe_absolute=res.mpe_absolute,
                    lower_limit_error=-res.mpe_absolute,
                    upper_limit_error=res.mpe_absolute,
                    tolerance_rule=f"MPE on Net Load {n_load} {unit_str}: +/-{res.mpe_absolute} {unit_str}",
                    position="CENTER",
                    remarks=f"Set tare={t_load} {unit_str}. Apply net load={n_load} {unit_str}. Gross={t_load + n_load} {unit_str}.",
                ).to_dict()
            )

        return ExecutableTestItem(
            test_id="A.4.3",
            test_name="Tare Accuracy & Net Weighing Test",
            applicable=True,
            manual_review=False,
            test_loads=test_points,
            acceptance_criteria=(
                f"Under Tare = {t_load} {unit_str}, the net weighing indication error at each net load "
                f"must not exceed the MPE calculated for the net load (OIML R 76-1 Clause 3.5.3.3)."
            ),
            required_equipment=[f"Class {weights_class} tare and net test weights"],
            source=source,
            priority=5,
        )

    @classmethod
    def _calculate_creep(
        cls,
        acc_class: AccuracyClass,
        max_cap: float,
        e_val: float,
        unit_str: str,
        v_type: VerificationType,
        source: str,
        weights_class: str,
        profile: Optional[Any] = None,
    ) -> ExecutableTestItem:
        """Creep test at Max with 0, 5, 15, 30 min readings and 15-30 min early termination rule."""
        res = MPEEngine.calculate(acc_class, max_cap, e_val, verification_type=v_type, profile=profile)

        observation_times = [0, 5, 15, 30]
        test_points: List[Dict[str, Any]] = []

        for idx, t_min in enumerate(observation_times, start=1):
            test_points.append(
                TestLoadPoint(
                    step_number=idx,
                    load=max_cap,
                    direction="STATIC",
                    load_in_e=res.load_in_e,
                    mpe_in_e=res.mpe_in_e,
                    mpe_absolute=res.mpe_absolute,
                    lower_limit_error=-res.mpe_absolute,
                    upper_limit_error=res.mpe_absolute,
                    tolerance_rule="Total drift over 30 min <= 0.5e (0.2e between 15m and 30m)",
                    position="CENTER",
                    observation_period_minutes=t_min,
                    remarks=f"Reading at T = {t_min} minutes under continuous Max load ({max_cap} {unit_str}).",
                ).to_dict()
            )

        return ExecutableTestItem(
            test_id="A.4.11.1",
            test_name="Creep Test (30-Minute Full-Load Drift)",
            applicable=True,
            manual_review=False,
            test_loads=test_points,
            acceptance_criteria=(
                f"1. Total indication drift over 30 minutes must not exceed 0.5e ({0.5 * e_val} {unit_str}).\n"
                f"2. Early Termination Rule: If the difference between the 15-minute and 30-minute readings is <= 0.2e "
                f"({0.2 * e_val} {unit_str}), the creep test is concluded compliant per OIML R 76-1 Clause 3.9.4.1."
            ),
            required_equipment=[
                f"Class {weights_class} standard weights totaling {max_cap} {unit_str}",
                "Precision digital stopwatch (+/- 0.1s)",
            ],
            source=source,
            priority=13,
            special_conditions={
                "early_termination_delta_e": 0.2,
                "early_termination_delta_absolute": round(0.2 * e_val, 6),
                "total_max_drift_e": 0.5,
                "total_max_drift_absolute": round(0.5 * e_val, 6),
            },
        )

    @classmethod
    def _calculate_temperature_effect(
        cls,
        acc_class: AccuracyClass,
        max_cap: float,
        e_val: float,
        unit_str: str,
        source: str,
    ) -> ExecutableTestItem:
        """Temperature effect requirements in climatic chamber (-10°C to +40°C)."""
        temp_steps = [20, 40, -10, 20]
        return ExecutableTestItem(
            test_id="A.5.3",
            test_name="Temperature Effect on No-Load & Span Test",
            applicable=True,
            manual_review=False,
            test_loads=[],
            acceptance_criteria=(
                "1. Indication errors at all temperatures (-10°C, +20°C, +40°C) must not exceed initial MPE.\n"
                "2. Zero drift: Zero indication drift per 5°C must be <= 1e for Class II, III, IIII (or <= 0.5e for Class I).\n"
                "3. Rate of temperature change must not exceed 5°C/h."
            ),
            required_equipment=[
                "Climatic Environmental Test Chamber (-20°C to +60°C)",
                "Standard Reference Weights",
                "Calibrated Pt100/Thermocouple Temperature Sensors",
            ],
            source=source,
            priority=17,
            special_conditions={
                "chamber_temperature_steps_celsius": temp_steps,
                "thermal_soak_hours_per_step": 2,
                "max_temp_change_rate_c_per_hour": 5.0,
            },
        )

    # =========================================================================
    # Helpers
    # =========================================================================

    @classmethod
    def _resolve_standard_weights_class(cls, acc_class: AccuracyClass) -> str:
        """Determines required OIML R 111 weight accuracy class so weight error <= 1/3 MPE."""
        if acc_class == AccuracyClass.CLASS_I:
            return "E2 (or E1)"
        elif acc_class == AccuracyClass.CLASS_II:
            return "F1 (or F2)"
        elif acc_class == AccuracyClass.CLASS_III:
            return "M1 (or M2)"
        else:
            return "M2 (or M3)"

    @classmethod
    def _resolve_environmental_conditions(cls, acc_class: AccuracyClass, is_type_evaluation: bool) -> Dict[str, Any]:
        """Resolves required laboratory ambient test conditions."""
        if acc_class == AccuracyClass.CLASS_I:
            temp_range = "+18°C to +23°C (strictly controlled laboratory environment)"
            stability = "Max 1°C drift per hour"
        elif acc_class == AccuracyClass.CLASS_II:
            temp_range = "+15°C to +25°C"
            stability = "Max 2°C drift per hour"
        else:
            temp_range = "+10°C to +30°C for routine verification; -10°C to +40°C for model approval"
            stability = "Max 5°C drift per hour"

        return {
            "prescribed_temperature_range": temp_range,
            "max_temperature_rate_of_change": "5°C per hour (1°C/h for Class I)",
            "relative_humidity_range": "20% to 85% RH (non-condensing)",
            "barometric_pressure_range": "86 kPa to 106 kPa (ambient atmospheric)",
            "air_current_restrictions": "Shield from direct drafts, air conditioning vents, and heat radiators",
            "vibration_restrictions": "Isolated from perceptible mechanical shocks and external building vibrations",
            "leveling_requirement": "Instrument leveled to center of level bubble on a rigid, unyielding table",
        }


def generate_regulatory_test_plan(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience functional wrapper returning structured dictionary."""
    return RegulatoryTestPlanGenerator.generate(spec).to_dict()
