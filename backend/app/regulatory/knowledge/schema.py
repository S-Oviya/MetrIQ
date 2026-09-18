"""
MetrIQ Regulatory Knowledge Base - Schema Definitions
Defines strongly-typed data structures, provenance metadata, legal origin tags,
and verification statuses for Indian Legal Metrology and OIML R 76 rules.
"""

from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import Dict, List, Any, Optional
from app.regulatory.models import AccuracyClass, MassUnit


class LegalOrigin(str, Enum):
    """
    Distinguishes legal and normative authority of a metrological rule.
    Critical for distinguishing Indian statutory requirements from international technical standards.
    """
    INDIAN_STATUTORY = "INDIAN_STATUTORY"           # Mandatory statutory law in India (Act & Rules)
    OIML_TECHNICAL = "OIML_TECHNICAL"               # International technical recommendation (OIML R 76-1)
    PRACTICE_REPORT_FORMAT = "PRACTICE_REPORT_FORMAT" # Testing and reporting layout (OIML R 76-2, GATC formats)
    LAB_CONFIGURABLE = "LAB_CONFIGURABLE"           # Laboratory operating procedure or custom profile


class VerificationStatus(str, Enum):
    """
    Provenance verification state of the regulatory rule.
    Prevents unverified gazettes or reported amendments from being treated as authoritative law.
    """
    OFFICIALLY_VERIFIED = "OFFICIALLY_VERIFIED"               # Confirmed against official Gazette / OIML text
    NOT_OFFICIALLY_VERIFIED = "NOT_OFFICIALLY_VERIFIED"       # Circulating report / draft, not legally confirmed
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"             # Requires legal metrology officer review
    SUPERSEDED = "SUPERSEDED"                                 # Former rule replaced by amendment


class RuleCategory(str, Enum):
    """Major metrological rule domains."""
    ACCURACY_CLASS = "ACCURACY_CLASS"
    SCALE_INTERVAL_AND_CAPACITY = "SCALE_INTERVAL_AND_CAPACITY"
    MPE_INITIAL = "MPE_INITIAL"
    MPE_SUBSEQUENT = "MPE_SUBSEQUENT"
    TEST_WEIGHTS = "TEST_WEIGHTS"
    ECCENTRICITY = "ECCENTRICITY"
    REPEATABILITY = "REPEATABILITY"
    DISCRIMINATION = "DISCRIMINATION"
    TEMPERATURE_DRIFT = "TEMPERATURE_DRIFT"
    CREEP_AND_ZERO_RETURN = "CREEP_AND_ZERO_RETURN"
    ZERO_SETTING = "ZERO_SETTING"
    TARE = "TARE"
    MULTI_RANGE = "MULTI_RANGE"
    MULTI_INTERVAL = "MULTI_INTERVAL"
    ELECTRONIC_INSTRUMENT = "ELECTRONIC_INSTRUMENT"
    GATC_ROUTING = "GATC_ROUTING"
    STATUTORY_FEES_AND_PROCEDURES = "STATUTORY_FEES_AND_PROCEDURES"
    MANUAL_REVIEW = "MANUAL_REVIEW"


@dataclass
class SourceCitation:
    """
    Detailed provenance metadata for statutory and technical rules.
    """
    source_document: str
    clause_or_section: str
    table_or_schedule: Optional[str] = None
    effective_date: Optional[str] = None
    legal_origin: LegalOrigin = LegalOrigin.INDIAN_STATUTORY
    verification_status: VerificationStatus = VerificationStatus.OFFICIALLY_VERIFIED
    notes: str = ""

    @property
    def is_indian_statutory(self) -> bool:
        """True only if the source is an Indian statutory law/rule."""
        return self.legal_origin == LegalOrigin.INDIAN_STATUTORY

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_document": self.source_document,
            "clause_or_section": self.clause_or_section,
            "table_or_schedule": self.table_or_schedule,
            "effective_date": self.effective_date,
            "legal_origin": self.legal_origin.value,
            "is_indian_statutory": self.is_indian_statutory,
            "verification_status": self.verification_status.value,
            "notes": self.notes,
        }


@dataclass
class RegulatoryRule:
    """
    A single, modular metrological compliance rule in the MetrIQ Knowledge Base.
    """
    rule_id: str
    title: str
    category: RuleCategory
    description: str
    citation: SourceCitation
    is_configurable: bool = False
    requires_manual_review: bool = False
    requires_regulatory_confirmation: bool = False
    parameters: Dict[str, Any] = dc_field(default_factory=dict)
    version: str = "2026.1"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "category": self.category.value,
            "description": self.description,
            "citation": self.citation.to_dict(),
            "is_configurable": self.is_configurable,
            "requires_manual_review": self.requires_manual_review,
            "requires_regulatory_confirmation": self.requires_regulatory_confirmation,
            "parameters": self.parameters,
            "version": self.version,
        }


@dataclass
class AccuracyClassDefinition:
    """
    Structured definition of a Non-Automatic Weighing Instrument Accuracy Class (I, II, III, IIII).
    """
    accuracy_class: AccuracyClass
    display_name: str
    description: str
    e_ranges: List[Dict[str, Any]]
    mpe_thresholds_initial: List[Dict[str, Any]]
    mpe_thresholds_subsequent: List[Dict[str, Any]]
    applicability_rules: List[str]
    citations: List[SourceCitation]
    version: str = "2026.1"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accuracy_class": self.accuracy_class.value,
            "display_name": self.display_name,
            "description": self.description,
            "e_ranges": self.e_ranges,
            "mpe_thresholds_initial": self.mpe_thresholds_initial,
            "mpe_thresholds_subsequent": self.mpe_thresholds_subsequent,
            "applicability_rules": self.applicability_rules,
            "citations": [c.to_dict() for c in self.citations],
            "version": self.version,
        }


@dataclass
class GATCRoutingDecision:
    """
    Decision container for Government Approved Test Centre (GATC) verification routing
    under the Legal Metrology (Government Approved Test Centre) Rules, 2013.
    """
    eligible_for_gatc: bool
    target_authority: str               # "GATC", "STATE_LEGAL_METROLOGY_OFFICER", "CENTRAL_DIRECTORATE"
    authority_name: str
    reason: str
    statutory_citation: SourceCitation
    requires_regulatory_confirmation: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eligible_for_gatc": self.eligible_for_gatc,
            "target_authority": self.target_authority,
            "authority_name": self.authority_name,
            "reason": self.reason,
            "statutory_citation": self.statutory_citation.to_dict(),
            "requires_regulatory_confirmation": self.requires_regulatory_confirmation,
        }
