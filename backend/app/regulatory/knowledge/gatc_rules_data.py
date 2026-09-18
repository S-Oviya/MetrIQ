"""
MetrIQ Regulatory Knowledge Base - GATC Statutory Routing Rules
Implements verification routing under the Legal Metrology (Government Approved Test Centre)
Rules, 2013 (G.S.R. 201(E), dated 1st April 2013).
"""

from typing import Dict, Any, Tuple
from app.regulatory.models import InstrumentProfile, AccuracyClass, MassUnit, JobType
from .schema import (
    GATCRoutingDecision,
    SourceCitation,
    LegalOrigin,
    VerificationStatus,
    RegulatoryRule,
    RuleCategory,
)


GATC_CITATION = SourceCitation(
    source_document="Legal Metrology (Government Approved Test Centre) Rules, 2013",
    clause_or_section="Rule 3 and First Schedule",
    table_or_schedule="First Schedule: Scope of Weights and Measures for GATC Verification",
    effective_date="2013-04-01",
    legal_origin=LegalOrigin.INDIAN_STATUTORY,
    verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
    notes="Delegates verification of specified weights and measures to GATCs.",
)


GATC_ROUTING_RULE = RegulatoryRule(
    rule_id="RULE_GATC_ROUTING_STATUTORY",
    title="Statutory Verification Routing to GATCs vs State Legal Metrology Officers",
    category=RuleCategory.GATC_ROUTING,
    description=(
        "Under the Legal Metrology (Government Approved Test Centre) Rules, 2013, GATCs are authorized "
        "to verify and stamp specified weights and measures only. For Non-Automatic Weighing Instruments: "
        "1. Class III instruments having capacity up to 150 kg are eligible for GATC verification. "
        "2. Class IIII instruments of all standard commercial capacities are eligible for GATC verification. "
        "3. Class II (High Accuracy) instruments are NOT authorized for GATC verification and must be "
        "routed to the State Legal Metrology Officer. "
        "4. Class I (Special Accuracy) instruments and Class III instruments exceeding 150 kg are NOT "
        "delegated to GATC and must be verified by the State Legal Metrology Officer."
    ),
    citation=GATC_CITATION,
    is_configurable=True,
    requires_manual_review=False,
    parameters={
        "class_iii_max_capacity_kg": 150.0,
        "class_iiii_eligible": True,
        "class_ii_eligible": False,  # Explicitly False under verified 2013 statutory schedule
        "class_i_eligible": False,
        "requires_centre_approval_under_rule_3": True,
    },
    version="2026.1",
)


def evaluate_gatc_routing(
    instrument: InstrumentProfile,
    job_type: JobType = JobType.RE_VERIFICATION,
) -> GATCRoutingDecision:
    """
    Evaluates statutory verification routing for an instrument under the
    Legal Metrology (Government Approved Test Centre) Rules, 2013.

    :param instrument: The instrument metrological profile.
    :param job_type: The verification job type.
    :return: GATCRoutingDecision indicating GATC eligibility, target authority, and reason.
    """
    # Model approval is strictly handled by CSIR-NPL / RRSL under Model Approval Rules
    if job_type == JobType.MODEL_APPROVAL:
        return GATCRoutingDecision(
            eligible_for_gatc=False,
            target_authority="CENTRAL_DIRECTORATE",
            authority_name="Central Directorate / Authorized Laboratories (CSIR-NPL, RRSL)",
            reason=(
                "Pattern Approval (Model Approval) is under the exclusive jurisdiction of the Central Government "
                "under Section 22 of the Legal Metrology Act, 2009 and Legal Metrology (Approval of Models) Rules, 2011. "
                "GATCs have no jurisdiction over model approval."
            ),
            statutory_citation=SourceCitation(
                source_document="Legal Metrology Act, 2009 / Approval of Models Rules, 2011",
                clause_or_section="Section 22 / Rule 3",
                effective_date="2011-04-01",
                legal_origin=LegalOrigin.INDIAN_STATUTORY,
                verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
            ),
            requires_regulatory_confirmation=False,
        )

    # Capacity converted to kg for threshold comparison
    max_kg = MassUnit.convert(instrument.max_capacity, from_unit=instrument.unit, to_unit=MassUnit.KG)
    acc_class = instrument.accuracy_class

    # 1. Class I Check
    if acc_class == AccuracyClass.CLASS_I:
        return GATCRoutingDecision(
            eligible_for_gatc=False,
            target_authority="STATE_LEGAL_METROLOGY_OFFICER",
            authority_name="State Legal Metrology Department / Inspector",
            reason=(
                "Class I (Special Accuracy) instruments are not included in the First Schedule of the GATC Rules, 2013. "
                "Statutory verification must be conducted directly by the State Legal Metrology Officer."
            ),
            statutory_citation=GATC_CITATION,
            requires_regulatory_confirmation=False,
        )

    # 2. Class II Check - STRICTLY PROHIBITED FROM AUTOMATIC GATC ROUTING
    if acc_class == AccuracyClass.CLASS_II:
        return GATCRoutingDecision(
            eligible_for_gatc=False,
            target_authority="STATE_LEGAL_METROLOGY_OFFICER",
            authority_name="State Legal Metrology Department / Inspector",
            reason=(
                "CRITICAL STATUTORY RULE: Class II (High Accuracy) instruments (such as jewelry and bullion balances) "
                "are NOT authorized for GATC verification under the First Schedule of the Legal Metrology (GATC) "
                "Rules, 2013. Verification must be performed directly by the statutory State Legal Metrology Officer."
            ),
            statutory_citation=GATC_CITATION,
            requires_regulatory_confirmation=False,
        )

    # 3. Class III Check - Capacity threshold 150 kg
    if acc_class == AccuracyClass.CLASS_III:
        if max_kg <= 150.0 + 1e-6:
            return GATCRoutingDecision(
                eligible_for_gatc=True,
                target_authority="GATC",
                authority_name="Government Approved Test Centre (GATC)",
                reason=(
                    f"Class III instrument with capacity Max={instrument.max_capacity} {instrument.unit.value} "
                    f"({max_kg:.2f} kg) is <= 150 kg statutory threshold. Fully eligible for verification and stamping "
                    f"by a Government Approved Test Centre under the First Schedule of GATC Rules, 2013."
                ),
                statutory_citation=GATC_CITATION,
                requires_regulatory_confirmation=False,
            )
        else:
            return GATCRoutingDecision(
                eligible_for_gatc=False,
                target_authority="STATE_LEGAL_METROLOGY_OFFICER",
                authority_name="State Legal Metrology Department / Inspector",
                reason=(
                    f"Class III instrument with capacity Max={instrument.max_capacity} {instrument.unit.value} "
                    f"({max_kg:.2f} kg) exceeds the 150 kg statutory threshold for GATC verification. "
                    f"Must be verified and stamped directly by the State Legal Metrology Officer (e.g. at site/weighbridge)."
                ),
                statutory_citation=GATC_CITATION,
                requires_regulatory_confirmation=False,
            )

    # 4. Class IIII Check - Eligible for GATC
    if acc_class == AccuracyClass.CLASS_IIII:
        return GATCRoutingDecision(
            eligible_for_gatc=True,
            target_authority="GATC",
            authority_name="Government Approved Test Centre (GATC)",
            reason=(
                "Class IIII (Ordinary Accuracy) instruments are authorized for GATC verification under the "
                "First Schedule of the Legal Metrology (GATC) Rules, 2013, subject to available standard test weights."
            ),
            statutory_citation=GATC_CITATION,
            requires_regulatory_confirmation=False,
        )

    # Fallback
    return GATCRoutingDecision(
        eligible_for_gatc=False,
        target_authority="STATE_LEGAL_METROLOGY_OFFICER",
        authority_name="State Legal Metrology Department",
        reason="Instrument parameters require inspection by the State Legal Metrology Department.",
        statutory_citation=GATC_CITATION,
        requires_regulatory_confirmation=True,
    )
