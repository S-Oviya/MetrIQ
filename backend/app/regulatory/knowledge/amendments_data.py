"""
MetrIQ Regulatory Knowledge Base - Pending & Unverified Amendments
Captures circulating draft proposals and reported gazette amendments, specifically
G.S.R. 568(E) / Fourth Amendment 2026. Strictly tagged as unverified with configurable parameters.
"""

from typing import Dict, Any, Optional
from .schema import (
    RegulatoryRule,
    RuleCategory,
    SourceCitation,
    LegalOrigin,
    VerificationStatus,
)


AMENDMENT_2026_CITATION = SourceCitation(
    source_document="Legal Metrology (General) Fourth Amendment Rules, 2026 [Reported]",
    clause_or_section="Reported G.S.R. 568(E) [Verification Pending]",
    table_or_schedule="Schedule Revision (Reported)",
    effective_date=None,
    legal_origin=LegalOrigin.INDIAN_STATUTORY,
    verification_status=VerificationStatus.NOT_OFFICIALLY_VERIFIED,
    notes=(
        "REPORTED / UNVERIFIED AMENDMENT: This notification is circulating in industry reports but has "
        "NOT been officially verified in the official Gazette of India in our current knowledge base. "
        "Reported values (such as ₹50,000 fee and 20% substitution) MUST NOT be treated as authoritative "
        "or legally enforceable until confirmed by the Central Directorate of Legal Metrology."
    ),
)


AMENDMENT_RULES: Dict[str, RegulatoryRule] = {
    # 1. REPORTED FEE REVISION (UNVERIFIED)
    "RULE_UNVERIFIED_2026_FEE": RegulatoryRule(
        rule_id="RULE_UNVERIFIED_2026_FEE",
        title="Reported Fee Revision under Fourth Amendment 2026 [NOT OFFICIALLY VERIFIED]",
        category=RuleCategory.STATUTORY_FEES_AND_PROCEDURES,
        description=(
            "Industry reports suggest a revision of verification / model approval fees (e.g. ₹50,000). "
            "STATUS: NOT OFFICIALLY VERIFIED. This value is NOT hard-coded as authoritative and must be "
            "verified by the user or testing authority against the official Gazette before levying fees."
        ),
        citation=AMENDMENT_2026_CITATION,
        is_configurable=True,
        requires_manual_review=True,
        requires_regulatory_confirmation=True,
        parameters={
            "reported_fee_inr": 50000.0,
            "is_authoritative": False,
            "verification_status": VerificationStatus.NOT_OFFICIALLY_VERIFIED.value,
            "action_required": "Confirm with official Gazette of India publication or State Controller.",
            "statutory_fallback_fee_source": "Legal Metrology (General) Rules, 2011 Schedule XII (Verified)",
        },
        version="2026.1-DRAFT",
    ),

    # 2. REPORTED TEST LOAD SUBSTITUTION REQUIREMENT (UNVERIFIED)
    "RULE_UNVERIFIED_2026_SUBSTITUTION": RegulatoryRule(
        rule_id="RULE_UNVERIFIED_2026_SUBSTITUTION",
        title="Reported 20% Standard Weight Substitution Requirement [NOT OFFICIALLY VERIFIED]",
        category=RuleCategory.TEST_WEIGHTS,
        description=(
            "Reports suggest a proposed amendment restricting material substitution (using ballast / dummy weights) "
            "to 20% of Max capacity, requiring 80% standard test weights. "
            "STATUS: NOT OFFICIALLY VERIFIED. OIML R 76-1 Clause 3.7.3 and current verified Indian practice allow "
            "substitution up to 50% Max (or 1/3 Max with 3 repeatability runs). This 20% threshold must remain "
            "configurable and requires formal regulatory confirmation."
        ),
        citation=AMENDMENT_2026_CITATION,
        is_configurable=True,
        requires_manual_review=True,
        requires_regulatory_confirmation=True,
        parameters={
            "reported_substitution_ratio": 0.20,      # Reported 20% substitution limit
            "verified_standard_substitution_ratio": 0.50, # Current standard 50% substitution limit (OIML Clause 3.7.3)
            "is_authoritative": False,
            "verification_status": VerificationStatus.NOT_OFFICIALLY_VERIFIED.value,
            "action_required": "Do not enforce 20% limit as mandatory without Gazette notification proof.",
        },
        version="2026.1-DRAFT",
    ),
}
