"""
MetrIQ Regulatory Engine - Automatic Test Plan Generator
Generates comprehensive, statutory test plans with sequenced test points,
loading/unloading schedules, eccentric test locations, repeatability cycles,
and pre-calculated MPE tolerance limits aligned with OIML R 76-1:2006 and Indian LM Rules.
"""

import math
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set

from .models import (
    AccuracyClass,
    InstrumentProfile,
    JobType,
    TestType,
    MassUnit,
    TestPoint,
    ApplicableTest,
    TestPlan,
    ReceptorType,
    MPEValue,
)
from .sources import REGULATORY_REGISTRY
from .mpe import calculate_mpe, get_mpe_breakpoints_for_instrument
from .applicability import get_applicable_tests
from .config import RegulatoryConfig, get_default_config, get_manual_review_checklist
from .scale_validation import validate_instrument_scales

# Modern Statutory Test Plan Generator (5-stage regulatory pipeline)
from .test_plan_generator import (
    RegulatoryTestPlanGenerator,
    GeneratedTestPlan,
    TestLoadPoint,
    ExecutableTestItem,
    generate_regulatory_test_plan,
)


def _round_to_e(val: float, e: float) -> float:
    """Rounds a calculated test load to the nearest verification scale interval e."""
    if e <= 0:
        return val
    steps = round(val / e)
    return round(steps * e, 6)


def generate_weighing_points(
    instrument: InstrumentProfile,
    job_type: JobType,
    standard_id: str,
    config: RegulatoryConfig,
) -> List[TestPoint]:
    """
    Generates sequenced test points for Weighing Performance Test (OIML R 76-1 Clause A.4.4).
    Includes Zero, Min, MPE transition breakpoints, intermediate steps, and Max.
    Runs increasing from Zero to Max, then decreasing from Max down to Zero.
    """
    loads_set: Set[float] = set()

    # Always include Zero and Min
    if config.include_zero_test_point:
        loads_set.add(0.0)
    if config.include_min_capacity_point and instrument.min_capacity > 0:
        loads_set.add(round(instrument.min_capacity, 6))

    # Add MPE transition breakpoints (e.g. 500e, 2000e)
    breakpoints = get_mpe_breakpoints_for_instrument(instrument)
    for bp in breakpoints:
        if instrument.min_capacity < bp < instrument.max_capacity:
            loads_set.add(round(bp, 6))

    # Add partial range maximums for multi-interval instruments
    if instrument.is_multi_interval and instrument.partial_ranges:
        for pr in instrument.partial_ranges:
            if pr.max_capacity < instrument.max_capacity:
                loads_set.add(round(pr.max_capacity, 6))

    # Add 50% Max if space permits
    if config.include_half_max_point:
        half_max = _round_to_e(instrument.max_capacity * 0.5, instrument.e)
        if instrument.min_capacity < half_max < instrument.max_capacity:
            loads_set.add(round(half_max, 6))

    # Add Max capacity
    if config.include_max_capacity_point:
        loads_set.add(round(instrument.max_capacity, 6))

    # If count is below minimum required, inject intermediate test loads
    sorted_loads = sorted(list(loads_set))
    if len(sorted_loads) < config.min_weighing_points_count:
        step_increment = (instrument.max_capacity - instrument.min_capacity) / (config.min_weighing_points_count - 1)
        for idx in range(1, config.min_weighing_points_count):
            injected = _round_to_e(instrument.min_capacity + idx * step_increment, instrument.e)
            if injected <= instrument.max_capacity:
                loads_set.add(round(injected, 6))

    increasing_loads = sorted(list(loads_set))

    # Decreasing loads (descending order, excluding duplicate Max at the top)
    decreasing_loads = list(reversed(increasing_loads[:-1]))

    points: List[TestPoint] = []
    step_no = 1

    # 1. Increasing load series
    for load in increasing_loads:
        eff_e = instrument.e
        load_e = load / eff_e if eff_e > 0 else 0.0
        mpe = calculate_mpe(load, instrument, job_type=job_type, standard_id=standard_id)
        desc = (
            "Zero load indication check"
            if load == 0.0
            else f"Weighing performance (Increasing) - Load: {load} {instrument.unit.value}"
        )
        points.append(
            TestPoint(
                step_number=step_no,
                test_type=TestType.WEIGHING_PERFORMANCE,
                description=desc,
                target_load=load,
                unit=instrument.unit,
                load_in_e=round(load_e, 2),
                direction="INCREASING",
                position="CENTER",
                expected_mpe=mpe,
                mandatory=True,
                reference_clause="OIML R 76-1:2006 Clause A.4.4.1",
                remarks="Ensure indicator is at rest before logging observation.",
            )
        )
        step_no += 1

    # 2. Decreasing load series
    for load in decreasing_loads:
        eff_e = instrument.e
        load_e = load / eff_e if eff_e > 0 else 0.0
        mpe = calculate_mpe(load, instrument, job_type=job_type, standard_id=standard_id)
        desc = (
            "Zero return check (Decreasing)"
            if load == 0.0
            else f"Weighing performance (Decreasing) - Load: {load} {instrument.unit.value}"
        )
        points.append(
            TestPoint(
                step_number=step_no,
                test_type=TestType.WEIGHING_PERFORMANCE,
                description=desc,
                target_load=load,
                unit=instrument.unit,
                load_in_e=round(load_e, 2),
                direction="DECREASING",
                position="CENTER",
                expected_mpe=mpe,
                mandatory=True,
                reference_clause="OIML R 76-1:2006 Clause A.4.4.2",
                remarks="Unload weights progressively without shock.",
            )
        )
        step_no += 1

    return points


def generate_eccentricity_points(
    instrument: InstrumentProfile,
    job_type: JobType,
    standard_id: str,
    config: RegulatoryConfig,
    start_step: int = 1,
) -> List[TestPoint]:
    """
    Generates test points for Eccentricity / Off-Center Loading Test (Clause A.4.7).
    Calculates appropriate test load based on receptor type (1/3 Max, 1/(N-1) Max, etc.).
    """
    points: List[TestPoint] = []

    # Calculate eccentric test load per Clause A.4.7
    if instrument.receptor_type in (ReceptorType.MORE_THAN_FOUR_POINTS, ReceptorType.TANK_HOPPER):
        # 1/(N-1) Max rule for platforms with N > 4 points of support
        n_supports = max(5, instrument.num_support_points)
        raw_load = instrument.max_capacity / (n_supports - 1)
        positions = [f"SUPPORT_POINT_{i+1}" for i in range(n_supports)]
        ref_clause = "OIML R 76-1:2006 Clause A.4.7.2 (1/(N-1) Max)"
    elif instrument.receptor_type == ReceptorType.ROLLING_LOAD:
        raw_load = instrument.max_capacity * 0.8
        positions = ["ROLLING_START", "ROLLING_MIDDLE", "ROLLING_END"]
        ref_clause = "OIML R 76-1:2006 Clause A.4.7.4 (Rolling load)"
    elif instrument.receptor_type == ReceptorType.SUSPENDED_LOAD:
        raw_load = instrument.max_capacity * 0.5
        positions = ["CENTER", "OFF_CENTER_FORWARD", "OFF_CENTER_BACKWARD"]
        ref_clause = "OIML R 76-1:2006 Clause A.4.7.5 (Suspended load)"
    else:
        # Standard platter / 4 points or less: 1/3 Max
        raw_load = instrument.max_capacity * config.eccentricity_load_ratio
        positions = [
            "CENTER",
            "CORNER_1_FRONT_LEFT",
            "CORNER_2_BACK_LEFT",
            "CORNER_3_BACK_RIGHT",
            "CORNER_4_FRONT_RIGHT",
        ]
        ref_clause = "OIML R 76-1:2006 Clause A.4.7.1 (1/3 Max standard platter)"

    ecc_load = _round_to_e(raw_load, instrument.e)
    mpe = calculate_mpe(ecc_load, instrument, job_type=job_type, standard_id=standard_id)
    load_e = ecc_load / instrument.e if instrument.e > 0 else 0.0

    step_no = start_step
    for pos in positions:
        points.append(
            TestPoint(
                step_number=step_no,
                test_type=TestType.ECCENTRICITY,
                description=f"Eccentric loading at {pos.replace('_', ' ').title()} - Load: {ecc_load} {instrument.unit.value}",
                target_load=ecc_load,
                unit=instrument.unit,
                load_in_e=round(load_e, 2),
                direction="STATIC",
                position=pos,
                expected_mpe=mpe,
                mandatory=True,
                reference_clause=ref_clause,
                remarks=f"Zero instrument before loading. Place test weight evenly within {pos}.",
            )
        )
        step_no += 1

    return points


def generate_repeatability_points(
    instrument: InstrumentProfile,
    job_type: JobType,
    standard_id: str,
    config: RegulatoryConfig,
    start_step: int = 1,
) -> List[TestPoint]:
    """
    Generates test points for Repeatability Test (Clause A.4.10).
    Runs 2 test series (approx. 50% Max and 100% Max) with specified cycles (3 for verification, 10 for approval).
    """
    points: List[TestPoint] = []
    if job_type == JobType.MODEL_APPROVAL:
        num_cycles = config.repeatability_cycles_approval
    elif instrument.accuracy_class in (AccuracyClass.CLASS_I, AccuracyClass.CLASS_II):
        num_cycles = max(6, config.repeatability_cycles_verification)
    else:
        num_cycles = config.repeatability_cycles_verification

    load_half = _round_to_e(instrument.max_capacity * config.repeatability_load_1_ratio, instrument.e)
    load_max = _round_to_e(instrument.max_capacity * config.repeatability_load_2_ratio, instrument.e)

    series_specs = [
        ("Series A (~50% Max)", load_half),
        ("Series B (~100% Max)", load_max),
    ]

    step_no = start_step
    for series_name, test_load in series_specs:
        mpe = calculate_mpe(test_load, instrument, job_type=job_type, standard_id=standard_id)
        load_e = test_load / instrument.e if instrument.e > 0 else 0.0
        for cycle in range(1, num_cycles + 1):
            points.append(
                TestPoint(
                    step_number=step_no,
                    test_type=TestType.REPEATABILITY,
                    description=f"Repeatability {series_name} - Run #{cycle} of {num_cycles} at {test_load} {instrument.unit.value}",
                    target_load=test_load,
                    unit=instrument.unit,
                    load_in_e=round(load_e, 2),
                    direction="STATIC",
                    position="CENTER",
                    expected_mpe=mpe,
                    mandatory=True,
                    reference_clause="OIML R 76-1:2006 Clause A.4.10 / IN LM 2011 Part II Clause 4",
                    remarks=f"Zero instrument before each run. Maximum spread between {num_cycles} runs must be <= |MPE|.",
                )
            )
            step_no += 1

    return points


def generate_discrimination_points(
    instrument: InstrumentProfile,
    job_type: JobType,
    standard_id: str,
    config: RegulatoryConfig,
    start_step: int = 1,
) -> List[TestPoint]:
    """Generates test points for Digital Discrimination Test (Clause A.4.8)."""
    points: List[TestPoint] = []
    d = instrument.actual_d
    extra_load = round(config.discrimination_load_factor * d, 6)

    test_loads = [
        ("Min Capacity", instrument.min_capacity),
        ("50% Max Capacity", _round_to_e(instrument.max_capacity * 0.5, instrument.e)),
        ("Max Capacity", instrument.max_capacity),
    ]

    step_no = start_step
    for name, base_load in test_loads:
        mpe = calculate_mpe(base_load, instrument, job_type=job_type, standard_id=standard_id)
        points.append(
            TestPoint(
                step_number=step_no,
                test_type=TestType.DISCRIMINATION,
                description=f"Discrimination at {name} ({base_load} {instrument.unit.value}) with +{extra_load} {instrument.unit.value} (1.4d)",
                target_load=base_load,
                unit=instrument.unit,
                load_in_e=round(base_load / instrument.e, 2),
                direction="STATIC",
                position="CENTER",
                expected_mpe=mpe,
                mandatory=True,
                reference_clause="OIML R 76-1:2006 Clause A.4.8",
                remarks=f"Place base load. Gently add extra load {extra_load} {instrument.unit.value}. Display must change unequivocally.",
            )
        )
        step_no += 1

    return points


def generate_tare_points(
    instrument: InstrumentProfile,
    job_type: JobType,
    standard_id: str,
    config: RegulatoryConfig,
    start_step: int = 1,
) -> List[TestPoint]:
    """Generates test points for Tare Device & Net Weighing Test (Clause A.4.6)."""
    points: List[TestPoint] = []
    if not instrument.has_tare:
        return points

    # Default tare load to 1/3 Max or specified tare
    raw_tare = instrument.max_subtractive_tare or (instrument.max_capacity * 0.33)
    tare_load = _round_to_e(raw_tare, instrument.e)
    max_net = instrument.max_capacity - tare_load

    net_loads = [
        instrument.min_capacity,
        _round_to_e(max_net * 0.5, instrument.e),
        _round_to_e(max_net, instrument.e),
    ]

    step_no = start_step
    for net_l in net_loads:
        gross_load = round(tare_load + net_l, 6)
        mpe = calculate_mpe(gross_load, instrument, job_type=job_type, tare_load=tare_load, standard_id=standard_id)
        points.append(
            TestPoint(
                step_number=step_no,
                test_type=TestType.TARE,
                description=f"Net weighing under Tare={tare_load} {instrument.unit.value} - Net Load: {net_l} {instrument.unit.value}",
                target_load=gross_load,
                unit=instrument.unit,
                load_in_e=round(net_l / instrument.e, 2),
                direction="STATIC",
                position="CENTER",
                expected_mpe=mpe,
                tare_load=tare_load,
                mandatory=True,
                reference_clause="OIML R 76-1:2006 Clause A.4.6",
                remarks="Apply tare load, trigger tare key, verify zero net indication, then apply net test load.",
            )
        )
        step_no += 1

    return points


def generate_test_plan(
    instrument: InstrumentProfile,
    job_type: JobType,
    standard_id: str = "OIML_R76_2006",
    config: Optional[RegulatoryConfig] = None,
) -> TestPlan:
    """
    Generates a complete, statutory Test Plan for Person 4 (Test Engine) and Person 3 (Instruments/Jobs).

    1. Validates the instrument profile against statutory accuracy limits.
    2. Determines all applicable test types.
    3. Generates discrete test points with directional sequence and pre-calculated MPE tolerance limits.
    4. Attaches statutory manual inspection review items.

    :param instrument: Instrument profile to test.
    :param job_type: Verification or approval job type.
    :param standard_id: Standard version (OIML_R76_2006, IN_LM_2011, etc.).
    :param config: Optional custom regulatory configuration.
    :return: TestPlan object.
    """
    cfg = config or get_default_config()
    source = REGULATORY_REGISTRY.get_or_default(standard_id)

    # 1. Validate instrument scale parameters
    val_result = validate_instrument_scales(instrument, standard_id=standard_id)

    # 2. Query applicable tests
    applicable_tests = get_applicable_tests(instrument, job_type=job_type, standard_id=standard_id)

    # 3. Generate test suites
    suites: Dict[str, List[TestPoint]] = {}
    current_step = 1

    for app_test in applicable_tests:
        if not app_test.applicable:
            continue

        tt = app_test.test_type
        if tt == TestType.WEIGHING_PERFORMANCE:
            pts = generate_weighing_points(instrument, job_type, standard_id, cfg)
            suites[tt.value] = pts
            current_step += len(pts)

        elif tt == TestType.ECCENTRICITY:
            pts = generate_eccentricity_points(instrument, job_type, standard_id, cfg, start_step=current_step)
            suites[tt.value] = pts
            current_step += len(pts)

        elif tt == TestType.REPEATABILITY:
            pts = generate_repeatability_points(instrument, job_type, standard_id, cfg, start_step=current_step)
            suites[tt.value] = pts
            current_step += len(pts)

        elif tt == TestType.DISCRIMINATION:
            pts = generate_discrimination_points(instrument, job_type, standard_id, cfg, start_step=current_step)
            suites[tt.value] = pts
            current_step += len(pts)

        elif tt == TestType.TARE:
            pts = generate_tare_points(instrument, job_type, standard_id, cfg, start_step=current_step)
            suites[tt.value] = pts
            current_step += len(pts)

    total_points = sum(len(pts) for pts in suites.values())

    # 4. Manual review items
    manual_items = [item.to_dict() for item in get_manual_review_checklist(instrument, job_type)]

    # 5. Build summary
    summary = {
        "manufacturer": instrument.manufacturer or "N/A",
        "model": instrument.model or "N/A",
        "serial_number": instrument.serial_number or "N/A",
        "accuracy_class": instrument.accuracy_class.roman,
        "max": f"{instrument.max_capacity} {instrument.unit.value}",
        "min": f"{instrument.min_capacity} {instrument.unit.value}",
        "e": f"{instrument.e} {instrument.unit.value}",
        "d": f"{instrument.actual_d} {instrument.unit.value}",
        "n": int(round(instrument.n)),
        "is_scale_valid": val_result.is_valid,
        "validation_issues_count": len(val_result.issues),
    }

    plan_id = f"PLAN-{uuid.uuid4().hex[:8].upper()}"
    generated_at = datetime.now(timezone.utc).isoformat()

    return TestPlan(
        plan_id=plan_id,
        generated_at=generated_at,
        regulatory_standard=source.short_title,
        job_type=job_type,
        instrument_summary=summary,
        applicable_tests=applicable_tests,
        test_suites=suites,
        total_test_points=total_points,
        manual_review_items=manual_items,
    )
