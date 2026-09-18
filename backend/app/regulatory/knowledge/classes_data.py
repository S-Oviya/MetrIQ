"""
MetrIQ Regulatory Knowledge Base - Accuracy Class Definitions
Comprehensive, structured metrological specifications for Accuracy Classes I, II, III, IIII
based on Indian Legal Metrology (General) Rules, 2011 and OIML R 76-1:2006.
"""

from typing import Dict, List, Any
from app.regulatory.models import AccuracyClass
from .schema import (
    AccuracyClassDefinition,
    SourceCitation,
    LegalOrigin,
    VerificationStatus,
)


CLASS_DEFINITIONS: Dict[AccuracyClass, AccuracyClassDefinition] = {
    AccuracyClass.CLASS_I: AccuracyClassDefinition(
        accuracy_class=AccuracyClass.CLASS_I,
        display_name="Class I (Special Accuracy)",
        description=(
            "Micro-balances, analytical balances, and ultra-precision metrology standards. "
            "Primarily used in chemical analysis, pharmaceutical testing, precious standards, and research."
        ),
        e_ranges=[
            {
                "range_id": "CLASS_I_STANDARD",
                "e_min_grams": 0.001,      # 1 mg
                "e_max_grams": None,       # No upper limit
                "n_min": 50000,
                "n_max": None,             # No upper limit on n
                "min_capacity_factor": 100,# Min = 100 * e
                "description": "Standard Class I verification scale interval e >= 1 mg, n >= 50,000, Min = 100e.",
            }
        ],
        mpe_thresholds_initial=[
            {"load_min_e": 0.0, "load_max_e": 50000.0, "mpe_e": 0.5},
            {"load_min_e": 50000.0, "load_max_e": 200000.0, "mpe_e": 1.0},
            {"load_min_e": 200000.0, "load_max_e": float("inf"), "mpe_e": 1.5},
        ],
        mpe_thresholds_subsequent=[
            {"load_min_e": 0.0, "load_max_e": 50000.0, "mpe_e": 1.0},
            {"load_min_e": 50000.0, "load_max_e": 200000.0, "mpe_e": 2.0},
            {"load_min_e": 200000.0, "load_max_e": float("inf"), "mpe_e": 3.0},
        ],
        applicability_rules=[
            "Auxiliary indicating devices (d < e <= 10d) are permitted (OIML R 76 Clause 3.4.1).",
            "Not eligible for GATC verification; must be verified by statutory Legal Metrology Officers.",
            "Test weights used for verification must have error <= 1/3 MPE of the instrument (Class E2 or F1).",
            "Operating temperature span must be at least 5°C if special limits are specified.",
        ],
        citations=[
            SourceCitation(
                source_document="Legal Metrology (General) Rules, 2011",
                clause_or_section="Seventh Schedule, Heading A, Part I",
                table_or_schedule="Table 1 & Table 2",
                effective_date="2011-04-01",
                legal_origin=LegalOrigin.INDIAN_STATUTORY,
                verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
                notes="Statutory Indian classification and MPE table for Class I.",
            ),
            SourceCitation(
                source_document="OIML R 76-1:2006 (E)",
                clause_or_section="Clause 3.2 & Clause 3.5",
                table_or_schedule="Table 3 & Table 6",
                effective_date="2006-10-01",
                legal_origin=LegalOrigin.OIML_TECHNICAL,
                verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
                notes="International technical classification and MPE table.",
            ),
        ],
        version="2026.1",
    ),

    AccuracyClass.CLASS_II: AccuracyClassDefinition(
        accuracy_class=AccuracyClass.CLASS_II,
        display_name="Class II (High Accuracy)",
        description=(
            "Precision balances, gold and precious stone weighing scales, and laboratory balances. "
            "Used in jewelry trade, bullion transactions, pharmaceutical dispensing, and high-precision laboratories."
        ),
        e_ranges=[
            {
                "range_id": "CLASS_II_LOW_E",
                "e_min_grams": 0.001,      # 1 mg
                "e_max_grams": 0.05,       # 50 mg
                "n_min": 100,
                "n_max": 100000,
                "min_capacity_factor": 20, # Min = 20 * e
                "description": "Class II for 1 mg <= e <= 50 mg: n from 100 to 100,000, Min = 20e.",
            },
            {
                "range_id": "CLASS_II_HIGH_E",
                "e_min_grams": 0.1,        # 100 mg
                "e_max_grams": None,       # No upper limit
                "n_min": 5000,
                "n_max": 100000,
                "min_capacity_factor": 50, # Min = 50 * e
                "description": "Class II for e >= 0.1 g: n from 5,000 to 100,000, Min = 50e.",
            },
        ],
        mpe_thresholds_initial=[
            {"load_min_e": 0.0, "load_max_e": 5000.0, "mpe_e": 0.5},
            {"load_min_e": 5000.0, "load_max_e": 20000.0, "mpe_e": 1.0},
            {"load_min_e": 20000.0, "load_max_e": 100000.0, "mpe_e": 1.5},
        ],
        mpe_thresholds_subsequent=[
            {"load_min_e": 0.0, "load_max_e": 5000.0, "mpe_e": 1.0},
            {"load_min_e": 5000.0, "load_max_e": 20000.0, "mpe_e": 2.0},
            {"load_min_e": 20000.0, "load_max_e": 100000.0, "mpe_e": 3.0},
        ],
        applicability_rules=[
            "Auxiliary indicating devices (d < e <= 10d) are permitted (OIML R 76 Clause 3.4.1).",
            "CRITICAL: Class II instruments are NOT eligible for GATC verification under the 2013 GATC Rules. "
            "They must be verified directly by the State Legal Metrology Officer.",
            "Test weights must have error <= 1/3 MPE of the instrument (Class F1 or F2).",
            "Operating temperature span must be at least 15°C if special limits are specified.",
        ],
        citations=[
            SourceCitation(
                source_document="Legal Metrology (General) Rules, 2011",
                clause_or_section="Seventh Schedule, Heading A, Part I",
                table_or_schedule="Table 1 & Table 2",
                effective_date="2011-04-01",
                legal_origin=LegalOrigin.INDIAN_STATUTORY,
                verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
            ),
            SourceCitation(
                source_document="Legal Metrology (Government Approved Test Centre) Rules, 2013",
                clause_or_section="Rule 3 and First Schedule",
                effective_date="2013-04-01",
                legal_origin=LegalOrigin.INDIAN_STATUTORY,
                verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
                notes="GATC First Schedule explicitly excludes Class II; verification remains with State LMO.",
            ),
            SourceCitation(
                source_document="OIML R 76-1:2006 (E)",
                clause_or_section="Clause 3.2 & Clause 3.5",
                table_or_schedule="Table 3 & Table 6",
                effective_date="2006-10-01",
                legal_origin=LegalOrigin.OIML_TECHNICAL,
                verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
            ),
        ],
        version="2026.1",
    ),

    AccuracyClass.CLASS_III: AccuracyClassDefinition(
        accuracy_class=AccuracyClass.CLASS_III,
        display_name="Class III (Medium Accuracy)",
        description=(
            "Commercial counter/bench scales, retail point-of-sale scales, platform scales, "
            "and vehicular weighbridges. Represents the vast majority of commercial trade instruments in India."
        ),
        e_ranges=[
            {
                "range_id": "CLASS_III_LOW_E",
                "e_min_grams": 0.1,        # 100 mg
                "e_max_grams": 2.0,        # 2 g
                "n_min": 100,
                "n_max": 10000,
                "min_capacity_factor": 20, # Min = 20 * e
                "description": "Class III for 0.1 g <= e <= 2 g: n from 100 to 10,000, Min = 20e.",
            },
            {
                "range_id": "CLASS_III_HIGH_E",
                "e_min_grams": 5.0,        # 5 g
                "e_max_grams": None,       # No upper limit
                "n_min": 500,
                "n_max": 10000,
                "min_capacity_factor": 20, # Min = 20 * e
                "description": "Class III for e >= 5 g: n from 500 to 10,000, Min = 20e.",
            },
        ],
        mpe_thresholds_initial=[
            {"load_min_e": 0.0, "load_max_e": 500.0, "mpe_e": 0.5},
            {"load_min_e": 500.0, "load_max_e": 2000.0, "mpe_e": 1.0},
            {"load_min_e": 2000.0, "load_max_e": 10000.0, "mpe_e": 1.5},
        ],
        mpe_thresholds_subsequent=[
            {"load_min_e": 0.0, "load_max_e": 500.0, "mpe_e": 1.0},
            {"load_min_e": 500.0, "load_max_e": 2000.0, "mpe_e": 2.0},
            {"load_min_e": 2000.0, "load_max_e": 10000.0, "mpe_e": 3.0},
        ],
        applicability_rules=[
            "Auxiliary indicating devices (d < e) are strictly PROHIBITED for Class III; d must equal e.",
            "GATC Routing Rule: Eligible for GATC verification ONLY IF maximum capacity Max <= 150 kg.",
            "Instruments exceeding 150 kg (e.g. heavy platforms, weighbridges) must be verified by State LMO.",
            "Standard test weights: Class M1 (or M2 for coarse tests). Test weight error <= 1/3 MPE.",
            "Standard operating temperature range: -10°C to +40°C unless otherwise marked.",
        ],
        citations=[
            SourceCitation(
                source_document="Legal Metrology (General) Rules, 2011",
                clause_or_section="Seventh Schedule, Heading A, Part I",
                table_or_schedule="Table 1 & Table 2",
                effective_date="2011-04-01",
                legal_origin=LegalOrigin.INDIAN_STATUTORY,
                verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
            ),
            SourceCitation(
                source_document="Legal Metrology (Government Approved Test Centre) Rules, 2013",
                clause_or_section="First Schedule",
                effective_date="2013-04-01",
                legal_origin=LegalOrigin.INDIAN_STATUTORY,
                verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
                notes="Authorizes GATCs to verify Class III NAWI having capacity up to 150 kg.",
            ),
            SourceCitation(
                source_document="OIML R 76-1:2006 (E)",
                clause_or_section="Clause 3.2 & Clause 3.5",
                table_or_schedule="Table 3 & Table 6",
                effective_date="2006-10-01",
                legal_origin=LegalOrigin.OIML_TECHNICAL,
                verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
            ),
        ],
        version="2026.1",
    ),

    AccuracyClass.CLASS_IIII: AccuracyClassDefinition(
        accuracy_class=AccuracyClass.CLASS_IIII,
        display_name="Class IIII (Ordinary Accuracy)",
        description=(
            "Heavy industrial scales, crane scales, scrap yard scales, and bulk material weighing. "
            "Used for coarse weighing where high resolution is not economically or physically required."
        ),
        e_ranges=[
            {
                "range_id": "CLASS_IIII_STANDARD",
                "e_min_grams": 5.0,        # 5 g
                "e_max_grams": None,       # No upper limit
                "n_min": 100,
                "n_max": 1000,
                "min_capacity_factor": 10, # Min = 10 * e
                "description": "Class IIII for e >= 5 g: n from 100 to 1,000, Min = 10e.",
            }
        ],
        mpe_thresholds_initial=[
            {"load_min_e": 0.0, "load_max_e": 50.0, "mpe_e": 0.5},
            {"load_min_e": 50.0, "load_max_e": 200.0, "mpe_e": 1.0},
            {"load_min_e": 200.0, "load_max_e": 1000.0, "mpe_e": 1.5},
        ],
        mpe_thresholds_subsequent=[
            {"load_min_e": 0.0, "load_max_e": 50.0, "mpe_e": 1.0},
            {"load_min_e": 50.0, "load_max_e": 200.0, "mpe_e": 2.0},
            {"load_min_e": 200.0, "load_max_e": 1000.0, "mpe_e": 3.0},
        ],
        applicability_rules=[
            "Auxiliary indicating devices (d < e) are strictly PROHIBITED; d must equal e.",
            "GATC Routing Rule: Eligible for GATC verification across all capacities within test weight limits.",
            "Standard test weights: Class M2 or M3.",
        ],
        citations=[
            SourceCitation(
                source_document="Legal Metrology (General) Rules, 2011",
                clause_or_section="Seventh Schedule, Heading A, Part I",
                table_or_schedule="Table 1 & Table 2",
                effective_date="2011-04-01",
                legal_origin=LegalOrigin.INDIAN_STATUTORY,
                verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
            ),
            SourceCitation(
                source_document="Legal Metrology (Government Approved Test Centre) Rules, 2013",
                clause_or_section="First Schedule",
                effective_date="2013-04-01",
                legal_origin=LegalOrigin.INDIAN_STATUTORY,
                verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
                notes="Authorizes GATCs to verify non-automatic weighing instruments of Class IIII.",
            ),
            SourceCitation(
                source_document="OIML R 76-1:2006 (E)",
                clause_or_section="Clause 3.2 & Clause 3.5",
                table_or_schedule="Table 3 & Table 6",
                effective_date="2006-10-01",
                legal_origin=LegalOrigin.OIML_TECHNICAL,
                verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
            ),
        ],
        version="2026.1",
    ),
}
