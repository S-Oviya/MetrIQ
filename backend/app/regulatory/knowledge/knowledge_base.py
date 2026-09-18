"""
MetrIQ Regulatory Knowledge Base - Central Query Engine & Knowledge Manager
Provides a single, structured, versioned query interface for the rest of the backend
to access Indian statutory requirements, OIML technical standards, accuracy class definitions,
GATC routing decisions, and unverified amendments.
"""

from typing import Dict, List, Optional, Any
from app.regulatory.models import AccuracyClass, InstrumentProfile, JobType, MassUnit

from .schema import (
    LegalOrigin,
    VerificationStatus,
    RuleCategory,
    SourceCitation,
    RegulatoryRule,
    AccuracyClassDefinition,
    GATCRoutingDecision,
)
from .sources_data import PRIMARY_STATUTORY_SOURCES
from .classes_data import CLASS_DEFINITIONS
from .rules_data import METROLOGICAL_RULES
from .gatc_rules_data import evaluate_gatc_routing, GATC_ROUTING_RULE
from .amendments_data import AMENDMENT_RULES


class RegulatoryKnowledgeBase:
    """
    Central repository of structured metrological regulations for MetrIQ.
    Distinguishes Indian statutory requirements, OIML technical recommendations,
    practice report formats, configurable parameters, and unverified amendments.
    """

    VERSION = "2026.1-IN-OIML"
    RELEASE_DATE = "2026-03-01"

    def __init__(self):
        self._sources = dict(PRIMARY_STATUTORY_SOURCES)
        self._classes = dict(CLASS_DEFINITIONS)
        self._rules = dict(METROLOGICAL_RULES)
        self._amendments = dict(AMENDMENT_RULES)
        # Include GATC routing rule in master rules collection
        self._rules[GATC_ROUTING_RULE.rule_id] = GATC_ROUTING_RULE

    # -------------------------------------------------------------------------
    # Accuracy Class Queries
    # -------------------------------------------------------------------------
    def get_accuracy_class_definition(self, accuracy_class: AccuracyClass) -> Optional[AccuracyClassDefinition]:
        """Retrieves structured definition, e ranges, n limits, and MPE steps for an accuracy class."""
        return self._classes.get(accuracy_class)

    def list_accuracy_classes(self) -> List[AccuracyClassDefinition]:
        """Returns all 4 defined accuracy classes (I, II, III, IIII)."""
        return list(self._classes.values())

    # -------------------------------------------------------------------------
    # Rule Queries by Category and Provenance
    # -------------------------------------------------------------------------
    def get_rule(self, rule_id: str) -> Optional[RegulatoryRule]:
        """Retrieves a specific metrological rule by ID."""
        if rule_id in self._rules:
            return self._rules[rule_id]
        if rule_id in self._amendments:
            return self._amendments[rule_id]
        return None

    def get_rules_by_category(self, category: RuleCategory) -> List[RegulatoryRule]:
        """Returns all rules within a specific metrological category."""
        all_rules = list(self._rules.values()) + list(self._amendments.values())
        return [r for r in all_rules if r.category == category]

    def get_rules_by_origin(self, origin: LegalOrigin) -> List[RegulatoryRule]:
        """Filters rules by legal provenance (e.g. INDIAN_STATUTORY vs OIML_TECHNICAL)."""
        all_rules = list(self._rules.values()) + list(self._amendments.values())
        return [r for r in all_rules if r.citation.legal_origin == origin]

    def get_indian_statutory_rules(self) -> List[RegulatoryRule]:
        """Returns only rules that carry statutory legal force in India."""
        return self.get_rules_by_origin(LegalOrigin.INDIAN_STATUTORY)

    def get_oiml_technical_rules(self) -> List[RegulatoryRule]:
        """Returns technical requirements derived from international OIML recommendations."""
        return self.get_rules_by_origin(LegalOrigin.OIML_TECHNICAL)

    def get_practice_report_formats(self) -> List[RegulatoryRule]:
        """Returns standardized testing/reporting templates (e.g. OIML R 76-2)."""
        return self.get_rules_by_origin(LegalOrigin.PRACTICE_REPORT_FORMAT)

    def get_unverified_rules(self) -> List[RegulatoryRule]:
        """Returns rules that are reported or draft and NOT yet officially verified."""
        all_rules = list(self._rules.values()) + list(self._amendments.values())
        return [r for r in all_rules if r.citation.verification_status == VerificationStatus.NOT_OFFICIALLY_VERIFIED]

    def get_configurable_rules(self) -> List[RegulatoryRule]:
        """Returns rules with configurable parameters that testing labs or states can adjust."""
        all_rules = list(self._rules.values()) + list(self._amendments.values())
        return [r for r in all_rules if r.is_configurable]

    def get_manual_review_rules(self) -> List[RegulatoryRule]:
        """Returns rules requiring physical verification or inspector discretion."""
        all_rules = list(self._rules.values()) + list(self._amendments.values())
        return [r for r in all_rules if r.requires_manual_review]

    # -------------------------------------------------------------------------
    # GATC Verification Routing Engine
    # -------------------------------------------------------------------------
    def evaluate_gatc_routing(
        self,
        instrument: InstrumentProfile,
        job_type: JobType = JobType.RE_VERIFICATION,
    ) -> GATCRoutingDecision:
        """
        Evaluates whether an instrument is eligible for GATC verification under the
        Legal Metrology (Government Approved Test Centre) Rules, 2013:
        - Class III up to 150 kg: ELIGIBLE
        - Class III above 150 kg: NOT ELIGIBLE (Routed to State LMO)
        - Class IIII: ELIGIBLE
        - Class II: NOT ELIGIBLE (Routed to State LMO)
        - Class I: NOT ELIGIBLE
        """
        return evaluate_gatc_routing(instrument, job_type=job_type)

    # -------------------------------------------------------------------------
    # Test Weights Specification
    # -------------------------------------------------------------------------
    def get_test_weight_requirement(self, instrument: InstrumentProfile) -> Dict[str, Any]:
        """
        Returns statutory test weight class and accuracy tolerance requirements for an instrument
        under the Sixth Schedule of Indian LM Rules and OIML R 76-1 Clause 3.7.1.
        """
        rule = self._rules.get("RULE_TEST_WEIGHT_ACCURACY")
        params = rule.parameters if rule else {}
        class_mapping = params.get("standard_class_mapping", {})
        allowed_classes = class_mapping.get(instrument.accuracy_class.value, ["M1"])

        return {
            "instrument_accuracy_class": instrument.accuracy_class.value,
            "recommended_test_weight_classes": allowed_classes,
            "max_weight_error_ratio": "1/3 of instrument MPE for the applied load",
            "statutory_citation": rule.citation.to_dict() if rule else None,
            "substitution_rules": {
                "verified_standard_substitution_limit": "Up to 50% Max with standard weights (OIML Clause 3.7.3)",
                "reported_2026_draft_limit": "Reported 20% substitution [NOT OFFICIALLY VERIFIED - Require confirmation]",
            },
        }

    # -------------------------------------------------------------------------
    # Master Sources and Metadata
    # -------------------------------------------------------------------------
    def list_sources(self) -> List[Dict[str, Any]]:
        """Lists all registered statutory and technical source documents."""
        return list(self._sources.values())

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the complete knowledge base to a dictionary."""
        return {
            "version": self.VERSION,
            "release_date": self.RELEASE_DATE,
            "accuracy_classes": {k.value: v.to_dict() for k, v in self._classes.items()},
            "rules_count": len(self._rules),
            "unverified_amendments_count": len(self._amendments),
            "sources_count": len(self._sources),
        }


# Singleton instance for convenient global access across MetrIQ backend
KNOWLEDGE_BASE = RegulatoryKnowledgeBase()
