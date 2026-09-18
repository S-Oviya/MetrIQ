"""
MetrIQ Regulatory Engine - Regulatory Sources & Versioning
Defines statutory standards, jurisdictions, and version registries for OIML R 76
and Indian Legal Metrology (General) Rules.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any


class Jurisdiction(str, Enum):
    INTERNATIONAL = "INTERNATIONAL"
    INDIA = "INDIA"
    CUSTOM = "CUSTOM"


class StandardStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    DRAFT = "DRAFT"


@dataclass
class RegulatorySource:
    """
    Metadata describing a statutory standard, metrology recommendation, or lab rulebook.
    """
    id: str
    name: str
    short_title: str
    jurisdiction: Jurisdiction
    version: str
    publication_year: int
    authority: str
    status: StandardStatus = StandardStatus.ACTIVE
    reference_document: str = ""
    description: str = ""
    default_mpe_multiplier_in_service: float = 2.0
    allows_auxiliary_indicating_class_3: bool = False
    strict_form_of_e: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "short_title": self.short_title,
            "jurisdiction": self.jurisdiction.value,
            "version": self.version,
            "publication_year": self.publication_year,
            "authority": self.authority,
            "status": self.status.value,
            "reference_document": self.reference_document,
            "description": self.description,
            "default_mpe_multiplier_in_service": self.default_mpe_multiplier_in_service,
            "allows_auxiliary_indicating_class_3": self.allows_auxiliary_indicating_class_3,
            "strict_form_of_e": self.strict_form_of_e,
            "metadata": self.metadata,
        }


class RegulatoryRegistry:
    """
    Registry for managing available and active regulatory editions.
    Supports runtime extension and version switching.
    """
    def __init__(self):
        self._sources: Dict[str, RegulatorySource] = {}
        self._register_default_standards()

    def _register_default_standards(self):
        # 1. OIML R 76-1:2006 (E)
        oiml_2006 = RegulatorySource(
            id="OIML_R76_2006",
            name="OIML R 76-1: Non-automatic weighing instruments - Part 1: Metrological and technical requirements - Tests",
            short_title="OIML R 76-1:2006",
            jurisdiction=Jurisdiction.INTERNATIONAL,
            version="2006 (E)",
            publication_year=2006,
            authority="International Organization of Legal Metrology (OIML)",
            status=StandardStatus.ACTIVE,
            reference_document="OIML R 76-1 Edition 2006 (E)",
            description="Harmonized international standard for pattern approval and statutory verification of NAWI.",
            default_mpe_multiplier_in_service=2.0,
            allows_auxiliary_indicating_class_3=False,
            strict_form_of_e=True,
            metadata={
                "table_classification": "Table 3",
                "table_mpe_initial": "Table 6",
                "annex_testing": "Annex A & B",
            }
        )
        self.register(oiml_2006)

        # 2. Indian Legal Metrology (General) Rules, 2011 - Seventh Schedule
        in_lm_2011 = RegulatorySource(
            id="IN_LM_2011",
            name="Legal Metrology (General) Rules, 2011 - Seventh Schedule: Non-Automatic Weighing Instruments",
            short_title="Indian Legal Metrology 2011",
            jurisdiction=Jurisdiction.INDIA,
            version="2011 (as amended)",
            publication_year=2011,
            authority="Department of Consumer Affairs, Government of India",
            status=StandardStatus.ACTIVE,
            reference_document="Seventh Schedule, Heading A: Non-Automatic Weighing Instruments",
            description="Indian statutory regulations governing verification, stamping, and inspection of commercial and industrial weighing machines.",
            default_mpe_multiplier_in_service=2.0,
            allows_auxiliary_indicating_class_3=False,
            strict_form_of_e=True,
            metadata={
                "schedule": "Seventh Schedule, Heading A",
                "gatc_applicable": True,
                "verification_certificate_schedule": "Third Schedule",
            }
        )
        self.register(in_lm_2011)

        # 3. Indian Legal Metrology Amendment Rules 2022
        in_lm_2022 = RegulatorySource(
            id="IN_LM_AMENDMENT_2022",
            name="Legal Metrology (General) Amendment Rules, 2022",
            short_title="Indian LM Amendment 2022",
            jurisdiction=Jurisdiction.INDIA,
            version="2022",
            publication_year=2022,
            authority="Department of Consumer Affairs, Government of India",
            status=StandardStatus.ACTIVE,
            reference_document="GSR Amendment 2022 for digital indications and weighbridges",
            description="Updated provisions for digital readouts, automatic zero tracking, and weighbridge verification stamping.",
            default_mpe_multiplier_in_service=2.0,
            allows_auxiliary_indicating_class_3=False,
            strict_form_of_e=True,
            metadata={
                "weighbridge_stamping_periodicity": "1 year",
                "cctv_integration_notified": True,
            }
        )
        self.register(in_lm_2022)

        # 4. Custom Accredited Lab Specification
        custom_lab = RegulatorySource(
            id="CUSTOM_LAB_SPEC",
            name="Accredited Metrology Laboratory Custom Specification",
            short_title="Custom Lab Spec",
            jurisdiction=Jurisdiction.CUSTOM,
            version="1.0",
            publication_year=2026,
            authority="Internal QA / Calibration Lab",
            status=StandardStatus.ACTIVE,
            reference_document="ISO/IEC 17025 Compliant Internal QA Manual",
            description="Configurable profile allowing tightening of MPE limits or custom repeatability runs for precision calibration.",
            default_mpe_multiplier_in_service=1.5,
            allows_auxiliary_indicating_class_3=False,
            strict_form_of_e=True,
        )
        self.register(custom_lab)

    def register(self, source: RegulatorySource) -> None:
        """Registers or updates a regulatory source."""
        self._sources[source.id] = source

    def get(self, source_id: str) -> Optional[RegulatorySource]:
        """Retrieves a regulatory source by its unique ID."""
        return self._sources.get(source_id)

    def get_or_default(self, source_id: Optional[str]) -> RegulatorySource:
        """Retrieves the source by ID, or falls back to OIML R 76-1:2006."""
        if source_id and source_id in self._sources:
            return self._sources[source_id]
        return self._sources["OIML_R76_2006"]

    def list_all(self) -> List[RegulatorySource]:
        """Returns all registered regulatory sources."""
        return list(self._sources.values())

    def list_ids(self) -> List[str]:
        """Returns list of registered standard IDs."""
        return list(self._sources.keys())


# Singleton instance for convenient global access across MetrIQ
REGULATORY_REGISTRY = RegulatoryRegistry()
