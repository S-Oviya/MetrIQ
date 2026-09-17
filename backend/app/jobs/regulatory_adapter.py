"""
MetrIQ Regulatory Adapter — Person 3 (Job / Instrument Engineer)
================================================================
Provides a clean, decoupled adapter interface between Person 3 Test Job
Management and Person 2 Regulatory Engine.

Queries and consumes Person 2's regulatory services:
- Regulatory Profile & Version (get_regulatory_profile_api)
- Test Applicability & Statutory Rules (determine_applicable_tests_api)
- Automatic Test Plan Generation (generate_test_plan_api)
- Statutory GATC Routing (evaluate_gatc_routing)

Strictly adheres to team boundaries: does NOT modify or duplicate Person 2 rules.
"""

from typing import Any, Dict, List, Optional, Tuple

# Person 2 canonical models and APIs (consumed as exposed interfaces)
from app.regulatory.models import (
    AccuracyClass,
    JobType as P2JobType,
    MassUnit,
    InstrumentProfile,
)
from app.regulatory.knowledge.gatc_rules_data import evaluate_gatc_routing
from app.regulatory.api import (
    determine_applicable_tests_api,
    generate_test_plan_api,
    get_regulatory_profile_api,
    get_rule_or_source_api,
)


class RegulatoryAdapter:
    """
    Adapter facilitating clean communication between Person 3 (Job Management)
    and Person 2 (Regulatory Engine).
    """

    @classmethod
    def validate_metrology_feasibility(cls, instrument_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates instrument metrological parameters using Person 2 validate_instrument_api.
        """
        from app.regulatory.api import validate_instrument_api
        res = validate_instrument_api(instrument_dict)
        if res.get("success") and res.get("data"):
            return res["data"]
        return {"valid": False, "errors": [{"message": res.get("message", "Validation failed")}], "warnings": []}

    @classmethod
    def get_profile_and_version(
        cls, profile_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieves regulatory profile metadata, version, and rule sources.
        Consumes Person 2's get_regulatory_profile_api.
        """
        params = {"profile_id": profile_id} if profile_id else {}
        resp = get_regulatory_profile_api(params)
        if resp.get("success") and resp.get("data"):
            data = resp["data"]
            active_details = data.get("active_profile_details", {})
            return {
                "profile_id": active_details.get("profile_id") or profile_id or "IN_LM_2011_ACTIVE",
                "version": active_details.get("version") or data.get("version", "1.0.0"),
                "jurisdiction": active_details.get("jurisdiction", "INDIA"),
                "regulation_name": active_details.get("regulation_name") or data.get("active_profile", "Legal Metrology Act, 2009 / General Rules 2011"),
                "sources": data.get("primary_indian_sources", []),
                "technical_sources": data.get("technical_sources", []),
            }

        # Safe statutory fallback
        return {
            "profile_id": profile_id or "IN_LM_2011_ACTIVE",
            "version": "1.0.0",
            "jurisdiction": "INDIA",
            "regulation_name": "Indian Legal Metrology (General) Rules, 2011 / Seventh Schedule",
            "sources": [],
            "technical_sources": [],
        }

    @classmethod
    def determine_applicable_tests(
        cls, instrument_dict: Dict[str, Any], is_type_evaluation: bool = False
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        """
        Determines applicable tests and rule references for an instrument.
        Consumes Person 2's determine_applicable_tests_api.
        Returns: (list_of_test_ids, list_of_full_test_definitions)
        """
        payload = dict(instrument_dict)
        payload["is_type_evaluation"] = is_type_evaluation
        resp = determine_applicable_tests_api(payload)

        if resp.get("success") and resp.get("data"):
            data = resp["data"]
            tests = data.get("applicable_tests", [])
            test_ids = [t.get("test_id") for t in tests if t.get("test_id")]
            return test_ids, tests

        # Standard statutory baseline test IDs if determination is unavailable
        baseline_ids = ["A.1", "A.2", "A.3", "A.4.2", "A.4.3", "A.4.4", "A.4.7", "A.4.8", "A.4.10"]
        return baseline_ids, []

    @classmethod
    def generate_automatic_test_plan(
        cls,
        instrument_spec: Dict[str, Any],
        job_id: str,
        job_type_str: str,
        profile_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Generates statutory test plan with load points, eccentricity positions,
        repeatability cycles, and MPE bounds.
        Consumes Person 2's generate_test_plan_api.
        """
        reg_spec = dict(instrument_spec)
        reg_spec["job_id"] = job_id
        is_in_service = job_type_str in ("RE_VERIFICATION", "POST_RELOCATION", "REINSTALLATION")
        reg_spec["verification_type"] = "SUBSEQUENT" if is_in_service else "INITIAL"
        reg_spec["is_type_evaluation"] = (job_type_str == "MODEL_APPROVAL")
        if profile_id:
            reg_spec["profile_id"] = profile_id

        plan_res = generate_test_plan_api(reg_spec)
        if plan_res.get("success") and plan_res.get("data"):
            return plan_res["data"]
        return None

    @classmethod
    def evaluate_routing(
        cls,
        instrument_id: str,
        manufacturer: str,
        model: str,
        serial_number: str,
        accuracy_class: AccuracyClass,
        max_capacity: float,
        min_capacity: float,
        e: float,
        d: float,
        unit: MassUnit,
        is_multi_interval: bool,
        is_multi_range: bool,
        is_electronic: bool,
        has_software: bool,
        p2_job_type: P2JobType,
    ) -> Any:
        """
        Evaluates GATC routing decision using Person 2's GATC rules engine.
        """
        inst_profile = InstrumentProfile(
            id=instrument_id,
            manufacturer=manufacturer,
            model=model,
            serial_number=serial_number,
            accuracy_class=accuracy_class,
            max_capacity=max_capacity,
            min_capacity=min_capacity,
            e=e,
            d=d,
            unit=unit,
            is_multi_interval=is_multi_interval,
            is_multi_range=is_multi_range,
            is_electronic=is_electronic,
            has_software=has_software,
        )
        return evaluate_gatc_routing(inst_profile, job_type=p2_job_type)
