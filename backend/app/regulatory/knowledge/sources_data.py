"""
MetrIQ Regulatory Knowledge Base - Statutory Sources Registry
Defines primary Indian statutory legal sources, verified amendments,
and technical standards (OIML R 76-1 and R 76-2).
"""

from typing import Dict, Any, List
from .schema import LegalOrigin, VerificationStatus, SourceCitation


PRIMARY_STATUTORY_SOURCES: Dict[str, Dict[str, Any]] = {
    "IN_ACT_2009": {
        "id": "IN_ACT_2009",
        "title": "Legal Metrology Act, 2009",
        "official_citation": "Act No. 1 of 2010",
        "authority": "Parliament of India / Ministry of Consumer Affairs, Food & Public Distribution",
        "jurisdiction": "INDIA",
        "enactment_date": "2010-01-13",
        "effective_date": "2011-04-01",
        "legal_origin": LegalOrigin.INDIAN_STATUTORY,
        "verification_status": VerificationStatus.OFFICIALLY_VERIFIED,
        "description": (
            "The overarching statutory enactment establishing standards of weights and measures, "
            "regulating trade and commerce in weights, measures, and other goods, and mandating "
            "statutory verification and model approval in India."
        ),
        "key_sections": {
            "Section 22": "Approval of model of weight or measure by Central Government",
            "Section 24": "Verification and stamping of weight or measure by Legal Metrology Officer",
            "Section 23": "Prohibition of manufacture, repair, or sale without license",
        },
    },

    "IN_GENERAL_RULES_2011": {
        "id": "IN_GENERAL_RULES_2011",
        "title": "Legal Metrology (General) Rules, 2011",
        "official_citation": "G.S.R. 175(E), dated 1st March, 2011",
        "authority": "Department of Consumer Affairs, Central Government of India",
        "jurisdiction": "INDIA",
        "effective_date": "2011-04-01",
        "legal_origin": LegalOrigin.INDIAN_STATUTORY,
        "verification_status": VerificationStatus.OFFICIALLY_VERIFIED,
        "description": (
            "Statutory rules prescribing technical specifications, accuracy classes, verification procedures, "
            "maximum permissible errors (MPE), and test methods for commercial and industrial measuring instruments."
        ),
        "key_schedules": {
            "Seventh Schedule, Heading A": "Specifications and testing for Non-Automatic Weighing Instruments (NAWI)",
            "Seventh Schedule Table 1": "Accuracy classification, scale intervals, and minimum capacity",
            "Seventh Schedule Table 2": "Maximum Permissible Errors on initial verification and inspection",
            "Sixth Schedule": "Specifications for Reference, Secondary, and Working Standards / Test Weights",
            "Third Schedule": "Statutory format for Certificate of Verification",
        },
    },

    "IN_MODEL_APPROVAL_RULES_2011": {
        "id": "IN_MODEL_APPROVAL_RULES_2011",
        "title": "Legal Metrology (Approval of Models) Rules, 2011",
        "official_citation": "G.S.R. 176(E), dated 1st March, 2011",
        "authority": "Department of Consumer Affairs, Central Government of India",
        "jurisdiction": "INDIA",
        "effective_date": "2011-04-01",
        "legal_origin": LegalOrigin.INDIAN_STATUTORY,
        "verification_status": VerificationStatus.OFFICIALLY_VERIFIED,
        "description": (
            "Statutory rules governing the procedure for model evaluation, technical testing by authorized labs "
            "(e.g., RRSL, CSIR-NPL), documentation dossiers, and issuance of model approval certificates."
        ),
    },

    "IN_GATC_RULES_2013": {
        "id": "IN_GATC_RULES_2013",
        "title": "Legal Metrology (Government Approved Test Centre) Rules, 2013",
        "official_citation": "G.S.R. 201(E), dated 1st April, 2013",
        "authority": "Department of Consumer Affairs, Central Government of India",
        "jurisdiction": "INDIA",
        "effective_date": "2013-04-01",
        "legal_origin": LegalOrigin.INDIAN_STATUTORY,
        "verification_status": VerificationStatus.OFFICIALLY_VERIFIED,
        "description": (
            "Statutory framework for approval and delegation of verification activities to Government Approved "
            "Test Centres (GATCs). Authorizes GATCs to verify specified classes of weights and measures, "
            "specifically Class III NAWI up to 150 kg and Class IIII instruments."
        ),
        "key_rules": {
            "Rule 3": "Approval of test centres and statutory verification mandate",
            "First Schedule": "Scope of weights and measures delegated to GATC verification",
        },
    },

    "IN_AMENDMENT_2022": {
        "id": "IN_AMENDMENT_2022",
        "title": "Legal Metrology (General) Amendment Rules, 2022",
        "official_citation": "G.S.R. 490(E), dated 30th June, 2022",
        "authority": "Department of Consumer Affairs, Central Government of India",
        "jurisdiction": "INDIA",
        "effective_date": "2022-07-01",
        "legal_origin": LegalOrigin.INDIAN_STATUTORY,
        "verification_status": VerificationStatus.OFFICIALLY_VERIFIED,
        "description": (
            "Statutory amendment mandating electronic display visibility, digital audit records, "
            "and periodic annual stamping for vehicular weighbridges."
        ),
    },

    "IN_FOURTH_AMENDMENT_2026_UNVERIFIED": {
        "id": "IN_FOURTH_AMENDMENT_2026_UNVERIFIED",
        "title": "Legal Metrology (General) Fourth Amendment Rules, 2026 [Reported / Unverified]",
        "official_citation": "Reported as G.S.R. 568(E) [Verification Pending]",
        "authority": "Central Government of India (Reported)",
        "jurisdiction": "INDIA",
        "effective_date": None,
        "legal_origin": LegalOrigin.INDIAN_STATUTORY,
        "verification_status": VerificationStatus.NOT_OFFICIALLY_VERIFIED,
        "description": (
            "Reported fourth amendment containing proposed fee revisions (e.g. reported ₹50,000) and "
            "a proposed 20% test weight substitution threshold. NOT officially verified in the Gazette of India; "
            "must remain configurable and require regulatory confirmation before enforcement."
        ),
    },

    "OIML_R76_1_2006": {
        "id": "OIML_R76_1_2006",
        "title": "OIML R 76-1: Non-automatic weighing instruments - Part 1: Metrological and technical requirements - Tests",
        "official_citation": "OIML R 76-1 Edition 2006 (E)",
        "authority": "International Organization of Legal Metrology (OIML)",
        "jurisdiction": "INTERNATIONAL",
        "effective_date": "2006-10-01",
        "legal_origin": LegalOrigin.OIML_TECHNICAL,
        "verification_status": VerificationStatus.OFFICIALLY_VERIFIED,
        "description": (
            "International harmonized recommendation specifying metrological characteristics, "
            "technical requirements, and laboratory testing procedures for NAWI pattern evaluation."
        ),
    },

    "OIML_R76_2_2007": {
        "id": "OIML_R76_2_2007",
        "title": "OIML R 76-2: Non-automatic weighing instruments - Part 2: Test report format",
        "official_citation": "OIML R 76-2 Edition 2007 (E)",
        "authority": "International Organization of Legal Metrology (OIML)",
        "jurisdiction": "INTERNATIONAL",
        "effective_date": "2007-05-01",
        "legal_origin": LegalOrigin.PRACTICE_REPORT_FORMAT,
        "verification_status": VerificationStatus.OFFICIALLY_VERIFIED,
        "description": (
            "Standardized test report format and evaluation recording templates. "
            "IMPORTANT: This is an international testing report template and practice format; "
            "it is NOT an Indian statutory requirement under the Legal Metrology Act, 2009."
        ),
    },
}
