"""
MetrIQ API Schemas — Person 3 (Job / Instrument Engineer)
=========================================================
Request schemas, validation definitions, and response envelopes for:
- Instruments (Registry, Specifications, Physical Seals)
- Model Approval Certificates (Pattern Approvals)
- Test Jobs (Creation, Scheduling, Validation, Plan Generation)
- Lifecycle Events (Traceable State Transitions)
- Verification Scheduling & Sync

Provides both Pydantic model definitions (when pydantic is available)
and standard Python validation helpers with consistent error formatting.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from pydantic import BaseModel, Field, validator
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    BaseModel = object  # type: ignore
    Field = lambda *args, **kwargs: None  # type: ignore


# =============================================================================
# Standard Response Envelopes
# =============================================================================

def iso_timestamp() -> str:
    """Returns the current UTC ISO-8601 timestamp string."""
    return datetime.now(timezone.utc).isoformat()


def success_envelope(
    data: Any,
    status_code: int = 200,
    message: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Builds a consistent, structured success response envelope."""
    payload: Dict[str, Any] = {
        "success": True,
        "status_code": status_code,
        "data": data,
        "timestamp": iso_timestamp(),
    }
    if message:
        payload["message"] = message
    if meta:
        payload["meta"] = meta
    return payload


def error_envelope(
    code: str,
    message: str,
    status_code: int = 400,
    details: Optional[Any] = None,
) -> Dict[str, Any]:
    """Builds a consistent, structured error response envelope without leaking internal traces."""
    err_body: Dict[str, Any] = {
        "code": str(code).strip().upper(),
        "message": str(message),
    }
    if details is not None:
        err_body["details"] = details
    return {
        "success": False,
        "status_code": status_code,
        "error": err_body,
        "timestamp": iso_timestamp(),
    }


# =============================================================================
# Request Validation Helpers (Pure Python & Pydantic-Ready)
# =============================================================================

def validate_instrument_create_payload(data: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
    """Validates required fields and types for instrument registration."""
    errors: List[Dict[str, Any]] = []
    if not isinstance(data, dict):
        return False, [{"field": "body", "issue": "Payload must be a JSON object."}]

    # Identity
    if not data.get("serial_number"):
        errors.append({"field": "serial_number", "issue": "Field 'serial_number' is required."})
    if not data.get("model_number") and not data.get("model_name"):
        errors.append({"field": "model_number", "issue": "Field 'model_number' is required."})
    if not data.get("manufacturer"):
        errors.append({"field": "manufacturer", "issue": "Field 'manufacturer' is required."})

    # Metrology
    if not data.get("accuracy_class"):
        errors.append({"field": "accuracy_class", "issue": "Field 'accuracy_class' is required."})
    
    max_c = data.get("max_capacity") if data.get("max_capacity") is not None else data.get("Max")
    if max_c is None:
        errors.append({"field": "Max", "issue": "Field 'Max' (max_capacity) is required."})
    else:
        try:
            if float(max_c) <= 0:
                errors.append({"field": "Max", "issue": "Max capacity must be greater than zero."})
        except (ValueError, TypeError):
            errors.append({"field": "Max", "issue": "Max capacity must be numeric."})

    e_val = data.get("e")
    if e_val is None:
        errors.append({"field": "e", "issue": "Field 'e' (verification scale interval) is required."})
    else:
        try:
            if float(e_val) <= 0:
                errors.append({"field": "e", "issue": "Scale interval 'e' must be positive."})
        except (ValueError, TypeError):
            errors.append({"field": "e", "issue": "Field 'e' must be numeric."})

    return len(errors) == 0, errors


def validate_test_job_create_payload(data: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
    """Validates required fields and types for test job creation."""
    errors: List[Dict[str, Any]] = []
    if not isinstance(data, dict):
        return False, [{"field": "body", "issue": "Payload must be a JSON object."}]

    if not data.get("instrument_id"):
        errors.append({"field": "instrument_id", "issue": "Field 'instrument_id' is required."})

    return len(errors) == 0, errors


def validate_lifecycle_event_payload(data: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
    """Validates required fields for lifecycle event creation."""
    errors: List[Dict[str, Any]] = []
    if not isinstance(data, dict):
        return False, [{"field": "body", "issue": "Payload must be a JSON object."}]

    if not data.get("event_type"):
        errors.append({"field": "event_type", "issue": "Field 'event_type' is required."})
    if not data.get("new_status"):
        errors.append({"field": "new_status", "issue": "Field 'new_status' is required."})

    return len(errors) == 0, errors


def validate_model_approval_create_payload(data: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
    """Validates required fields for model approval registration."""
    errors: List[Dict[str, Any]] = []
    if not isinstance(data, dict):
        return False, [{"field": "body", "issue": "Payload must be a JSON object."}]

    if not data.get("application_reference") and not data.get("approval_number"):
        errors.append({"field": "application_reference", "issue": "Field 'application_reference' is required."})
    if not data.get("manufacturer"):
        errors.append({"field": "manufacturer", "issue": "Field 'manufacturer' is required."})
    if not data.get("model_number") and not data.get("model_name"):
        errors.append({"field": "model_number", "issue": "Field 'model_number' is required."})
    if not data.get("accuracy_class") and not data.get("accuracy_classes"):
        errors.append({"field": "accuracy_class", "issue": "Field 'accuracy_class' is required."})

    return len(errors) == 0, errors
