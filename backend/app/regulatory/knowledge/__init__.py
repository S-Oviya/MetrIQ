"""
MetrIQ Regulatory Knowledge Base Package
Provides structured, versioned statutory metrological data for Indian Legal Metrology
and OIML R 76-1/2 recommendations.
"""

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
from .knowledge_base import RegulatoryKnowledgeBase, KNOWLEDGE_BASE

__all__ = [
    "LegalOrigin",
    "VerificationStatus",
    "RuleCategory",
    "SourceCitation",
    "RegulatoryRule",
    "AccuracyClassDefinition",
    "GATCRoutingDecision",
    "PRIMARY_STATUTORY_SOURCES",
    "CLASS_DEFINITIONS",
    "METROLOGICAL_RULES",
    "AMENDMENT_RULES",
    "GATC_ROUTING_RULE",
    "evaluate_gatc_routing",
    "RegulatoryKnowledgeBase",
    "KNOWLEDGE_BASE",
]
