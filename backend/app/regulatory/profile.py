"""
MetrIQ Regulatory Engine - Regulatory Profile & Rule Versioning
===============================================================
Enables data-driven regulatory rule versioning, lifecycle statuses,
state-specific customizations, and audit-friendly explanations without
rewriting calculation engines.

Lifecycle Statuses Supported:
- ACTIVE: Currently verified and legally enforceable standard.
- DRAFT: Proposed / planned regulatory revision not yet in statutory force.
- SUPERSEDED: Historical regulation replaced by an official amendment.
- MANUAL_REVIEW: Circulating reports or draft notices (e.g. reported G.S.R. 568(E))
                 requiring inspector/officer verification before enforcement.

Audit Question Answered:
"Why did the system apply this rule?"
Includes:
- Rule ID
- Source Document
- Clause / Section
- Regulatory Version
- Effective Date
- Statutory Rationale
"""

from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from .models import AccuracyClass, MassUnit
from .mpe_engine import MPEBandDefinition


class ProfileStatus(str, Enum):
    """Lifecycle and verification state of a regulatory profile."""
    ACTIVE = "ACTIVE"
    DRAFT = "DRAFT"
    SUPERSEDED = "SUPERSEDED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


@dataclass
class RuleAuditTrace:
    """
    Audit-friendly explanation answering: 'Why did the system apply this rule?'
    Captures complete statutory provenance and rationale for metrological decisions.
    """
    rule_id: str
    rule_name: str
    source_document: str
    clause: str
    regulatory_version: str
    effective_date: Optional[str]
    applied_to: str
    statutory_rationale: str
    legal_origin: str = "INDIAN_STATUTORY"
    verification_status: str = "ACTIVE"
    is_authoritative: bool = True
    parameters_used: Dict[str, Any] = dc_field(default_factory=dict)
    evaluation_timestamp: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def answer_why(self) -> str:
        """
        Returns a concise, inspector/auditor-friendly explanation answering:
        'Why did the system apply this rule?'
        """
        auth_note = "" if self.is_authoritative else " [WARNING: Non-authoritative / Pending Confirmation]"
        eff_str = self.effective_date or "Statutory baseline"
        return (
            f"Rule {self.rule_id} ('{self.rule_name}'){auth_note} was applied per {self.source_document}, "
            f"Clause '{self.clause}' (Version {self.regulatory_version}, Effective: {eff_str}). "
            f"Applied condition: {self.applied_to}. Rationale: {self.statutory_rationale}"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Returns serializable dictionary."""
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "source_document": self.source_document,
            "clause": self.clause,
            "regulatory_version": self.regulatory_version,
            "effective_date": self.effective_date,
            "applied_to": self.applied_to,
            "statutory_rationale": self.statutory_rationale,
            "legal_origin": self.legal_origin,
            "verification_status": self.verification_status,
            "is_authoritative": self.is_authoritative,
            "parameters_used": self.parameters_used,
            "evaluation_timestamp": self.evaluation_timestamp,
            "audit_explanation": self.answer_why(),
        }


@dataclass
class RegulatoryProfile:
    """
    Complete data-driven regulatory profile.
    Allows changing MPE tables, fees, GATC rules, test weight substitution limits,
    state-specific rules, and re-verification periods without altering code.
    """
    profile_id: str
    jurisdiction: str
    regulation_name: str
    version: str
    effective_from: Optional[str]
    effective_to: Optional[str]
    source: str
    verification_status: ProfileStatus
    rules: Dict[str, Any] = dc_field(default_factory=dict)
    # Configurable data-driven domains
    mpe_tables: Optional[Dict[str, List[Dict[str, Any]]]] = None
    fees: Optional[Dict[str, Any]] = None
    gatc_applicability: Optional[Dict[str, Any]] = None
    test_weight_substitution: Optional[Dict[str, Any]] = None
    state_specific_rules: Optional[Dict[str, Any]] = None
    re_verification_periods: Optional[Dict[str, Any]] = None
    is_authoritative: bool = True
    notes: str = ""
    created_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def is_effective(self, at_date: Optional[str] = None) -> bool:
        """
        Evaluates whether this profile was or is effective on the given date (YYYY-MM-DD).
        If at_date is None, checks against current date.
        """
        is_current = at_date is None
        target_date = at_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # When evaluating current date without an explicit historical timestamp,
        # superseded profiles are never currently active.
        if is_current and self.verification_status == ProfileStatus.SUPERSEDED:
            return False

        if self.effective_from and target_date < self.effective_from:
            return False

        if self.effective_to and target_date > self.effective_to:
            return False

        return True

    def get_mpe_bands_for_class(self, accuracy_class: AccuracyClass) -> Optional[List[MPEBandDefinition]]:
        """
        Retrieves custom MPE band definitions if configured in this profile.
        Returns None to fall back to statutory default table.
        """
        if not self.mpe_tables:
            return None

        class_key = accuracy_class.roman
        raw_bands = self.mpe_tables.get(class_key) or self.mpe_tables.get(accuracy_class.name)
        if not raw_bands:
            return None

        custom_bands: List[MPEBandDefinition] = []
        for b in raw_bands:
            custom_bands.append(
                MPEBandDefinition(
                    band_index=int(b.get("band_index", 1)),
                    min_load_e=Decimal(str(b["min_load_e"])),
                    max_load_e=Decimal(str(b["max_load_e"])),
                    mpe_initial_e=Decimal(str(b["mpe_initial_e"])),
                    mpe_subsequent_e=Decimal(str(b.get("mpe_subsequent_e", 2 * Decimal(str(b["mpe_initial_e"]))))),
                    inclusive_lower=bool(b.get("inclusive_lower", True)),
                    inclusive_upper=bool(b.get("inclusive_upper", True)),
                    description=b.get("description", ""),
                )
            )
        return custom_bands

    def get_max_substitution_ratio(self) -> float:
        """Returns allowed standard test weight substitution ratio (e.g. 0.50 or 0.20)."""
        if self.test_weight_substitution:
            return float(self.test_weight_substitution.get("max_substitution_ratio", 0.50))
        return 0.50

    def get_fee(self, fee_type: str = "VERIFICATION", capacity_kg: Optional[float] = None) -> Optional[float]:
        """Calculates or retrieves statutory fee from data-driven schedule."""
        if not self.fees:
            return None

        # Check direct fee
        if fee_type in self.fees and isinstance(self.fees[fee_type], (int, float)):
            return float(self.fees[fee_type])

        # Check tiered capacity schedule
        schedule = self.fees.get("capacity_tiers", [])
        if capacity_kg is not None and isinstance(schedule, list):
            for tier in schedule:
                max_t = tier.get("max_capacity_kg", float("inf"))
                if capacity_kg <= max_t:
                    return float(tier.get("fee_inr", 0.0))

        return None

    def get_re_verification_period_months(self, instrument_type: str = "COMMERCIAL_NAWI") -> int:
        """Returns re-verification interval in months (e.g. 12 or 24)."""
        if self.re_verification_periods:
            clean_type = instrument_type.upper()
            for k, months in self.re_verification_periods.items():
                if k.upper() in clean_type or clean_type in k.upper():
                    return int(months)
            return int(self.re_verification_periods.get("DEFAULT", 12))
        return 12

    def is_gatc_eligible(
        self, accuracy_class: Union[str, AccuracyClass], max_capacity_kg: float
    ) -> Tuple[bool, str]:
        """
        Evaluates whether GATC testing is legally permissible under this profile.
        Under the Legal Metrology (Government Approved Test Centre) Rules, 2013 (First Schedule):
        - Class III instruments are eligible ONLY up to 150 kg.
        - Class IIII instruments are eligible.
        - Class I and Class II instruments are strictly ineligible and must be verified by State Officers.
        """
        if isinstance(accuracy_class, str):
            accuracy_class = AccuracyClass.from_value(accuracy_class)

        gatc_cfg = self.gatc_applicability or {}
        enabled = gatc_cfg.get("enabled", True)
        if not enabled:
            return False, "GATC verification is disabled under this regulatory profile."

        allowed_classes = gatc_cfg.get("allowed_classes", ["III", "IIII"])
        if accuracy_class.roman not in allowed_classes:
            return (
                False,
                f"Class {accuracy_class.roman} instruments must be tested directly by State Legal Metrology "
                f"Officers; ineligible for GATC under Rule 3 and First Schedule of GATC Rules, 2013.",
            )

        # Enforce statutory 150 kg ceiling for Class III under First Schedule of GATC Rules, 2013
        if accuracy_class == AccuracyClass.CLASS_III:
            class_iii_limit = float(gatc_cfg.get("class_iii_max_capacity_kg", 150.0))
            if max_capacity_kg > class_iii_limit:
                return (
                    False,
                    f"Class III capacity {max_capacity_kg} kg exceeds statutory GATC limit of {class_iii_limit} kg "
                    f"under First Schedule of GATC Rules, 2013; must be verified by State Legal Metrology Officer.",
                )

        max_allowed_cap = float(gatc_cfg.get("max_capacity_kg", 5000.0))
        if max_capacity_kg > max_allowed_cap:
            return (
                False,
                f"Capacity {max_capacity_kg} kg exceeds maximum GATC accredited ceiling of {max_allowed_cap} kg.",
            )

        return True, "Instrument is legally eligible for Government Approved Test Centre (GATC) verification."

    def create_audit_trace(
        self,
        rule_id: str,
        applied_to: str,
        rule_name: Optional[str] = None,
        clause: Optional[str] = None,
        rationale: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> RuleAuditTrace:
        """Constructs an audit-ready trace answering 'Why did the system apply this rule?'"""
        rule_obj = self.rules.get(rule_id, {})
        r_name = rule_name or rule_obj.get("title") or f"Statutory Rule {rule_id}"
        r_clause = clause or rule_obj.get("clause") or "Seventh Schedule / OIML R 76-1"
        r_rationale = rationale or rule_obj.get("description") or f"Enforcing statutory tolerance for {applied_to}."

        return RuleAuditTrace(
            rule_id=rule_id,
            rule_name=r_name,
            source_document=self.source,
            clause=r_clause,
            regulatory_version=self.version,
            effective_date=self.effective_from,
            applied_to=applied_to,
            statutory_rationale=r_rationale,
            legal_origin=self.jurisdiction,
            verification_status=self.verification_status.value,
            is_authoritative=self.is_authoritative,
            parameters_used=parameters or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        """Converts profile to structured dictionary."""
        return {
            "profile_id": self.profile_id,
            "jurisdiction": self.jurisdiction,
            "regulation_name": self.regulation_name,
            "version": self.version,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "source": self.source,
            "verification_status": self.verification_status.value,
            "is_authoritative": self.is_authoritative,
            "rules": self.rules,
            "mpe_tables": self.mpe_tables,
            "fees": self.fees,
            "gatc_applicability": self.gatc_applicability,
            "test_weight_substitution": self.test_weight_substitution,
            "state_specific_rules": self.state_specific_rules,
            "re_verification_periods": self.re_verification_periods,
            "notes": self.notes,
            "created_at": self.created_at,
        }


# =============================================================================
# Pre-Configured Authoritative and Draft Regulatory Profiles
# =============================================================================

DEFAULT_INDIAN_LM_PROFILE = RegulatoryProfile(
    profile_id="IN_LM_2011_ACTIVE",
    jurisdiction="INDIA",
    regulation_name="Legal Metrology (General) Rules, 2011",
    version="2011.1-CURRENT",
    effective_from="2011-04-01",
    effective_to=None,
    source="Ministry of Consumer Affairs, Government of India, Notification G.S.R. 71(E)",
    verification_status=ProfileStatus.ACTIVE,
    is_authoritative=True,
    notes="Authoritative active Indian statutory baseline for Non-Automatic Weighing Instruments.",
    rules={
        "RULE_STATUTORY_MPE": {
            "title": "MPE Tolerance Bands",
            "clause": "Seventh Schedule Table 2",
            "description": "Initial verification errors shall not exceed +/-0.5e, +/-1.0e, or +/-1.5e.",
        },
        "RULE_GATC_ROUTING": {
            "title": "GATC Eligibility",
            "clause": "Rule 3 and First Schedule, GATC Rules 2013",
            "description": "Class III (<= 150 kg) and Class IIII instruments are eligible for GATC verification.",
        },
        "RULE_WEIGHT_SUBSTITUTION": {
            "title": "Test Load Material Substitution",
            "clause": "Sixth Schedule / OIML R 76-1 Clause 3.7.3",
            "description": "Standard test weights must total at least 50% of Max (or 1/3 Max with 3 repeatability weighings).",
        },
    },
    fees={
        "capacity_tiers": [
            {"max_capacity_kg": 50.0, "fee_inr": 200.0},
            {"max_capacity_kg": 500.0, "fee_inr": 500.0},
            {"max_capacity_kg": 5000.0, "fee_inr": 2000.0},
            {"max_capacity_kg": float("inf"), "fee_inr": 5000.0},
        ],
        "model_approval_inr": 25000.0,
    },
    gatc_applicability={
        "enabled": True,
        "allowed_classes": ["III", "IIII"],
        "class_iii_max_capacity_kg": 150.0,
        "max_capacity_kg": 5000.0,
    },
    test_weight_substitution={
        "max_substitution_ratio": 0.50,
        "min_standard_weights_ratio": 0.50,
        "required_repeatability_cycles": 3,
    },
    state_specific_rules={
        "central_stamping_certificate": "Form Schedule III",
        "allows_electronic_sealing": True,
    },
    re_verification_periods={
        "COMMERCIAL_NAWI": 12,
        "INDUSTRIAL_WEIGHBRIDGE": 12,
        "PRECISION_LAB": 24,
        "DEFAULT": 12,
    },
)


DRAFT_GSR_568E_PROFILE = RegulatoryProfile(
    profile_id="IN_LM_2026_GSR568E_DRAFT",
    jurisdiction="INDIA",
    regulation_name="Legal Metrology (General) Fourth Amendment Rules, 2026 (Reported G.S.R. 568(E))",
    version="2026.1-DRAFT",
    effective_from="2026-07-01",
    effective_to=None,
    source="Reported G.S.R. 568(E) [Secondary Industry Report - Verification Pending]",
    verification_status=ProfileStatus.MANUAL_REVIEW,
    is_authoritative=False,
    notes=(
        "REPORTED / UNVERIFIED: Contains circulating industry claims regarding 20% test weight substitution "
        "and ₹50,000 model approval fee. NOT confirmed against the official Gazette of India. "
        "Must be held in MANUAL_REVIEW status and verified by legal metrology officer prior to enforcement."
    ),
    rules={
        "RULE_UNVERIFIED_2026_FEE": {
            "title": "Reported Fee Revision under Fourth Amendment 2026 [UNVERIFIED]",
            "clause": "Reported G.S.R. 568(E) Schedule XII Revision",
            "description": "Reported revision of model approval fee to ₹50,000. Verification pending.",
        },
        "RULE_UNVERIFIED_2026_SUBSTITUTION": {
            "title": "Reported 20% Standard Weight Substitution [UNVERIFIED]",
            "clause": "Reported G.S.R. 568(E) Clause 3",
            "description": "Reported restriction requiring 80% standard weights (max 20% substitution). Verification pending.",
        },
    },
    fees={
        "capacity_tiers": [
            {"max_capacity_kg": 50.0, "fee_inr": 400.0},
            {"max_capacity_kg": 500.0, "fee_inr": 1000.0},
            {"max_capacity_kg": 5000.0, "fee_inr": 4000.0},
            {"max_capacity_kg": float("inf"), "fee_inr": 10000.0},
        ],
        "model_approval_inr": 50000.0,  # Reported ₹50,000 fee
    },
    gatc_applicability={
        "enabled": True,
        "allowed_classes": ["II", "III", "IIII"],
        "max_capacity_kg": 5000.0,
    },
    test_weight_substitution={
        "max_substitution_ratio": 0.20,  # Reported 20% limit
        "min_standard_weights_ratio": 0.80,
        "is_unverified": True,
        "action_required": "Do not enforce without Gazette notification proof.",
    },
    state_specific_rules={
        "central_stamping_certificate": "Form Schedule III (Draft 2026)",
        "qr_code_stamping_mandatory": True,
    },
    re_verification_periods={
        "COMMERCIAL_NAWI": 12,
        "INDUSTRIAL_WEIGHBRIDGE": 6,  # Reported semi-annual check for weighbridges
        "DEFAULT": 12,
    },
)


SUPERSEDED_LM_2009_PROFILE = RegulatoryProfile(
    profile_id="IN_LM_HISTORIC_2009_SUPERSEDED",
    jurisdiction="INDIA",
    regulation_name="Standards of Weights and Measures (General) Rules, 1987 / LM Act 2009 Baseline",
    version="1987.1-SUPERSEDED",
    effective_from="1987-01-01",
    effective_to="2011-03-31",
    source="Standards of Weights and Measures Act, 1976 / Pre-2011 Rules",
    verification_status=ProfileStatus.SUPERSEDED,
    is_authoritative=False,
    notes="Superseded upon notification and enforcement of the Legal Metrology (General) Rules, 2011 on April 1, 2011.",
    rules={},
)


INTERNATIONAL_OIML_PROFILE = RegulatoryProfile(
    profile_id="OIML_R76_2006_ACTIVE",
    jurisdiction="INTERNATIONAL",
    regulation_name="OIML R 76-1: Non-automatic weighing instruments",
    version="2006 (E)",
    effective_from="2006-01-01",
    effective_to=None,
    source="International Organization of Legal Metrology (OIML)",
    verification_status=ProfileStatus.ACTIVE,
    is_authoritative=True,
    notes="Harmonized international technical recommendation for NAWIs.",
    rules={
        "RULE_OIML_MPE": {
            "title": "MPE Table 6",
            "clause": "OIML R 76-1:2006 Clause 3.5 & Table 6",
            "description": "Standard 3-band MPE allocation for Classes I, II, III, and IIII.",
        },
    },
    test_weight_substitution={
        "max_substitution_ratio": 0.50,
        "min_standard_weights_ratio": 0.50,
        "alternative_min_ratio": 0.33,
    },
)


STATE_MAHARASHTRA_PROFILE = RegulatoryProfile(
    profile_id="STATE_MAHARASHTRA_2026",
    jurisdiction="INDIA_MAHARASHTRA",
    regulation_name="Maharashtra Legal Metrology (Enforcement) Rules, 2011 (as amended 2026)",
    version="2026.1",
    effective_from="2026-01-01",
    effective_to=None,
    source="Government of Maharashtra, Food, Civil Supplies and Consumer Protection Department",
    verification_status=ProfileStatus.ACTIVE,
    is_authoritative=True,
    notes="State-specific enforcement profile including local user fees and e-stamping portal integration.",
    fees={
        "capacity_tiers": [
            {"max_capacity_kg": 50.0, "fee_inr": 250.0},
            {"max_capacity_kg": 500.0, "fee_inr": 600.0},
            {"max_capacity_kg": 5000.0, "fee_inr": 2500.0},
            {"max_capacity_kg": float("inf"), "fee_inr": 6000.0},
        ],
        "state_inspection_cess_inr": 100.0,
    },
    state_specific_rules={
        "state_code": "MH",
        "stamping_software_portal": "MahaParikshan Legal Metrology",
        "quarterly_reporting_required": True,
    },
    re_verification_periods={
        "COMMERCIAL_NAWI": 12,
        "INDUSTRIAL_WEIGHBRIDGE": 12,
        "DEFAULT": 12,
    },
)


# =============================================================================
# Regulatory Profile Registry & Version Selection Manager
# =============================================================================

class RegulatoryProfileRegistry:
    """
    Central registry for managing, switching, and selecting regulatory profiles
    by jurisdiction, version, lifecycle status, and effective date.
    """

    def __init__(self):
        self._profiles: Dict[str, RegulatoryProfile] = {}
        self._default_profile_id: str = DEFAULT_INDIAN_LM_PROFILE.profile_id
        self._register_default_profiles()

    def _register_default_profiles(self) -> None:
        """Registers built-in default profiles."""
        for p in (
            DEFAULT_INDIAN_LM_PROFILE,
            DRAFT_GSR_568E_PROFILE,
            SUPERSEDED_LM_2009_PROFILE,
            INTERNATIONAL_OIML_PROFILE,
            STATE_MAHARASHTRA_PROFILE,
        ):
            self.register(p)

    def register(self, profile: RegulatoryProfile) -> None:
        """Registers a regulatory profile."""
        self._profiles[profile.profile_id] = profile

    def get_profile(self, profile_id: str) -> Optional[RegulatoryProfile]:
        """Retrieves profile by its unique ID."""
        return self._profiles.get(profile_id)

    def get_default_profile(self) -> RegulatoryProfile:
        """Returns active default profile."""
        return self._profiles.get(self._default_profile_id, DEFAULT_INDIAN_LM_PROFILE)

    def set_default_profile(self, profile_id: str) -> bool:
        """Sets the active default profile ID."""
        if profile_id in self._profiles:
            self._default_profile_id = profile_id
            return True
        return False

    def select_profile(
        self,
        jurisdiction: str = "INDIA",
        at_date: Optional[str] = None,
        allow_draft: bool = False,
        allow_manual_review: bool = False,
    ) -> RegulatoryProfile:
        """
        Selects the most appropriate regulatory profile based on jurisdiction and effective date.
        Never returns a draft or manual_review profile unless explicitly permitted.
        """
        clean_jurisdiction = str(jurisdiction).upper().strip()

        # Exact match on jurisdiction takes precedence over broad substring match
        exact_profiles = [p for p in self._profiles.values() if p.jurisdiction.upper() == clean_jurisdiction]
        candidates = exact_profiles if exact_profiles else [
            p for p in self._profiles.values() if clean_jurisdiction in p.jurisdiction.upper()
        ]

        matching_profiles: List[RegulatoryProfile] = []
        for p in candidates:
            # Filter by status
            if p.verification_status == ProfileStatus.DRAFT and not allow_draft:
                continue
            if p.verification_status == ProfileStatus.MANUAL_REVIEW and not allow_manual_review:
                continue
            if p.is_effective(at_date):
                matching_profiles.append(p)

        if matching_profiles:
            # Sort by effective_from descending (most recent regulation takes precedence)
            matching_profiles.sort(key=lambda p: p.effective_from or "", reverse=True)
            return matching_profiles[0]

        # Fallback to default
        return self.get_default_profile()

    def list_profiles(
        self,
        status: Optional[Union[str, ProfileStatus]] = None,
        jurisdiction: Optional[str] = None,
    ) -> List[RegulatoryProfile]:
        """Filters profiles by status or jurisdiction."""
        results = list(self._profiles.values())
        if status:
            target_status = status.value if isinstance(status, ProfileStatus) else str(status).upper()
            results = [p for p in results if p.verification_status.value == target_status]
        if jurisdiction:
            target_jur = str(jurisdiction).upper()
            results = [p for p in results if target_jur in p.jurisdiction.upper()]
        return results


# Global singleton instance
PROFILE_REGISTRY = RegulatoryProfileRegistry()
