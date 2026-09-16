"""
MetrIQ Regulatory Engine - API Router Endpoints
Provides REST API endpoints for Person 1 (Team Lead) to expose regulatory
services to the frontend and other services. Compatible with FastAPI.
"""

from typing import Dict, Any, List, Optional

from .models import (
    InstrumentProfile,
    JobType,
    AccuracyClass,
    MassUnit,
    MPEValue,
    TestPlan,
)
from .scale_validation import validate_instrument_scales
from .mpe import (
    calculate_mpe,
    is_error_within_mpe,
    get_mpe_breakpoints_for_instrument,
)
from .mpe_engine import MPEEngine, calculate_mpe_statutory
from .applicability import get_applicable_tests, evaluate_test_applicability
from .test_plan import generate_test_plan
from .test_plan_generator import generate_regulatory_test_plan, RegulatoryTestPlanGenerator
from .sources import REGULATORY_REGISTRY
from .config import get_manual_review_checklist, get_default_config


# Pure python service functions for direct invocation by Person 1 or routers
def api_validate_scales(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validates scale interval, capacity, and accuracy class parameters."""
    instrument = InstrumentProfile.from_dict(payload)
    standard_id = payload.get("regulatory_standard", "OIML_R76_2006")
    result = validate_instrument_scales(instrument, standard_id=standard_id)
    return result.to_dict()


def api_calculate_mpe(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculates Maximum Permissible Error for a given test load.
    Supports direct stateless parameters (accuracy_class, load, e, verification_type, observed_error)
    as well as full InstrumentProfile payloads.
    """
    if "accuracy_class" in payload and "e" in payload:
        acc_class = payload.get("accuracy_class")
        load = payload.get("load", 0.0)
        e = payload.get("e", 1.0)
        v_type = payload.get("verification_type") or payload.get("job_type", "INITIAL")
        observed_error = payload.get("observed_error")
        observed_error_e = payload.get("observed_error_in_e")

        res = MPEEngine.calculate(
            accuracy_class=acc_class,
            load=load,
            e=e,
            verification_type=v_type,
            observed_error=observed_error,
            observed_error_in_e=observed_error_e,
        )
        return res.to_dict()

    instrument = InstrumentProfile.from_dict(payload.get("instrument", {}))
    load = float(payload.get("load", 0.0))
    job_type_str = payload.get("job_type", "INITIAL_VERIFICATION")
    job_type = JobType(job_type_str) if isinstance(job_type_str, str) else job_type_str
    tare_load = float(payload.get("tare_load", 0.0))
    standard_id = payload.get("regulatory_standard", "OIML_R76_2006")

    mpe = calculate_mpe(
        load=load,
        instrument=instrument,
        job_type=job_type,
        tare_load=tare_load,
        standard_id=standard_id,
    )
    return mpe.to_dict()


def api_evaluate_error(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluates whether an observed error is within MPE."""
    instrument = InstrumentProfile.from_dict(payload.get("instrument", {}))
    load = float(payload.get("load", 0.0))
    observed_error = float(payload.get("observed_error", 0.0))
    job_type_str = payload.get("job_type", "INITIAL_VERIFICATION")
    job_type = JobType(job_type_str) if isinstance(job_type_str, str) else job_type_str
    tare_load = float(payload.get("tare_load", 0.0))
    standard_id = payload.get("regulatory_standard", "OIML_R76_2006")

    is_pass, mpe = is_error_within_mpe(
        observed_error=observed_error,
        load=load,
        instrument=instrument,
        job_type=job_type,
        tare_load=tare_load,
        standard_id=standard_id,
    )
    return {
        "is_pass": is_pass,
        "observed_error": observed_error,
        "mpe": mpe.to_dict(),
    }


def api_applicable_tests(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Returns statutory test applicability list."""
    instrument = InstrumentProfile.from_dict(payload.get("instrument", {}))
    job_type_str = payload.get("job_type", "INITIAL_VERIFICATION")
    job_type = JobType(job_type_str) if isinstance(job_type_str, str) else job_type_str
    standard_id = payload.get("regulatory_standard", "OIML_R76_2006")

    tests = get_applicable_tests(instrument, job_type, standard_id)
    return [t.to_dict() for t in tests]


def api_evaluate_applicability(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates complete statutory test applicability based on instrument characteristics.
    Returns categorized lists: applicable_tests, not_applicable_tests, manual_review_tests, warnings.
    """
    return evaluate_test_applicability(payload)


def api_generate_test_plan(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Generates complete statutory test plan."""
    if "instrument" not in payload and any(k in payload for k in ("accuracy_class", "Max", "class", "max_capacity")):
        return generate_regulatory_test_plan(payload)

    instrument = InstrumentProfile.from_dict(payload.get("instrument", {}))
    job_type_str = payload.get("job_type", "INITIAL_VERIFICATION")
    job_type = JobType(job_type_str) if isinstance(job_type_str, str) else job_type_str
    standard_id = payload.get("regulatory_standard", "OIML_R76_2006")

    plan = generate_test_plan(instrument, job_type, standard_id=standard_id)
    return plan.to_dict()


def api_generate_regulatory_test_plan(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generates complete statutory test plan using modern 5-stage regulatory pipeline.
    Directly consumable by Person 4 (Test Engine).
    """
    return generate_regulatory_test_plan(payload)


def api_list_standards() -> List[Dict[str, Any]]:
    """Lists all registered statutory standards."""
    return [s.to_dict() for s in REGULATORY_REGISTRY.list_all()]


def api_list_manual_review_items() -> List[Dict[str, Any]]:
    """Lists statutory manual review inspection checklist."""
    return [item.to_dict() for item in get_manual_review_checklist()]


def api_get_knowledge_classes() -> List[Dict[str, Any]]:
    """Returns structured definitions for all accuracy classes."""
    from .knowledge import KNOWLEDGE_BASE
    return [c.to_dict() for c in KNOWLEDGE_BASE.list_accuracy_classes()]


def api_get_knowledge_rules(category: Optional[str] = None, origin: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns rules from knowledge base filtered by category or legal origin."""
    from .knowledge import KNOWLEDGE_BASE, RuleCategory, LegalOrigin
    if category:
        rules = KNOWLEDGE_BASE.get_rules_by_category(RuleCategory(category))
    elif origin:
        rules = KNOWLEDGE_BASE.get_rules_by_origin(LegalOrigin(origin))
    else:
        rules = list(KNOWLEDGE_BASE._rules.values()) + list(KNOWLEDGE_BASE._amendments.values())
    return [r.to_dict() for r in rules]


def api_evaluate_gatc_routing(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluates statutory GATC verification routing decision."""
    from .knowledge import KNOWLEDGE_BASE
    instrument = InstrumentProfile.from_dict(payload.get("instrument", {}))
    job_type_str = payload.get("job_type", "RE_VERIFICATION")
    job_type = JobType(job_type_str) if isinstance(job_type_str, str) else job_type_str
    decision = KNOWLEDGE_BASE.evaluate_gatc_routing(instrument, job_type=job_type)
    return decision.to_dict()


def api_get_unverified_amendments() -> List[Dict[str, Any]]:
    """Returns unverified/draft amendments such as Fourth Amendment 2026."""
    from .knowledge import KNOWLEDGE_BASE
    return [r.to_dict() for r in KNOWLEDGE_BASE.get_unverified_rules()]


def api_get_test_weight_requirements(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Returns test weight requirements and class mapping for an instrument."""
    from .knowledge import KNOWLEDGE_BASE
    instrument = InstrumentProfile.from_dict(payload.get("instrument", {}))
    return KNOWLEDGE_BASE.get_test_weight_requirement(instrument)


# FastAPI router integration if installed
try:
    from fastapi import APIRouter, Body, Query

    router = APIRouter(prefix="/regulatory", tags=["Regulatory Engine"])

    @router.post("/validate-scales")
    def endpoint_validate_scales(payload: Dict[str, Any] = Body(...)):
        return api_validate_scales(payload)

    @router.post("/calculate-mpe")
    def endpoint_calculate_mpe(payload: Dict[str, Any] = Body(...)):
        return api_calculate_mpe(payload)

    @router.post("/evaluate-error")
    def endpoint_evaluate_error(payload: Dict[str, Any] = Body(...)):
        return api_evaluate_error(payload)

    @router.post("/applicable-tests")
    def endpoint_applicable_tests(payload: Dict[str, Any] = Body(...)):
        return api_applicable_tests(payload)

    @router.post("/evaluate-applicability")
    def endpoint_evaluate_applicability(payload: Dict[str, Any] = Body(...)):
        return api_evaluate_applicability(payload)

    @router.post("/generate-test-plan")
    def endpoint_generate_test_plan(payload: Dict[str, Any] = Body(...)):
        return api_generate_test_plan(payload)

    @router.post("/generate-regulatory-test-plan")
    def endpoint_generate_regulatory_test_plan(payload: Dict[str, Any] = Body(...)):
        return api_generate_regulatory_test_plan(payload)

    @router.get("/standards")
    def endpoint_list_standards():
        return api_list_standards()

    @router.get("/manual-review-checklist")
    def endpoint_manual_review_checklist():
        return api_list_manual_review_items()

    @router.get("/knowledge/classes")
    def endpoint_knowledge_classes():
        return api_get_knowledge_classes()

    @router.get("/knowledge/rules")
    def endpoint_knowledge_rules(category: Optional[str] = Query(None), origin: Optional[str] = Query(None)):
        return api_get_knowledge_rules(category=category, origin=origin)

    @router.post("/knowledge/gatc-routing")
    def endpoint_knowledge_gatc_routing(payload: Dict[str, Any] = Body(...)):
        return api_evaluate_gatc_routing(payload)

    @router.get("/knowledge/unverified-amendments")
    def endpoint_knowledge_unverified_amendments():
        return api_get_unverified_amendments()

    @router.post("/knowledge/test-weights")
    def endpoint_knowledge_test_weights(payload: Dict[str, Any] = Body(...)):
        return api_get_test_weight_requirements(payload)

except ImportError:
    # FastAPI is not yet installed in current Python environment.
    # The pure Python API functions above are directly usable by Person 1.
    router = None
