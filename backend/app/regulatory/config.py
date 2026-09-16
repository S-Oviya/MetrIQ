"""
MetrIQ Regulatory Engine - Regulatory Configuration & Manual Review Checklists
Defines configurable parameters, laboratory overrides, and statutory manual review checklists
for Legal Metrology Officers and testing technicians.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from enum import Enum


@dataclass
class RegulatoryConfig:
    """
    Configurable regulatory parameters for the MetrIQ Regulatory Engine.
    Allows testing laboratories and state legal metrology jurisdictions to adapt rules.
    """
    # MPE settings
    in_service_mpe_multiplier: float = 2.0
    post_repair_uses_initial_mpe: bool = False  # Indian LM: Some states require initial MPE after major repair
    retest_uses_initial_mpe: bool = True

    # Weighing test plan configuration
    min_weighing_points_count: int = 5         # Minimum number of test load steps (typically 5 to 10)
    include_zero_test_point: bool = True
    include_min_capacity_point: bool = True
    include_half_max_point: bool = True
    include_max_capacity_point: bool = True

    # Eccentricity settings
    eccentricity_load_ratio: float = 1.0 / 3.0 # Default 1/3 Max for standard platter
    use_n_minus_one_rule_for_large_platforms: bool = True # 1/(N-1) Max for platforms with N > 4 supports

    # Repeatability settings
    repeatability_cycles_verification: int = 3 # 3 weighings for statutory verification
    repeatability_cycles_approval: int = 10     # 10 weighings (or 6 for Class I/II) for pattern approval
    repeatability_load_1_ratio: float = 0.5    # ~50% Max
    repeatability_load_2_ratio: float = 1.0    # ~100% Max (or 0.8 Max)

    # Discrimination settings
    discrimination_load_factor: float = 1.4    # 1.4d per OIML R 76 Clause A.4.8

    # Tolerance calculation
    strict_rounding: bool = True
    state_jurisdiction: Optional[str] = None   # State-specific legal metrology department (e.g. "TN", "MH", "DL")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "in_service_mpe_multiplier": self.in_service_mpe_multiplier,
            "post_repair_uses_initial_mpe": self.post_repair_uses_initial_mpe,
            "retest_uses_initial_mpe": self.retest_uses_initial_mpe,
            "min_weighing_points_count": self.min_weighing_points_count,
            "eccentricity_load_ratio": self.eccentricity_load_ratio,
            "repeatability_cycles_verification": self.repeatability_cycles_verification,
            "repeatability_cycles_approval": self.repeatability_cycles_approval,
            "discrimination_load_factor": self.discrimination_load_factor,
            "strict_rounding": self.strict_rounding,
            "state_jurisdiction": self.state_jurisdiction,
        }


@dataclass
class ManualReviewItem:
    """
    Physical examination or statutory compliance item requiring human verification.
    These cannot be determined purely mathematically and require inspector judgment.
    """
    item_id: str
    category: str
    title: str
    description: str
    regulatory_reference: str
    mandatory: bool = True
    expected_standard: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "regulatory_reference": self.regulatory_reference,
            "mandatory": self.mandatory,
            "expected_standard": self.expected_standard,
        }


# Standard statutory manual review checklists per OIML R 76-1 & Indian Legal Metrology Rules 2011
STANDARD_MANUAL_REVIEW_ITEMS: List[ManualReviewItem] = [
    ManualReviewItem(
        item_id="REV_INSCRIPTION_LEGIBILITY",
        category="MARKINGS",
        title="Statutory Markings & Inscription Plate Legibility",
        description="Verify that Max, Min, e, d (if applicable), Accuracy Class mark, Serial Number, and Manufacturer Name are clearly, indelibly stamped or printed on the nameplate.",
        regulatory_reference="OIML R 76-1:2006 Clause 7.1 / IN LM 2011 Seventh Schedule Part I Clause 6",
        mandatory=True,
        expected_standard="Markings must be indelible, distinct, and visible without tool disassembly.",
    ),
    ManualReviewItem(
        item_id="REV_MODEL_APPROVAL_SIGN",
        category="LEGAL_AUTHORIZATION",
        title="Model Approval Number & Verification Mark",
        description="Verify that the instrument bears an authentic Model Approval number issued by the Central Government / Competent Metrological Authority.",
        regulatory_reference="Indian Legal Metrology Act, 2009 Section 22 / OIML R 76-1 Clause 7.1",
        mandatory=True,
        expected_standard="Valid model approval number matching central government gazette notification.",
    ),
    ManualReviewItem(
        item_id="REV_SEALING_PROVISION",
        category="ANTI_TAMPER",
        title="Physical Sealing Provisions & Lead Stamping Space",
        description="Inspect physical lead/wire sealing provisions, security stickers, or calibration access switches to ensure metrological adjustments cannot be made without breaking the seal.",
        regulatory_reference="OIML R 76-1:2006 Clause 4.1.2.4 / IN LM 2011 Sixth Schedule",
        mandatory=True,
        expected_standard="Seals must secure housing or calibration jumper; stamping plug must accept statutory verification punch.",
    ),
    ManualReviewItem(
        item_id="REV_LEVEL_INDICATOR",
        category="INSTALLATION",
        title="Level Indicator Alignment & Foundation Stability",
        description="Check that the spirit level bubble is centered within the central circle. Confirm that the instrument rests on a firm, stable base free from excessive external vibration.",
        regulatory_reference="OIML R 76-1:2006 Clause 3.9.1.1",
        mandatory=True,
        expected_standard="Level bubble must be centered within reference ring; leveling feet must lock firmly.",
    ),
    ManualReviewItem(
        item_id="REV_ENVIRONMENT_SUITABILITY",
        category="ENVIRONMENT",
        title="Environmental Conditions & Draft Shielding",
        description="Verify that ambient room temperature, relative humidity, and air draft are within the manufacturer's rated operating limits. Ensure analytical balances have drafts shields closed.",
        regulatory_reference="OIML R 76-1:2006 Clause 3.9.2 / Annex A.1",
        mandatory=True,
        expected_standard="Ambient temperature within specified nameplate limits; no direct drafts or direct radiant heat.",
    ),
    ManualReviewItem(
        item_id="REV_SOFTWARE_AUDIT_TRAIL",
        category="SOFTWARE_INTEGRITY",
        title="Software Event Counter / Calibration Audit Trail Check",
        description="For electronic instruments with audit trails, verify that the event counter number displayed on power-up or menu matches the value recorded on the previous verification certificate.",
        regulatory_reference="OIML R 76-1:2006 Clause 5.5 / WELMEC 7.2",
        mandatory=False,
        expected_standard="Current event counter matches prior statutory certificate; no unauthorized calibration interventions.",
    ),
]


def get_default_config() -> RegulatoryConfig:
    """Returns the default regulatory engine configuration."""
    return RegulatoryConfig()


def get_manual_review_checklist(
    instrument: Optional[Any] = None,
    job_type: Optional[Any] = None,
) -> List[ManualReviewItem]:
    """Returns the applicable manual review checklist items."""
    # Could filter or append items depending on instrument attributes (e.g. software)
    items = list(STANDARD_MANUAL_REVIEW_ITEMS)
    return items
