"""
MetrIQ Job & Verification Location Integration — Person 3
=========================================================
Implements statutory verification location assignment and GATC routing integration:
    RegulatoryRoutingService (Consumes Person 2's statutory GATC rules)
                ↓
    JobLocationService (Resolves locations, testing centres, installation premises, and audit metadata)

Statutory Compliance Rules:
1. P3 MUST CONSUME P2's GATC applicability/routing result directly.
2. P3 does NOT recreate GATC regulatory rules or make independent metrological decisions.
3. Class II (High Accuracy) is NEVER assumed to be GATC eligible; statutory verification
   is performed directly by the State Legal Metrology Officer.
4. Class III <= 150 kg: Authorized for GATC verification.
5. Class III > 150 kg: Exceeds statutory threshold; routed to State Legal Metrology Officer.
6. Class IIII: Authorized for GATC verification across standard commercial capacities.
7. Unverified 2026 secondary claims (e.g. reported G.S.R. 568(E)) are flagged for manual review.
"""

from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional, Tuple, Union

# Person 2 Regulatory Engine Imports (Read-Only Consumption)
from app.regulatory.knowledge.gatc_rules_data import evaluate_gatc_routing
from app.regulatory.knowledge.schema import GATCRoutingDecision
from app.regulatory.models import (
    AccuracyClass,
    InstrumentProfile,
    MassUnit,
    JobType as P2JobType,
)
from app.regulatory.profile import PROFILE_REGISTRY, ProfileStatus

# Person 3 Domain Models
from app.instruments.models import Instrument, VerificationReason
from .models import JobType, StatutoryRoutingInfo, TestJob, VerificationLocationType


@dataclass
class RegulatoryRoutingResult:
    """
    Structured statutory routing decision consumed directly from Person 2.
    Contains complete regulatory authority assignment, statutory rule references,
    and manual review flags without duplicating regulatory engine rules.
    """
    eligible_for_gatc: bool
    target_authority: str               # "GATC", "STATE_LEGAL_METROLOGY_OFFICER", "CENTRAL_DIRECTORATE"
    authority_name: str
    reason: str
    statutory_citation: Dict[str, Any]
    regulatory_rule_reference: str
    regulatory_profile_id: str
    regulatory_version: str
    manual_review_flag: bool = False
    manual_review_reason: Optional[str] = None
    p2_decision: Optional[GATCRoutingDecision] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eligible_for_gatc": self.eligible_for_gatc,
            "target_authority": self.target_authority,
            "authority_name": self.authority_name,
            "reason": self.reason,
            "statutory_citation": self.statutory_citation,
            "regulatory_rule_reference": self.regulatory_rule_reference,
            "regulatory_profile_id": self.regulatory_profile_id,
            "regulatory_version": self.regulatory_version,
            "manual_review_flag": self.manual_review_flag,
            "manual_review_reason": self.manual_review_reason,
        }


@dataclass
class JobLocationRoutingResult:
    """
    Complete resolved verification location, testing centre, and statutory routing
    metadata for a Test Job.
    """
    verification_location_type: str     # GATC_CENTRE, STATE_LABORATORY, ON_SITE_INSTALLATION, etc.
    laboratory: str
    test_centre: str
    testing_centre_id: Optional[str]
    gatc_reference: Optional[str]
    installation_location: Optional[Dict[str, Any]]
    reason_for_verification: str
    routing_decision: str
    regulatory_rule_reference: str
    regulatory_profile_id: str
    regulatory_version: str
    manual_review_flag: bool
    manual_review_reason: Optional[str]
    routing_result: RegulatoryRoutingResult

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verification_location_type": self.verification_location_type,
            "laboratory": self.laboratory,
            "test_centre": self.test_centre,
            "testing_centre_id": self.testing_centre_id,
            "gatc_reference": self.gatc_reference,
            "installation_location": self.installation_location,
            "reason_for_verification": self.reason_for_verification,
            "routing_decision": self.routing_decision,
            "regulatory_rule_reference": self.regulatory_rule_reference,
            "regulatory_profile_id": self.regulatory_profile_id,
            "regulatory_version": self.regulatory_version,
            "manual_review_flag": self.manual_review_flag,
            "manual_review_reason": self.manual_review_reason,
            "routing_result": self.routing_result.to_dict(),
        }


# =============================================================================
# 1. Regulatory Routing Service (Consumes Person 2)
# =============================================================================

class RegulatoryRoutingService:
    """
    Statutory Routing Adapter that consumes Person 2's GATC evaluation engine
    and Profile Registry without duplicating metrological rules.
    """

    def evaluate_routing(
        self,
        instrument: Union[Instrument, InstrumentProfile, Dict[str, Any]],
        job_type: Union[str, JobType] = JobType.RE_VERIFICATION,
        profile_id: Optional[str] = None,
    ) -> RegulatoryRoutingResult:
        """
        Calls Person 2's evaluate_gatc_routing and attaches profile/citation provenance.
        """
        # 1. Standardize Job Type to Person 2 enum
        j_type = JobType.from_value(job_type) if not isinstance(job_type, JobType) else job_type
        p2_job_type = j_type.to_p2_job_type()

        # 2. Build Person 2 InstrumentProfile
        inst_profile = self._build_instrument_profile(instrument)

        # 3. Call Person 2's authoritative evaluator
        p2_decision: GATCRoutingDecision = evaluate_gatc_routing(inst_profile, job_type=p2_job_type)

        # 4. Resolve Regulatory Profile provenance
        target_profile_id = profile_id or "IN_LM_2011_ACTIVE"
        profile = PROFILE_REGISTRY.get_profile(target_profile_id)
        if not profile:
            profile = PROFILE_REGISTRY.get_default_profile()

        # 5. Check manual review triggers (P2 decision or unverified/draft profile)
        manual_review = p2_decision.requires_regulatory_confirmation
        review_reasons: List[str] = []

        if manual_review:
            review_reasons.append("Statutory authority requires manual regulatory confirmation.")

        if profile.verification_status in (ProfileStatus.MANUAL_REVIEW, ProfileStatus.DRAFT) or not profile.is_authoritative:
            manual_review = True
            review_reasons.append(
                f"Regulatory profile '{profile.profile_id}' is in {profile.verification_status.value} "
                f"status and requires legal confirmation prior to enforcement."
            )

        citation_dict = p2_decision.statutory_citation.to_dict() if p2_decision.statutory_citation else {}
        rule_ref = (
            f"{citation_dict.get('source_document', 'Legal Metrology (GATC) Rules, 2013')} "
            f"({citation_dict.get('clause_or_section', 'First Schedule')})".strip()
        )

        return RegulatoryRoutingResult(
            eligible_for_gatc=p2_decision.eligible_for_gatc,
            target_authority=p2_decision.target_authority,
            authority_name=p2_decision.authority_name,
            reason=p2_decision.reason,
            statutory_citation=citation_dict,
            regulatory_rule_reference=rule_ref,
            regulatory_profile_id=profile.profile_id,
            regulatory_version=profile.version,
            manual_review_flag=manual_review,
            manual_review_reason="; ".join(review_reasons) if review_reasons else None,
            p2_decision=p2_decision,
        )

    def _build_instrument_profile(
        self,
        instrument: Union[Instrument, InstrumentProfile, Dict[str, Any]],
    ) -> InstrumentProfile:
        """Translates instrument entity to Person 2 InstrumentProfile."""
        if isinstance(instrument, InstrumentProfile):
            return instrument

        if isinstance(instrument, Instrument):
            acc_class = AccuracyClass.from_string(instrument.accuracy_class.roman)
            unit = self._parse_mass_unit(instrument.unit)
            has_soft = instrument.software.has_software if instrument.software else False
            return InstrumentProfile(
                id=instrument.instrument_id,
                manufacturer=instrument.manufacturer,
                model=instrument.model_name,
                serial_number=instrument.serial_number,
                accuracy_class=acc_class,
                max_capacity=instrument.max_capacity,
                min_capacity=instrument.min_capacity,
                e=instrument.e,
                d=instrument.d,
                unit=unit,
                is_multi_interval=instrument.is_multi_interval,
                is_multi_range=instrument.is_multi_range,
                is_electronic=instrument.is_electronic,
                has_software=has_soft,
            )

        # Dictionary payload
        acc_str = str(instrument.get("accuracy_class", "CLASS_III"))
        acc_class = AccuracyClass.from_string(acc_str)
        unit = self._parse_mass_unit(instrument.get("unit", "kg"))
        return InstrumentProfile(
            id=str(instrument.get("instrument_id", "INST-001")),
            manufacturer=str(instrument.get("manufacturer", "Generic")),
            model=str(instrument.get("model_name") or instrument.get("model", "Model-1")),
            serial_number=str(instrument.get("serial_number", "SN-001")),
            accuracy_class=acc_class,
            max_capacity=float(instrument.get("max_capacity", 30.0)),
            min_capacity=float(instrument.get("min_capacity", 0.1)),
            e=float(instrument.get("e", 0.005)),
            d=float(instrument.get("d", 0.005)),
            unit=unit,
            is_multi_interval=bool(instrument.get("is_multi_interval", False)),
            is_multi_range=bool(instrument.get("is_multi_range", False)),
            is_electronic=bool(instrument.get("is_electronic", True)),
            has_software=bool(instrument.get("has_software", False)),
        )

    def _parse_mass_unit(self, val: Any) -> MassUnit:
        """Safely parses MassUnit from enum, object, or string."""
        if isinstance(val, MassUnit):
            return val
        if hasattr(val, "value"):
            val = val.value
        clean = str(val or "kg").strip().lower()
        for m in MassUnit:
            if m.value == clean or m.name.lower() == clean:
                return m
        return MassUnit.KG


# Global singleton for RegulatoryRoutingService
REGULATORY_ROUTING_SERVICE = RegulatoryRoutingService()


# =============================================================================
# 2. Job Location Service (Consumes RegulatoryRoutingService)
# =============================================================================

class JobLocationService:
    """
    Coordinates verification location types, assigned testing centres / laboratories,
    physical installation premises, and statutory GATC references for Test Jobs.
    """

    def __init__(self, routing_service: Optional[RegulatoryRoutingService] = None):
        self.routing_service = routing_service or REGULATORY_ROUTING_SERVICE

    def resolve_job_location_and_routing(
        self,
        instrument: Union[Instrument, Dict[str, Any]],
        job_type: Union[str, JobType] = JobType.RE_VERIFICATION,
        reason: Optional[Union[str, VerificationReason]] = None,
        preferred_location_type: Optional[Union[str, VerificationLocationType]] = None,
        testing_centre_id: Optional[str] = None,
        testing_centre_name: Optional[str] = None,
        gatc_reference: Optional[str] = None,
        profile_id: Optional[str] = None,
        strict_gatc_validation: bool = True,
    ) -> JobLocationRoutingResult:
        """
        Resolves complete verification location and routing metadata by evaluating P2 rules.

        :param instrument: Instrument record or dictionary.
        :param job_type: Verification job type.
        :param reason: Reason verification is required.
        :param preferred_location_type: User-requested location type.
        :param testing_centre_id: Identifier of testing centre or lab.
        :param testing_centre_name: Display name of centre/lab.
        :param gatc_reference: GATC accreditation code / certificate reference.
        :param profile_id: Applicable regulatory profile ID.
        :param strict_gatc_validation: If True, raises ValueError if GATC is requested for ineligible instrument.
        """
        # 1. Authoritative P2 routing evaluation
        routing_result = self.routing_service.evaluate_routing(
            instrument=instrument, job_type=job_type, profile_id=profile_id
        )

        # 2. Extract installation location from instrument
        inst_loc = self._extract_installation_location(instrument)

        # 3. Resolve verification reason
        v_reason = self._resolve_verification_reason(instrument, job_type, reason)

        # 4. Resolve Location Type & Testing Centre based on P2 decision
        resolved_loc_type: str
        resolved_lab: str
        resolved_test_centre: str
        resolved_centre_id = testing_centre_id
        resolved_gatc_ref: Optional[str] = None

        req_loc_str = str(preferred_location_type).upper() if preferred_location_type else None

        if routing_result.eligible_for_gatc:
            # GATC IS STATUTORILY AUTHORIZED
            if req_loc_str and "ON_SITE" in req_loc_str:
                resolved_loc_type = VerificationLocationType.ON_SITE_INSTALLATION.value
            elif req_loc_str and "STATE" in req_loc_str:
                resolved_loc_type = VerificationLocationType.STATE_LABORATORY.value
            else:
                resolved_loc_type = VerificationLocationType.GATC_CENTRE.value

            resolved_gatc_ref = gatc_reference or testing_centre_id or "GATC-CENTRAL-001"
            resolved_test_centre = testing_centre_name or "Government Approved Test Centre (GATC)"
            resolved_lab = resolved_test_centre

        else:
            # GATC IS STATUTORILY PROHIBITED (e.g. Class II, Class I, Class III > 150 kg, Model Approval)
            if strict_gatc_validation and (req_loc_str == "GATC_CENTRE" or (gatc_reference and not routing_result.eligible_for_gatc)):
                raise ValueError(
                    f"Statutory Routing Violation: Instrument '{self._get_instrument_id(instrument)}' "
                    f"is NOT eligible for GATC verification under the First Schedule of GATC Rules, 2013. "
                    f"Statutory Reason: {routing_result.reason}"
                )

            # Route to statutory authority dictated by P2
            if routing_result.target_authority == "CENTRAL_DIRECTORATE":
                resolved_loc_type = VerificationLocationType.CENTRAL_LABORATORY.value
                resolved_test_centre = (
                    testing_centre_name or
                    "Central Directorate / Authorized Laboratory (CSIR-NPL / RRSL)"
                )
                resolved_lab = resolved_test_centre
                resolved_gatc_ref = None

            else:  # STATE_LEGAL_METROLOGY_OFFICER
                max_cap = self._get_max_capacity_kg(instrument)
                if max_cap > 150.0 or (req_loc_str and "ON_SITE" in req_loc_str):
                    resolved_loc_type = VerificationLocationType.ON_SITE_INSTALLATION.value
                else:
                    resolved_loc_type = VerificationLocationType.STATE_LABORATORY.value

                resolved_test_centre = (
                    testing_centre_name or
                    "State Legal Metrology Department / Office of Inspector of Legal Metrology"
                )
                resolved_lab = resolved_test_centre
                resolved_gatc_ref = None

        return JobLocationRoutingResult(
            verification_location_type=resolved_loc_type,
            laboratory=resolved_lab,
            test_centre=resolved_test_centre,
            testing_centre_id=resolved_centre_id,
            gatc_reference=resolved_gatc_ref,
            installation_location=inst_loc,
            reason_for_verification=v_reason,
            routing_decision=routing_result.target_authority,
            regulatory_rule_reference=routing_result.regulatory_rule_reference,
            regulatory_profile_id=routing_result.regulatory_profile_id,
            regulatory_version=routing_result.regulatory_version,
            manual_review_flag=routing_result.manual_review_flag,
            manual_review_reason=routing_result.manual_review_reason,
            routing_result=routing_result,
        )

    def apply_to_job(
        self,
        job: TestJob,
        instrument: Union[Instrument, Dict[str, Any]],
        reason: Optional[Union[str, VerificationReason]] = None,
        preferred_location_type: Optional[Union[str, VerificationLocationType]] = None,
        testing_centre_id: Optional[str] = None,
        testing_centre_name: Optional[str] = None,
        gatc_reference: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> TestJob:
        """
        Evaluates location and statutory routing and applies all metadata fields to the TestJob entity.
        """
        res = self.resolve_job_location_and_routing(
            instrument=instrument,
            job_type=job.job_type,
            reason=reason or job.reason_for_verification,
            preferred_location_type=preferred_location_type or job.verification_location_type,
            testing_centre_id=testing_centre_id or job.testing_centre_id,
            testing_centre_name=testing_centre_name or job.testing_centre_name,
            gatc_reference=gatc_reference or job.gatc_reference,
            profile_id=profile_id or job.regulatory_profile_id,
            strict_gatc_validation=False,
        )

        job.verification_location_type = res.verification_location_type
        job.testing_centre_id = res.testing_centre_id
        job.testing_centre_name = res.test_centre
        job.assigned_laboratory = res.laboratory
        job.gatc_reference = res.gatc_reference
        job.installation_location = res.installation_location
        job.reason_for_verification = res.reason_for_verification
        job.routing_decision = res.routing_decision
        job.regulatory_rule_reference = res.regulatory_rule_reference
        job.regulatory_profile_id = res.regulatory_profile_id
        job.regulatory_version = res.regulatory_version
        job.manual_review_flag = res.manual_review_flag
        job.manual_review_reason = res.manual_review_reason

        # Synchronize statutory_routing container
        job.statutory_routing = StatutoryRoutingInfo(
            eligible_for_gatc=res.routing_result.eligible_for_gatc,
            target_authority=res.routing_result.target_authority,
            authority_name=res.routing_result.authority_name,
            reason=res.routing_result.reason,
            requires_regulatory_confirmation=res.manual_review_flag,
            citation=res.routing_result.statutory_citation,
        )

        return job

    def validate_location_assignment(
        self,
        instrument: Union[Instrument, Dict[str, Any]],
        location_type: Union[str, VerificationLocationType],
        job_type: Union[str, JobType] = JobType.RE_VERIFICATION,
    ) -> Tuple[bool, str]:
        """
        Validates whether a proposed verification location complies with P2 statutory routing.
        """
        routing = self.routing_service.evaluate_routing(instrument, job_type=job_type)
        loc_str = str(location_type.value if hasattr(location_type, "value") else location_type).upper()

        if "GATC" in loc_str and not routing.eligible_for_gatc:
            return (
                False,
                f"Statutory Routing Violation: Instrument '{self._get_instrument_id(instrument)}' "
                f"is not eligible for GATC verification. Statutory Reason: {routing.reason}",
            )

        return True, "Proposed verification location satisfies statutory routing rules."

    # -------------------------------------------------------------------------
    # Helper methods
    # -------------------------------------------------------------------------

    def _extract_installation_location(
        self,
        instrument: Union[Instrument, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Extracts customer premises / installation location dictionary."""
        if isinstance(instrument, Instrument):
            if instrument.location:
                return instrument.location.to_dict()
            return None
        return instrument.get("location") or instrument.get("installation_location")

    def _resolve_verification_reason(
        self,
        instrument: Union[Instrument, Dict[str, Any]],
        job_type: Union[str, JobType],
        explicit_reason: Optional[Union[str, VerificationReason]] = None,
    ) -> str:
        """Determines the statutory verification reason."""
        if explicit_reason:
            if hasattr(explicit_reason, "value"):
                return explicit_reason.value
            return str(explicit_reason)

        if isinstance(instrument, Instrument) and instrument.verification_reason:
            return instrument.verification_reason

        j_val = job_type.value if hasattr(job_type, "value") else str(job_type)
        if "INITIAL" in j_val:
            return VerificationReason.INITIAL_STAMPING.value
        if "REPAIR" in j_val:
            return VerificationReason.POST_REPAIR.value
        if "RELOCATION" in j_val:
            return VerificationReason.POST_RELOCATION.value
        if "REINSTALL" in j_val:
            return VerificationReason.POST_REINSTALLATION.value
        return VerificationReason.PERIODIC_EXPIRY.value

    def _get_instrument_id(self, instrument: Union[Instrument, Dict[str, Any]]) -> str:
        if isinstance(instrument, Instrument):
            return instrument.instrument_id
        return str(instrument.get("instrument_id", "UNKNOWN"))

    def _get_max_capacity_kg(self, instrument: Union[Instrument, Dict[str, Any]]) -> float:
        if isinstance(instrument, Instrument):
            unit_val = instrument.unit.value if hasattr(instrument.unit, "value") else str(instrument.unit)
            cap = float(instrument.max_capacity)
        else:
            unit_val = str(instrument.get("unit", "kg"))
            cap = float(instrument.get("max_capacity", 30.0))

        u_clean = unit_val.lower()
        if u_clean == "g":
            return cap / 1000.0
        if u_clean in ("t", "ton", "tonne"):
            return cap * 1000.0
        if u_clean == "mg":
            return cap / 1000000.0
        return cap


# Global singleton for JobLocationService
JOB_LOCATION_SERVICE = JobLocationService()
