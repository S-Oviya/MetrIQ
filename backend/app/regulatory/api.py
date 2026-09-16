"""
MetrIQ Regulatory Engine - API Service & Facade Layer
=====================================================
Provides clean, consistent, high-level API functions and service interfaces
for Person 1 (Team Lead) and external backend modules to interact with the
Regulatory Engine without importing internal submodules directly.

Endpoints / Operations supported:
1. Validate Instrument:           POST /regulatory/validate-instrument
2. Calculate MPE:                 POST /regulatory/mpe
3. Determine Applicable Tests:    POST /regulatory/applicable-tests
4. Generate Test Plan:            POST /regulatory/test-plan
5. Retrieve Regulatory Profile:   GET  /regulatory/profile
6. Retrieve Rule / Source Info:   GET  /regulatory/rules/{rule_id}

Returns consistent structured response envelopes with standard HTTP status codes
and detailed error structures.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
import re

# Internal imports within regulatory module
from .classification_validator import RegulatoryClassificationValidator
from .mpe_engine import MPEEngine, VerificationType
from .test_applicability_engine import (
    RegulatoryTestApplicabilityEngine,
    InstrumentCharacteristics,
    ALL_STATUTORY_TESTS,
)
from .test_plan_generator import RegulatoryTestPlanGenerator
from .sources import REGULATORY_REGISTRY
from .knowledge import KNOWLEDGE_BASE
from .models import AccuracyClass, MassUnit


# =============================================================================
# Standard API Response Envelopes
# =============================================================================

def _iso_timestamp() -> str:
    """Returns current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def success_response(
    data: Any,
    status_code: int = 200,
    message: Optional[str] = None,
) -> Dict[str, Any]:
    """Wraps successful output in a standard API response envelope."""
    resp: Dict[str, Any] = {
        "success": True,
        "status_code": status_code,
        "data": data,
        "timestamp": _iso_timestamp(),
    }
    if message:
        resp["message"] = message
    return resp


def error_response(
    code: str,
    message: str,
    status_code: int = 400,
    details: Optional[Any] = None,
) -> Dict[str, Any]:
    """Constructs a consistent structured error envelope with HTTP status."""
    err_body: Dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if details is not None:
        err_body["details"] = details
    return {
        "success": False,
        "status_code": status_code,
        "error": err_body,
        "timestamp": _iso_timestamp(),
    }


def _safe_float(val: Any, field_name: str) -> Tuple[Optional[float], Optional[Dict[str, Any]]]:
    """Converts a value to float safely without silent corruption."""
    if val is None:
        return None, {"field": field_name, "issue": f"Field '{field_name}' cannot be null."}
    try:
        f = float(val)
        return f, None
    except (ValueError, TypeError):
        return None, {"field": field_name, "issue": f"Field '{field_name}' must be numeric; received '{val}'."}


# =============================================================================
# 1. Validate Instrument (POST /regulatory/validate-instrument)
# =============================================================================

def validate_instrument_api(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validates instrument parameters against statutory OIML R 76-1 / Indian Legal Metrology limits.

    :param payload: Dictionary containing accuracy_class, Max, Min, e, etc.
    :return: Structured API response (HTTP 200 for evaluated instrument, 400/422 for malformed request).
    """
    if not isinstance(payload, dict) or not payload:
        return error_response(
            code="INVALID_REQUEST_PAYLOAD",
            message="Request body must be a non-empty JSON object.",
            status_code=400,
        )

    # Unwrap nested instrument object if provided
    spec = dict(payload.get("instrument", payload))
    for k, v in payload.items():
        if k != "instrument" and k not in spec:
            spec[k] = v

    # Required field verification
    raw_class = spec.get("accuracy_class") or spec.get("class")
    if not raw_class:
        return error_response(
            code="MISSING_REQUIRED_FIELD",
            message="Missing required field 'accuracy_class'. Allowed values: 'I', 'II', 'III', 'IIII'.",
            status_code=400,
            details=[{"field": "accuracy_class", "issue": "Field is required"}],
        )

    raw_max = spec.get("Max") if spec.get("Max") is not None else spec.get("max_capacity")
    if raw_max is None:
        return error_response(
            code="MISSING_REQUIRED_FIELD",
            message="Missing required field 'Max' (maximum capacity).",
            status_code=400,
            details=[{"field": "Max", "issue": "Field is required"}],
        )

    raw_e = spec.get("e") if spec.get("e") is not None else spec.get("verification_scale_interval")
    if raw_e is None:
        return error_response(
            code="MISSING_REQUIRED_FIELD",
            message="Missing required field 'e' (verification scale interval).",
            status_code=400,
            details=[{"field": "e", "issue": "Field is required"}],
        )

    # Validate numeric types
    _, err_max = _safe_float(raw_max, "Max")
    if err_max:
        return error_response(
            code="INVALID_FIELD_FORMAT",
            message=err_max["issue"],
            status_code=422,
            details=[err_max],
        )

    _, err_e = _safe_float(raw_e, "e")
    if err_e:
        return error_response(
            code="INVALID_FIELD_FORMAT",
            message=err_e["issue"],
            status_code=422,
            details=[err_e],
        )

    # Run statutory validation engine
    val_result = RegulatoryClassificationValidator.validate(spec)
    val_dict = val_result.to_dict()
    summary = val_dict.get("instrument_summary") or {}
    val_dict["accuracy_class"] = summary.get("accuracy_class") or str(raw_class)
    val_dict["max_capacity"] = summary.get("max_capacity") if summary.get("max_capacity") is not None else float(raw_max)
    val_dict["min_capacity"] = summary.get("min_capacity")
    val_dict["e"] = summary.get("e") if summary.get("e") is not None else float(raw_e)
    val_dict["d"] = summary.get("d")
    val_dict["n"] = summary.get("n") if summary.get("n") is not None else int(round(float(raw_max) / float(raw_e)))
    val_dict["unit"] = summary.get("unit") or spec.get("unit", "kg")
    return success_response(val_dict, status_code=200)


# =============================================================================
# 2. Calculate MPE (POST /regulatory/mpe)
# =============================================================================

def calculate_mpe_api(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculates Maximum Permissible Error (MPE) for a given load and scale interval e.

    :param payload: Dictionary containing accuracy_class, load, e, and optional verification_type, observed_error.
    :return: Structured API response (HTTP 200 on calculation, 400/422 on invalid parameters).
    """
    if not isinstance(payload, dict) or not payload:
        return error_response(
            code="INVALID_REQUEST_PAYLOAD",
            message="Request body must be a non-empty JSON object.",
            status_code=400,
        )

    # Extract accuracy class
    raw_class = payload.get("accuracy_class") or payload.get("class")
    if not raw_class:
        # Check nested instrument
        inst = payload.get("instrument", {})
        raw_class = inst.get("accuracy_class") or inst.get("class")

    if not raw_class:
        return error_response(
            code="MISSING_PARAMETER",
            message="Missing required parameter 'accuracy_class'. Allowed values: 'I', 'II', 'III', 'IIII'.",
            status_code=400,
            details=[{"field": "accuracy_class", "issue": "Parameter is required"}],
        )

    # Extract load
    raw_load = payload.get("load")
    if raw_load is None:
        return error_response(
            code="MISSING_PARAMETER",
            message="Missing required parameter 'load'.",
            status_code=400,
            details=[{"field": "load", "issue": "Parameter is required"}],
        )

    load_val, err_load = _safe_float(raw_load, "load")
    if err_load:
        return error_response(
            code="INVALID_PARAMETER_FORMAT",
            message=err_load["issue"],
            status_code=422,
            details=[err_load],
        )

    # Extract scale interval e
    raw_e = payload.get("e")
    if raw_e is None:
        inst = payload.get("instrument", {})
        raw_e = inst.get("e") or inst.get("verification_scale_interval")

    if raw_e is None:
        return error_response(
            code="MISSING_PARAMETER",
            message="Missing required parameter 'e' (verification scale interval).",
            status_code=400,
            details=[{"field": "e", "issue": "Parameter is required"}],
        )

    e_val, err_e = _safe_float(raw_e, "e")
    if err_e:
        return error_response(
            code="INVALID_PARAMETER_FORMAT",
            message=err_e["issue"],
            status_code=422,
            details=[err_e],
        )

    if e_val <= 0:
        return error_response(
            code="INVALID_SCALE_INTERVAL",
            message=f"Scale interval 'e' must be strictly positive (> 0). Received: {e_val}.",
            status_code=422,
            details=[{"field": "e", "issue": "Must be > 0"}],
        )

    # Verification type & observed error
    v_type_raw = payload.get("verification_type") or payload.get("job_type", "INITIAL")
    observed_err = payload.get("observed_error")
    observed_err_e = payload.get("observed_error_in_e")
    unit_str = payload.get("unit") or "kg"

    try:
        res = MPEEngine.calculate(
            accuracy_class=raw_class,
            load=load_val,
            e=e_val,
            verification_type=v_type_raw,
            observed_error=observed_err,
            observed_error_in_e=observed_err_e,
        )
        data = res.to_dict()
        data["unit"] = str(unit_str)
        data["tolerance_band"] = data.get("band_description", "")
        data["lower_limit_error"] = -data["mpe_absolute"]
        data["upper_limit_error"] = data["mpe_absolute"]
        data["is_pass"] = res.passed
        data["passed"] = res.passed
        return success_response(data, status_code=200)
    except ValueError as ex:
        return error_response(
            code="MPE_CALCULATION_ERROR",
            message=str(ex),
            status_code=422,
        )


# =============================================================================
# 3. Determine Applicable Tests (POST /regulatory/applicable-tests)
# =============================================================================

def determine_applicable_tests_api(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Determines statutory test applicability across OIML R 76-1 Annex A & B and Indian Legal Metrology Rules.

    :param payload: Dictionary containing instrument characteristics.
    :return: Structured report of applicable, not-applicable, and manual-review tests.
    """
    if not isinstance(payload, dict):
        return error_response(
            code="INVALID_REQUEST_PAYLOAD",
            message="Request body must be a JSON object.",
            status_code=400,
        )

    report = RegulatoryTestApplicabilityEngine.evaluate(payload)
    data = report.to_dict()
    data["total_tests_evaluated"] = len(report.applicable_tests) + len(report.not_applicable_tests)
    data["applicable_count"] = len(report.applicable_tests)
    data["not_applicable_count"] = len(report.not_applicable_tests)
    data["manual_review_count"] = len(report.manual_review_tests)
    return success_response(data, status_code=200)


# =============================================================================
# 4. Generate Test Plan (POST /regulatory/test-plan)
# =============================================================================

def generate_test_plan_api(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Executes the 5-stage regulatory pipeline and generates a complete statutory test plan.

    :param payload: Validated instrument specification dictionary.
    :return: GeneratedTestPlan object serializable dictionary.
    """
    if not isinstance(payload, dict) or not payload:
        return error_response(
            code="INVALID_REQUEST_PAYLOAD",
            message="Request body must be a non-empty JSON object.",
            status_code=400,
        )

    # Unwrap nested instrument if passed
    spec = dict(payload.get("instrument", payload))
    for k, v in payload.items():
        if k != "instrument" and k not in spec:
            spec[k] = v

    # Verify essential test planning parameters
    raw_class = spec.get("accuracy_class") or spec.get("class")
    if not raw_class:
        return error_response(
            code="MISSING_PLAN_PARAMETERS",
            message="Cannot generate test plan: missing required parameter 'accuracy_class'.",
            status_code=400,
            details=[{"field": "accuracy_class", "issue": "Parameter is required"}],
        )

    raw_max = spec.get("Max") if spec.get("Max") is not None else spec.get("max_capacity")
    if raw_max is None:
        return error_response(
            code="MISSING_PLAN_PARAMETERS",
            message="Cannot generate test plan: missing required parameter 'Max'.",
            status_code=400,
            details=[{"field": "Max", "issue": "Parameter is required"}],
        )

    raw_e = spec.get("e") if spec.get("e") is not None else spec.get("verification_scale_interval")
    if raw_e is None:
        return error_response(
            code="MISSING_PLAN_PARAMETERS",
            message="Cannot generate test plan: missing required parameter 'e'.",
            status_code=400,
            details=[{"field": "e", "issue": "Parameter is required"}],
        )

    # Validate numbers
    _, err_max = _safe_float(raw_max, "Max")
    if err_max:
        return error_response(
            code="INVALID_PARAMETER_FORMAT",
            message=err_max["issue"],
            status_code=422,
            details=[err_max],
        )

    _, err_e = _safe_float(raw_e, "e")
    if err_e:
        return error_response(
            code="INVALID_PARAMETER_FORMAT",
            message=err_e["issue"],
            status_code=422,
            details=[err_e],
        )

    try:
        plan = RegulatoryTestPlanGenerator.generate(spec)
        return success_response(plan.to_dict(), status_code=200)
    except Exception as ex:
        return error_response(
            code="TEST_PLAN_GENERATION_FAILED",
            message=f"Failed to generate statutory test plan: {str(ex)}",
            status_code=500,
        )


# =============================================================================
# 5. Retrieve Regulatory Profile/Version (GET /regulatory/profile)
# =============================================================================

def get_regulatory_profile_api() -> Dict[str, Any]:
    """
    Returns active regulatory profiles, standard versions, and jurisdictional authorities.
    """
    indian_sources = [
        {
            "code": "LM_ACT_2009",
            "title": "Legal Metrology Act, 2009 (Act 1 of 2010)",
            "jurisdiction": "INDIA",
            "authority": "Department of Consumer Affairs, Government of India",
            "status": "STATUTORY_MANDATORY",
            "description": "Primary statutory legislation establishing legal units of weights and measures in India.",
        },
        {
            "code": "IN_LM_2011",
            "title": "Legal Metrology (General) Rules, 2011",
            "schedule": "Seventh Schedule (Non-Automatic Weighing Instruments)",
            "jurisdiction": "INDIA",
            "authority": "Department of Consumer Affairs, Government of India",
            "status": "STATUTORY_MANDATORY",
            "description": "Governs classification, verification scale intervals, tolerances, and verification tests for NAWIs.",
        },
        {
            "code": "IN_AMR_2011",
            "title": "Legal Metrology (Approval of Models) Rules, 2011",
            "jurisdiction": "INDIA",
            "authority": "Central Government / Regional Reference Standards Laboratories",
            "status": "STATUTORY_MANDATORY",
            "description": "Mandates statutory model approval and pattern evaluation prior to manufacture or import.",
        },
        {
            "code": "IN_GATC_2013",
            "title": "Legal Metrology (Government Approved Test Centre) Rules, 2013",
            "jurisdiction": "INDIA",
            "authority": "Central Government / State Metrology Departments",
            "status": "STATUTORY_MANDATORY",
            "description": "Prescribes verification routing, eligible accuracy classes (Class II, III, IIII), and GATC accreditation rules.",
        },
    ]

    technical_sources = [
        {
            "code": "OIML_R76_2006",
            "title": "OIML R 76-1:2006 Non-automatic weighing instruments - Part 1: Metrological and technical requirements - Tests",
            "jurisdiction": "INTERNATIONAL",
            "authority": "International Organization of Legal Metrology (OIML)",
            "status": "TECHNICAL_STANDARD",
            "description": "Authoritative international metrological basis for test procedures, MPE tables, and disturbance testing.",
        },
        {
            "code": "OIML_R76_2_2007",
            "title": "OIML R 76-2:2007 Non-automatic weighing instruments - Part 2: Pattern evaluation report",
            "jurisdiction": "INTERNATIONAL",
            "authority": "International Organization of Legal Metrology (OIML)",
            "status": "TECHNICAL_REPORT_FORMAT",
            "description": "Standardized test report form and format (not an Indian statutory requirement).",
        },
    ]

    profile_data = {
        "engine_name": "MetrIQ Regulatory Compliance Engine",
        "version": "1.0.0",
        "active_profile": "OIML R 76-1:2006 / Indian Legal Metrology (General) Rules, 2011",
        "supported_accuracy_classes": ["I", "II", "III", "IIII"],
        "supported_verification_types": ["INITIAL", "SUBSEQUENT", "IN_SERVICE"],
        "primary_indian_sources": indian_sources,
        "technical_sources": technical_sources,
        "statutory_distinctions": {
            "indian_legal": "Statutory requirements carrying legal force under Legal Metrology Act, 2009 and Central Rules.",
            "oiml_technical": "International technical standards and test protocols.",
            "report_formats": "Default evaluation templates (e.g. OIML R 76-2, non-statutory in India).",
            "configurable_rules": "Parameters that testing laboratories or State controllers can configure.",
            "manual_review": "Procedures requiring physical visual inspection or inspector discretion.",
        },
        "gatc_routing_supported": True,
        "subsequent_mpe_multiplier": 2.0,
    }

    return success_response(profile_data, status_code=200)


# =============================================================================
# 6. Retrieve Rule / Source Information (GET /regulatory/rules/{rule_id})
# =============================================================================

def get_rule_or_source_api(rule_id: str) -> Dict[str, Any]:
    """
    Retrieves detailed statutory rule, test procedure, standard source, or class definition by identifier.

    :param rule_id: Identifier (e.g. 'A.4.4', 'RULE_MPE_CLASS_III_INITIAL', 'OIML_R76_2006', 'IN_LM_2011', 'CLASS_III')
    :return: Structured rule details or HTTP 404 if not found.
    """
    if not rule_id or not str(rule_id).strip():
        return error_response(
            code="MISSING_RULE_ID",
            message="Rule ID parameter cannot be empty.",
            status_code=400,
        )

    clean_id = str(rule_id).strip()

    # 1. Look up in Knowledge Base Rules and Amendments
    kb_rule = KNOWLEDGE_BASE.get_rule(clean_id)
    if kb_rule:
        return success_response(kb_rule.to_dict(), status_code=200)

    # 2. Look up in Regulatory Sources Registry
    src = REGULATORY_REGISTRY.get(clean_id)
    if src:
        src_data = src.to_dict()
        src_data["type"] = "REGULATORY_STANDARD_SOURCE"
        return success_response(src_data, status_code=200)

    # 3. Look up in Statutory Tests (A.1, A.4.4, A.4.7, etc.)
    for t_def in ALL_STATUTORY_TESTS:
        if t_def.test_id.upper() == clean_id.upper():
            return success_response(
                {
                    "rule_id": t_def.test_id,
                    "rule_name": t_def.test_name,
                    "source": t_def.source,
                    "category": "STATUTORY_TEST_PROCEDURE",
                    "applicable_when": t_def.applicable_when,
                    "not_applicable_when": t_def.not_applicable_when,
                    "required_inputs": t_def.required_inputs,
                    "manual_review": t_def.manual_review,
                    "priority": t_def.priority,
                    "type": "STATUTORY_TEST_DEFINITION",
                },
                status_code=200,
            )

    # 4. Look up in Accuracy Classes
    for acc_cls in (AccuracyClass.CLASS_I, AccuracyClass.CLASS_II, AccuracyClass.CLASS_III, AccuracyClass.CLASS_IIII):
        if (
            clean_id.upper() in (acc_cls.name, acc_cls.value, f"CLASS_{acc_cls.value}", acc_cls.roman)
            or clean_id.upper() == f"CLASS_{acc_cls.roman}"
        ):
            cls_def = KNOWLEDGE_BASE.get_accuracy_class_definition(acc_cls)
            if cls_def:
                data = cls_def.to_dict()
                data["type"] = "ACCURACY_CLASS_DEFINITION"
                data["rule_id"] = clean_id
                data["class_id"] = clean_id
                data["roman_numeral"] = acc_cls.roman
                return success_response(data, status_code=200)

    # 5. Not found - compile suggestions
    suggestions = [
        "A.1", "A.4.4", "A.4.7", "A.4.8", "A.4.10", "A.4.11.1", "A.5.3",
        "OIML_R76_2006", "IN_LM_2011", "IN_AMR_2011", "IN_GATC_2013",
        "CLASS_I", "CLASS_II", "CLASS_III", "CLASS_IIII",
        "RULE_GATC_CLASS_RESTRICTION", "RULE_FOURTH_AMENDMENT_2026",
    ]

    return error_response(
        code="RULE_NOT_FOUND",
        message=f"Regulatory rule, test, or standard '{clean_id}' was not found in knowledge base or registry.",
        status_code=404,
        details={
            "requested_id": clean_id,
            "suggested_ids": suggestions[:8],
        },
    )


# =============================================================================
# High-Level Facade Class for Person 1 (Team Lead)
# =============================================================================

class RegulatoryAPI:
    """
    Authoritative facade for Person 1 (Team Lead) and external services.
    Provides direct method access and HTTP-like dispatch handling.
    """

    validate_instrument = staticmethod(validate_instrument_api)
    calculate_mpe = staticmethod(calculate_mpe_api)
    determine_applicable_tests = staticmethod(determine_applicable_tests_api)
    generate_test_plan = staticmethod(generate_test_plan_api)
    get_profile = staticmethod(get_regulatory_profile_api)
    get_rule = staticmethod(get_rule_or_source_api)

    @classmethod
    def dispatch(
        cls,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Routes an HTTP-like request path and method to the corresponding service function.

        :param method: 'GET' or 'POST'
        :param path: e.g. '/regulatory/validate-instrument' or '/regulatory/rules/A.4.4'
        :param body: JSON body dictionary for POST requests
        :param params: Optional query parameters
        :return: Standard API response dictionary with status_code and data/error
        """
        clean_method = str(method).upper().strip()
        clean_path = str(path).strip()
        if not clean_path.startswith("/"):
            clean_path = "/" + clean_path

        # Normalize prefix if present
        norm_path = clean_path
        if norm_path.startswith("/api/v1/regulatory"):
            norm_path = norm_path.replace("/api/v1", "", 1)
        elif norm_path.startswith("/api/regulatory"):
            norm_path = norm_path.replace("/api", "", 1)

        # 1. POST /regulatory/validate-instrument
        if norm_path in ("/regulatory/validate-instrument", "/validate-instrument"):
            if clean_method != "POST":
                return error_response("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for {path}. Expected POST.", 405)
            return cls.validate_instrument(body or {})

        # 2. POST /regulatory/mpe
        elif norm_path in ("/regulatory/mpe", "/mpe"):
            if clean_method != "POST":
                return error_response("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for {path}. Expected POST.", 405)
            return cls.calculate_mpe(body or {})

        # 3. POST /regulatory/applicable-tests
        elif norm_path in ("/regulatory/applicable-tests", "/applicable-tests"):
            if clean_method != "POST":
                return error_response("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for {path}. Expected POST.", 405)
            return cls.determine_applicable_tests(body or {})

        # 4. POST /regulatory/test-plan
        elif norm_path in ("/regulatory/test-plan", "/test-plan"):
            if clean_method != "POST":
                return error_response("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for {path}. Expected POST.", 405)
            return cls.generate_test_plan(body or {})

        # 5. GET /regulatory/profile
        elif norm_path in ("/regulatory/profile", "/profile"):
            if clean_method != "GET":
                return error_response("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for {path}. Expected GET.", 405)
            return cls.get_profile()

        # 6. GET /regulatory/rules/{rule_id}
        rule_match = re.match(r"^/(?:regulatory/)?rules/([^/]+)/?$", norm_path)
        if rule_match:
            if clean_method != "GET":
                return error_response("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for {path}. Expected GET.", 405)
            rule_id = rule_match.group(1)
            return cls.get_rule(rule_id)

        return error_response(
            code="ROUTE_NOT_FOUND",
            message=f"Endpoint '{clean_path}' with method '{clean_method}' was not found in Regulatory Engine API.",
            status_code=404,
        )
