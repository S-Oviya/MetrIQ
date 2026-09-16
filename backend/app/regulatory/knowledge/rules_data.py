"""
MetrIQ Regulatory Knowledge Base - Structured Metrological Rules
Detailed rule definitions covering MPE, test weights, eccentricity, repeatability,
discrimination, temperature drift, creep, zero-setting, tare, multi-range/interval,
and electronic instrument provisions under Indian Legal Metrology and OIML R 76-1.
"""

from typing import Dict, Any, List
from .schema import (
    RegulatoryRule,
    RuleCategory,
    SourceCitation,
    LegalOrigin,
    VerificationStatus,
)


METROLOGICAL_RULES: Dict[str, RegulatoryRule] = {
    # 1. TEST WEIGHTS ACCURACY REQUIREMENT
    "RULE_TEST_WEIGHT_ACCURACY": RegulatoryRule(
        rule_id="RULE_TEST_WEIGHT_ACCURACY",
        title="Standard Test Weights Accuracy & MPE Ratio",
        category=RuleCategory.TEST_WEIGHTS,
        description=(
            "The standard weights or test loads used for the statutory verification of an instrument "
            "shall not have an error greater than 1/3 of the Maximum Permissible Error (MPE) of the "
            "instrument for the applied load. If auxiliary indicating devices (d < e) are used, "
            "the test weight error shall not exceed 1/5 of the instrument MPE."
        ),
        citation=SourceCitation(
            source_document="Legal Metrology (General) Rules, 2011 / OIML R 76-1:2006",
            clause_or_section="Sixth Schedule (Standards) / Clause 3.7.1",
            table_or_schedule="Sixth Schedule Part I & Part II",
            effective_date="2011-04-01",
            legal_origin=LegalOrigin.INDIAN_STATUTORY,
            verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
            notes="Mandates 1/3 instrument MPE limit for reference/working test standards.",
        ),
        is_configurable=True,
        requires_manual_review=True,
        parameters={
            "max_test_weight_mpe_ratio": 1.0 / 3.0,
            "auxiliary_device_mpe_ratio": 1.0 / 5.0,
            "standard_class_mapping": {
                "CLASS_I": ["E1", "E2"],
                "CLASS_II": ["F1", "F2"],
                "CLASS_III": ["M1"],
                "CLASS_IIII": ["M2", "M3"],
            },
        },
        version="2026.1",
    ),

    # 2. ECCENTRICITY TEST LOAD
    "RULE_ECCENTRICITY_LOAD": RegulatoryRule(
        rule_id="RULE_ECCENTRICITY_LOAD",
        title="Eccentricity / Off-Center Loading Test Schedule",
        category=RuleCategory.ECCENTRICITY,
        description=(
            "On an instrument with a load receptor having 4 or fewer points of support, the test load "
            "shall be equal to 1/3 of the sum of maximum capacity and maximum additive tare (or 1/3 Max). "
            "For instruments with N > 4 points of support (large platform / weighbridge), the load over each "
            "support shall be 1/(N-1) of Max. For rolling loads, a standard concentrated test load is used."
        ),
        citation=SourceCitation(
            source_document="Legal Metrology (General) Rules, 2011 / OIML R 76-1:2006",
            clause_or_section="Seventh Schedule Part II Clause 3 / Clause A.4.7",
            table_or_schedule="Clause A.4.7.1 - A.4.7.5",
            effective_date="2011-04-01",
            legal_origin=LegalOrigin.INDIAN_STATUTORY,
            verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
        ),
        is_configurable=True,
        requires_manual_review=False,
        parameters={
            "standard_platter_ratio": 1.0 / 3.0,
            "supports_greater_than_four_formula": "1 / (N - 1) * Max",
            "rolling_load_ratio": 0.8,
            "positions_four_supports": ["CENTER", "CORNER_1_FL", "CORNER_2_BL", "CORNER_3_BR", "CORNER_4_FR"],
            "max_allowed_error_formula": "MPE for eccentric test load",
        },
        version="2026.1",
    ),

    # 3. REPEATABILITY TEST REQUIREMENTS
    "RULE_REPEATABILITY": RegulatoryRule(
        rule_id="RULE_REPEATABILITY",
        title="Repeatability Test Series and Spread Limits",
        category=RuleCategory.REPEATABILITY,
        description=(
            "Two series of weighings shall be performed: one with a load of approximately 50% Max, and "
            "one with a load of approximately 100% Max (or 80% Max for heavy scales). At least 3 weighings "
            "per series are required for verification, and 10 weighings (or 6 for Class I/II) for pattern approval. "
            "The maximum difference between any two readings for the same load shall not exceed the absolute "
            "value of the MPE of the instrument for that load."
        ),
        citation=SourceCitation(
            source_document="Legal Metrology (General) Rules, 2011 / OIML R 76-1:2006",
            clause_or_section="Seventh Schedule Part II Clause 4 / Clause A.4.10",
            effective_date="2011-04-01",
            legal_origin=LegalOrigin.INDIAN_STATUTORY,
            verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
        ),
        is_configurable=True,
        requires_manual_review=False,
        parameters={
            "series_loads": [0.5, 1.0],
            "cycles_verification": 3,
            "cycles_pattern_approval": 10,
            "cycles_class_i_ii_pattern_approval": 6,
            "spread_limit_formula": "abs(MPE) for applied load",
        },
        version="2026.1",
    ),

    # 4. DIGITAL DISCRIMINATION
    "RULE_DIGITAL_DISCRIMINATION": RegulatoryRule(
        rule_id="RULE_DIGITAL_DISCRIMINATION",
        title="Digital Discrimination Test Load and Response",
        category=RuleCategory.DISCRIMINATION,
        description=(
            "An additional load of 1.4 times the actual scale interval (1.4d) placed gently on the loaded "
            "receptor shall cause an unequivocal increase in the displayed reading by at least 1d. "
            "Evaluated at Min, 50% Max, and Max."
        ),
        citation=SourceCitation(
            source_document="OIML R 76-1:2006 (E)",
            clause_or_section="Clause A.4.8 & Clause 3.8",
            effective_date="2006-10-01",
            legal_origin=LegalOrigin.OIML_TECHNICAL,
            verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
            notes="Technical requirement for digital indicating instruments.",
        ),
        is_configurable=False,
        requires_manual_review=False,
        parameters={
            "extra_load_factor": 1.4,
            "minimum_display_change": 1.0,  # in d
            "test_points": ["MIN", "50% MAX", "MAX"],
        },
        version="2026.1",
    ),

    # 5. TEMPERATURE DRIFT LIMITS
    "RULE_TEMPERATURE_DRIFT": RegulatoryRule(
        rule_id="RULE_TEMPERATURE_DRIFT",
        title="Temperature Effect on No-Load and Span Drift",
        category=RuleCategory.TEMPERATURE_DRIFT,
        description=(
            "The zero indication shall not vary by more than 1 verification scale interval (1e) for a "
            "temperature change of 5°C for Class I instruments, or 1e for a change of 2°C for Class II, III, "
            "and IIII instruments. During pattern evaluation, span errors across operating limits (-10°C to +40°C) "
            "must remain strictly within statutory MPE."
        ),
        citation=SourceCitation(
            source_document="Legal Metrology (General) Rules, 2011 / OIML R 76-1:2006",
            clause_or_section="Seventh Schedule Part I / Clause A.5.3",
            effective_date="2011-04-01",
            legal_origin=LegalOrigin.INDIAN_STATUTORY,
            verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
        ),
        is_configurable=False,
        requires_manual_review=False,
        parameters={
            "max_zero_drift_class_i_per_5c": 1.0,  # 1e per 5 deg C
            "max_zero_drift_class_ii_iii_iiii_per_2c": 1.0,  # 1e per 2 deg C
            "standard_temperature_range_min_c": -10.0,
            "standard_temperature_range_max_c": 40.0,
        },
        version="2026.1",
    ),

    # 6. CREEP AND ZERO RETURN
    "RULE_CREEP_AND_ZERO_RETURN": RegulatoryRule(
        rule_id="RULE_CREEP_AND_ZERO_RETURN",
        title="Creep and Zero Return Under Sustained Max Load",
        category=RuleCategory.CREEP_AND_ZERO_RETURN,
        description=(
            "When loaded with Maximum capacity for 30 minutes (or 4 hours for model approval), the difference "
            "between the indication obtained immediately after loading (at 30 seconds) and at 30 minutes "
            "shall not exceed 0.5e. The zero return error upon unloading shall not exceed 0.5e."
        ),
        citation=SourceCitation(
            source_document="OIML R 76-1:2006 (E)",
            clause_or_section="Clause A.4.11 & Clause 3.9.4.1",
            effective_date="2006-10-01",
            legal_origin=LegalOrigin.OIML_TECHNICAL,
            verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
        ),
        is_configurable=False,
        requires_manual_review=False,
        parameters={
            "creep_duration_minutes": 30,
            "max_drift_in_e": 0.5,
            "max_zero_return_in_e": 0.5,
            "intermediate_check_minute": 15,
        },
        version="2026.1",
    ),

    # 7. ZERO-SETTING AND ZERO-TRACKING
    "RULE_ZERO_SETTING": RegulatoryRule(
        rule_id="RULE_ZERO_SETTING",
        title="Zero-Setting Ranges and Automatic Zero-Tracking Limits",
        category=RuleCategory.ZERO_SETTING,
        description=(
            "Initial zero-setting range shall not exceed 20% (+/- 10%) or 4% (+/- 2%) of Max depending on model. "
            "Semi-automatic zero-setting range shall not exceed +/- 2% of Max. "
            "The error of zero-setting shall not exceed +/- 0.25e. "
            "Automatic zero-tracking rate shall not exceed 0.5d per second."
        ),
        citation=SourceCitation(
            source_document="Legal Metrology (General) Rules, 2011 / OIML R 76-1:2006",
            clause_or_section="Seventh Schedule Part I / Clause 4.5.1 - 4.5.7",
            effective_date="2011-04-01",
            legal_origin=LegalOrigin.INDIAN_STATUTORY,
            verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
        ),
        is_configurable=True,
        requires_manual_review=False,
        parameters={
            "initial_zero_setting_percent_max": 4.0,
            "semi_automatic_zero_percent_max": 2.0,
            "max_zero_setting_error_in_e": 0.25,
            "max_zero_tracking_rate_d_per_second": 0.5,
        },
        version="2026.1",
    ),

    # 8. TARE RULES
    "RULE_TARE": RegulatoryRule(
        rule_id="RULE_TARE",
        title="Tare Device Accuracy and Net Load MPE",
        category=RuleCategory.TARE,
        description=(
            "A tare device shall permit setting indication to zero with accuracy <= +/- 0.25e. "
            "For any tare value, the MPE for net loads shall be equal to the MPE for a gross load of the "
            "same value. Subtractive tare capacity cannot exceed Max."
        ),
        citation=SourceCitation(
            source_document="Legal Metrology (General) Rules, 2011 / OIML R 76-1:2006",
            clause_or_section="Seventh Schedule Part I / Clause 3.5.3.3 & 4.6",
            effective_date="2011-04-01",
            legal_origin=LegalOrigin.INDIAN_STATUTORY,
            verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
        ),
        is_configurable=False,
        requires_manual_review=False,
        parameters={
            "tare_setting_accuracy_in_e": 0.25,
            "net_mpe_governed_by_net_load": True,
            "preset_tare_rounding": "0.1d or 1d",
        },
        version="2026.1",
    ),

    # 9. MULTI-RANGE HANDLING
    "RULE_MULTI_RANGE": RegulatoryRule(
        rule_id="RULE_MULTI_RANGE",
        title="Multi-Range Instrument Architecture",
        category=RuleCategory.MULTI_RANGE,
        description=(
            "An instrument having two or more weighing ranges with different maximum capacities and "
            "different scale intervals, each extending from zero to its Max capacity. "
            "Each individual range shall independently satisfy all requirements of the declared accuracy class."
        ),
        citation=SourceCitation(
            source_document="OIML R 76-1:2006 (E)",
            clause_or_section="Clause 3.2.2 & Clause 3.4",
            effective_date="2006-10-01",
            legal_origin=LegalOrigin.OIML_TECHNICAL,
            verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
        ),
        is_configurable=False,
        requires_manual_review=False,
        parameters={
            "independent_range_validation": True,
            "tare_handling_per_range": "Governed by active range scale interval",
        },
        version="2026.1",
    ),

    # 10. MULTI-INTERVAL HANDLING
    "RULE_MULTI_INTERVAL": RegulatoryRule(
        rule_id="RULE_MULTI_INTERVAL",
        title="Multi-Interval Instrument Partial Ranges and Auxiliary Device Prohibition",
        category=RuleCategory.MULTI_INTERVAL,
        description=(
            "An instrument having one weighing range divided into partial weighing ranges (e1 < e2 < ... < er). "
            "Each partial range must satisfy statutory n_min and n_max. "
            "Auxiliary indicating devices (d < e) are strictly prohibited on multi-interval instruments. "
            "Transition points switch automatically upon increasing and decreasing loads."
        ),
        citation=SourceCitation(
            source_document="Legal Metrology (General) Rules, 2011 / OIML R 76-1:2006",
            clause_or_section="Seventh Schedule Part I / Clause 3.3",
            effective_date="2011-04-01",
            legal_origin=LegalOrigin.INDIAN_STATUTORY,
            verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
        ),
        is_configurable=False,
        requires_manual_review=False,
        parameters={
            "auxiliary_devices_permitted": False,
            "strictly_increasing_intervals": True,
            "min_partial_ranges": 2,
        },
        version="2026.1",
    ),

    # 11. ELECTRONIC INSTRUMENT IMMUNITY & POWER
    "RULE_ELECTRONIC_INSTRUMENTS": RegulatoryRule(
        rule_id="RULE_ELECTRONIC_INSTRUMENTS",
        title="Electronic Instruments Warm-Up and Mains Voltage Immunity",
        category=RuleCategory.ELECTRONIC_INSTRUMENT,
        description=(
            "Electronic instruments shall maintain metrological accuracy across mains voltage variations of "
            "-15% to +10% of nominal voltage. If powered by battery, the instrument shall automatically inhibit "
            "weighing operations or display an error when voltage drops below the operating threshold. "
            "Warm-up period must be observed prior to testing."
        ),
        citation=SourceCitation(
            source_document="Legal Metrology (General) Rules, 2011 / OIML R 76-1:2006",
            clause_or_section="Seventh Schedule Part I / Clause A.5.4 & Clause 5",
            effective_date="2011-04-01",
            legal_origin=LegalOrigin.INDIAN_STATUTORY,
            verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
        ),
        is_configurable=False,
        requires_manual_review=True,
        parameters={
            "voltage_upper_tolerance_percent": 10.0,
            "voltage_lower_tolerance_percent": -15.0,
            "automatic_low_battery_inhibition": True,
            "warm_up_time_minutes": 30,
        },
        version="2026.1",
    ),

    # 12. OIML R 76-2 TEST REPORT FORMAT (PRACTICE / DEFAULT FORMAT)
    "RULE_OIML_R76_2_REPORT_FORMAT": RegulatoryRule(
        rule_id="RULE_OIML_R76_2_REPORT_FORMAT",
        title="OIML R 76-2 Test Report Format (Technical Practice Layout)",
        category=RuleCategory.STATUTORY_FEES_AND_PROCEDURES,
        description=(
            "OIML R 76-2 provides a standardized international test reporting layout for pattern evaluation. "
            "IMPORTANT STATUTORY DISTINCTION: OIML R 76-2 is an international testing report format / practice "
            "template. It is NOT an Indian statutory requirement under the Legal Metrology Act, 2009. "
            "The statutory Indian verification certificate is prescribed under the Third Schedule of the "
            "Legal Metrology (General) Rules, 2011."
        ),
        citation=SourceCitation(
            source_document="OIML R 76-2:2007 (E)",
            clause_or_section="Complete Document",
            effective_date="2007-05-01",
            legal_origin=LegalOrigin.PRACTICE_REPORT_FORMAT,
            verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
            notes="Used as standardized technical template; not enacted as statutory law in India.",
        ),
        is_configurable=True,
        requires_manual_review=False,
        parameters={
            "is_indian_statutory": False,
            "format_purpose": "Pattern Evaluation Test Record Template",
            "statutory_indian_counterpart": "Third Schedule, Legal Metrology (General) Rules, 2011",
        },
        version="2026.1",
    ),
}
