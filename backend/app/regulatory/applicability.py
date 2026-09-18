"""
MetrIQ Regulatory Engine - Test Applicability Matrix
Determines statutory and technical test applicability based on Job Type,
Instrument characteristics, and regulatory standards (OIML R 76-1 / Indian Legal Metrology).
"""

from typing import List, Dict, Any, Optional
from .models import InstrumentProfile, JobType, TestType, ApplicableTest
from .sources import REGULATORY_REGISTRY
from .test_applicability_engine import (
    IndicationType,
    InstrumentCharacteristics,
    InstrumentIndicationMode,
    StatutoryTestDefinition,
    TestEvaluationResult,
    ApplicabilityReport,
    ALL_STATUTORY_TESTS,
    RegulatoryTestApplicabilityEngine,
    evaluate_test_applicability,
)


def get_applicable_tests(
    instrument: InstrumentProfile,
    job_type: JobType,
    standard_id: str = "OIML_R76_2006",
) -> List[ApplicableTest]:
    """
    Evaluates which metrological tests are applicable for a given instrument and job type.

    Returns a prioritized list of ApplicableTest instances detailing applicability,
    statutory justification, and normative reference clauses.
    """
    source = REGULATORY_REGISTRY.get_or_default(standard_id)
    tests: List[ApplicableTest] = []

    # 1. VISUAL_EXAMINATION
    tests.append(
        ApplicableTest(
            test_type=TestType.VISUAL_EXAMINATION,
            title="Visual & Construction Examination",
            applicable=True,
            justification=(
                "Mandatory for all verification jobs. Verifies statutory markings (Max, Min, e, d, "
                "accuracy class), manufacturer plates, sealing provisions, and leveling device."
            ),
            standard_reference=f"{source.short_title} Clause 7 & Clause 3.9",
            priority=1,
            mandatory=True,
        )
    )

    # 2. WEIGHING_PERFORMANCE
    tests.append(
        ApplicableTest(
            test_type=TestType.WEIGHING_PERFORMANCE,
            title="Weighing Performance Test",
            applicable=True,
            justification=(
                "Mandatory core test for all verification jobs. Evaluates indication error across the full "
                "range with increasing and decreasing loads at critical breakpoint loads."
            ),
            standard_reference=f"{source.short_title} Clause A.4.4",
            priority=2,
            mandatory=True,
        )
    )

    # 3. ECCENTRICITY
    tests.append(
        ApplicableTest(
            test_type=TestType.ECCENTRICITY,
            title="Eccentricity / Off-Center Loading Test",
            applicable=True,
            justification=(
                "Mandatory test for load receptors. Verifies that off-center load distribution does not "
                "introduce errors exceeding MPE for the eccentric test load."
            ),
            standard_reference=f"{source.short_title} Clause A.4.7 / IN LM 2011 Part II Clause 3",
            priority=3,
            mandatory=True,
        )
    )

    # 4. REPEATABILITY
    tests.append(
        ApplicableTest(
            test_type=TestType.REPEATABILITY,
            title="Repeatability Test",
            applicable=True,
            justification=(
                "Mandatory metrological test. Verifies that the difference between repeated weighing results "
                "for the same load does not exceed the absolute MPE for that load."
            ),
            standard_reference=f"{source.short_title} Clause A.4.10 / IN LM 2011 Part II Clause 4",
            priority=4,
            mandatory=True,
        )
    )

    # 5. DISCRIMINATION
    is_disc_applicable = job_type in (JobType.MODEL_APPROVAL, JobType.INITIAL_VERIFICATION)
    tests.append(
        ApplicableTest(
            test_type=TestType.DISCRIMINATION,
            title="Digital Discrimination Test",
            applicable=is_disc_applicable,
            justification=(
                "Verifies display response to an extra load of 1.4d placed gently on the loaded receptor. "
                "Mandatory for Pattern Approval and Initial Verification."
                if is_disc_applicable
                else "Optional during periodic re-verification unless digital resolution is in question."
            ),
            standard_reference=f"{source.short_title} Clause A.4.8",
            priority=5,
            mandatory=is_disc_applicable,
        )
    )

    # 6. TARE
    is_tare_applicable = instrument.has_tare
    tests.append(
        ApplicableTest(
            test_type=TestType.TARE,
            title="Tare Device & Net Weighing Test",
            applicable=is_tare_applicable,
            justification=(
                "Instrument is equipped with a tare balancing/weighing device. Verifies tare accuracy "
                "and net weighing performance under tare."
                if is_tare_applicable
                else "Instrument has no tare facility declared."
            ),
            standard_reference=f"{source.short_title} Clause A.4.6",
            priority=6,
            mandatory=is_tare_applicable,
        )
    )

    # 7. ZERO_SETTING_AND_TRACKING
    is_zero_applicable = job_type in (JobType.MODEL_APPROVAL, JobType.INITIAL_VERIFICATION) or instrument.has_zero_tracking
    tests.append(
        ApplicableTest(
            test_type=TestType.ZERO_SETTING_AND_TRACKING,
            title="Zero-Setting & Zero-Tracking Test",
            applicable=is_zero_applicable,
            justification=(
                "Evaluates semi-automatic zero-setting accuracy (<= 0.25e) and zero-tracking rate limit (<= 0.5d/s). "
                "Mandatory for Type Evaluation and Initial Verification."
                if is_zero_applicable
                else "Not required for standard periodic re-verification."
            ),
            standard_reference=f"{source.short_title} Clause A.4.1 - A.4.3",
            priority=7,
            mandatory=is_zero_applicable,
        )
    )

    # 8. TILTING
    is_tilt_applicable = (
        job_type == JobType.MODEL_APPROVAL
        or instrument.is_mobile
        or not instrument.has_level_indicator
    )
    tests.append(
        ApplicableTest(
            test_type=TestType.TILTING,
            title="Tilting Sensitivity Test",
            applicable=is_tilt_applicable,
            justification=(
                "Instrument is mobile/transportable or lacks self-leveling / level bubble. "
                "Evaluates performance under 1:1000 or 50:1000 tilt."
                if is_tilt_applicable
                else "Instrument is a fixed stationary installation with verified level indicator."
            ),
            standard_reference=f"{source.short_title} Clause A.4.4",
            priority=8,
            mandatory=is_tilt_applicable,
        )
    )

    # 9. CREEP_AND_ZERO_RETURN
    is_creep_applicable = (
        job_type == JobType.MODEL_APPROVAL
        or (job_type == JobType.POST_REPAIR and instrument.is_electronic)
    )
    tests.append(
        ApplicableTest(
            test_type=TestType.CREEP_AND_ZERO_RETURN,
            title="Creep & Zero Return Test",
            applicable=is_creep_applicable,
            justification=(
                "Evaluates drift under continuous Max load for 30 minutes (<= 0.5e) and zero return (<= 0.5e). "
                "Required for Pattern Approval and major load-cell post-repair verification."
                if is_creep_applicable
                else "Not applicable for routine periodic re-verification."
            ),
            standard_reference=f"{source.short_title} Clause A.4.11",
            priority=9,
            mandatory=is_creep_applicable,
        )
    )

    # 10. TEMPERATURE_EFFECT
    is_temp_applicable = job_type == JobType.MODEL_APPROVAL
    tests.append(
        ApplicableTest(
            test_type=TestType.TEMPERATURE_EFFECT,
            title="Temperature Effect on No-Load & Span Test",
            applicable=is_temp_applicable,
            justification=(
                "Evaluates temperature coefficients across operating range in environmental chamber. "
                "Strictly a Type Evaluation / Model Approval test."
                if is_temp_applicable
                else "Field verification tests are performed at ambient site temperature."
            ),
            standard_reference=f"{source.short_title} Clause A.5.3",
            priority=10,
            mandatory=is_temp_applicable,
        )
    )

    # 11. VOLTAGE_VARIATION
    is_volt_applicable = job_type == JobType.MODEL_APPROVAL and instrument.is_electronic
    tests.append(
        ApplicableTest(
            test_type=TestType.VOLTAGE_VARIATION,
            title="Mains & Battery Voltage Variation Test",
            applicable=is_volt_applicable,
            justification=(
                "Tests immunity to voltage fluctuations (85% to 110% of nominal) or battery cut-off. "
                "Pattern Approval requirement for electronic instruments."
                if is_volt_applicable
                else "Not applicable for field verification jobs."
            ),
            standard_reference=f"{source.short_title} Clause A.5.4",
            priority=11,
            mandatory=is_volt_applicable,
        )
    )

    # 12. SOFTWARE_EXAMINATION
    is_sw_applicable = (
        instrument.has_software
        and job_type in (JobType.MODEL_APPROVAL, JobType.INITIAL_VERIFICATION, JobType.POST_REPAIR)
    )
    tests.append(
        ApplicableTest(
            test_type=TestType.SOFTWARE_EXAMINATION,
            title="Software Securing & Audit Trail Examination",
            applicable=is_sw_applicable,
            justification=(
                "Verifies legally relevant software version, cryptographic checksum, and calibration event counter. "
                "Mandatory for software-equipped electronic instruments."
                if is_sw_applicable
                else "Instrument is mechanical, non-software equipped, or routine field re-check."
            ),
            standard_reference=f"{source.short_title} Clause 5.5",
            priority=12,
            mandatory=is_sw_applicable,
        )
    )

    # Sort by priority
    return sorted(tests, key=lambda t: t.priority)


def is_test_applicable(
    test_type: TestType,
    instrument: InstrumentProfile,
    job_type: JobType,
    standard_id: str = "OIML_R76_2006",
) -> bool:
    """Convenience function to quickly check applicability of a specific test type."""
    applicable_tests = get_applicable_tests(instrument, job_type, standard_id)
    for t in applicable_tests:
        if t.test_type == test_type:
            return t.applicable
    return False
