"""
MetrIQ Person 3 API Facade & Service Layer
==========================================
Provides clean, consistent, high-level API functions and service interfaces
for Person 1 (Team Lead) and external modules to interact with Person 3's
Instrument Registry, Model Approvals, Test Jobs, Lifecycle Management,
and Verification Scheduling without accessing internal repositories directly.

Endpoints / Operations supported:
---------------------------------
INSTRUMENTS:
- POST   /instruments
- GET    /instruments
- GET    /instruments/{instrument_id}
- PUT    /instruments/{instrument_id}
- PATCH  /instruments/{instrument_id}
- DELETE /instruments/{instrument_id}

MODEL APPROVAL:
- POST   /model-approvals
- GET    /model-approvals
- GET    /model-approvals/{approval_id}
- PUT    /model-approvals/{approval_id}
- PATCH  /model-approvals/{approval_id}

TEST JOBS:
- POST   /test-jobs               (alias: /jobs)
- GET    /test-jobs                (alias: /jobs)
- GET    /test-jobs/{job_id}       (alias: /jobs/{job_id})
- PUT    /test-jobs/{job_id}       (alias: /jobs/{job_id})
- PATCH  /test-jobs/{job_id}       (alias: /jobs/{job_id})
- POST   /test-jobs/{job_id}/validate       (alias: /jobs/{job_id}/validate)
- POST   /test-jobs/{job_id}/generate-plan  (alias: /jobs/{job_id}/generate-plan)
- GET    /test-jobs/{job_id}/test-plan      (alias: /jobs/{job_id}/test-plan)
- POST   /test-jobs/{job_id}/transition     (alias: /jobs/{job_id}/transition)
- POST   /test-jobs/{job_id}/assign         (alias: /jobs/{job_id}/assign)

LIFECYCLE:
- GET    /instruments/{instrument_id}/lifecycle         (alias: /instruments/{id}/lifecycle-history)
- POST   /instruments/{instrument_id}/lifecycle-events

VERIFICATION:
- GET    /instruments/due-for-verification              (alias: /instruments/requiring-verification)
- POST   /instruments/{instrument_id}/verification-job  (alias: /instruments/{id}/create-verification-job)
- POST   /jobs/{job_id}/complete-verification           (alias: /test-jobs/{id}/complete-verification)

Returns structured, standardized response envelopes with HTTP status codes.
"""

from typing import Any, Dict, List, Optional, Union
import re

from app.instruments.service import INSTRUMENT_SERVICE, InstrumentService
from app.jobs.service import TEST_JOB_SERVICE, TestJobService
from app.instruments.model_approval import MODEL_APPROVAL_REGISTRY
from .schemas import (
    success_envelope,
    error_envelope,
    validate_instrument_create_payload,
    validate_test_job_create_payload,
    validate_lifecycle_event_payload,
    validate_model_approval_create_payload,
)


# =============================================================================
# 1. Instrument Service Handlers
# =============================================================================

def api_register_instrument(
    payload: Dict[str, Any],
    enforce_model_approval: bool = True,
) -> Dict[str, Any]:
    """Registers a new weighing instrument after statutory validation."""
    valid, errors = validate_instrument_create_payload(payload)
    if not valid:
        return error_envelope(
            code="VALIDATION_ERROR",
            message="Required instrument registration fields are missing or invalid.",
            status_code=422,
            details=errors,
        )

    res = INSTRUMENT_SERVICE.create_instrument(payload, enforce_model_approval=enforce_model_approval)
    if not res.get("success"):
        return error_envelope(
            code="REGISTRATION_FAILED",
            message=res.get("message", "Instrument registration failed."),
            status_code=res.get("status_code", 400),
            details=res.get("validation_errors"),
        )
    return success_envelope(
        data=res.get("data"),
        status_code=201,
        message=res.get("message", "Instrument registered successfully."),
        meta={
            "regulatory_validation": res.get("regulatory_validation"),
            "model_approval_check": res.get("model_approval_check"),
        },
    )


def api_list_instruments(
    status: Optional[str] = None,
    accuracy_class: Optional[str] = None,
    instrument_type: Optional[str] = None,
    usage_type: Optional[str] = None,
    verification_status: Optional[str] = None,
    approval_status: Optional[str] = None,
    gatc_code: Optional[str] = None,
    manufacturer: Optional[str] = None,
    customer: Optional[str] = None,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    """Lists instruments matching query criteria."""
    items = INSTRUMENT_SERVICE.list_instruments(
        status=status,
        accuracy_class=accuracy_class,
        instrument_type=instrument_type,
        usage_type=usage_type,
        verification_status=verification_status,
        approval_status=approval_status,
        gatc_code=gatc_code,
        manufacturer=manufacturer,
        customer_name=customer,
        search=search,
    )
    return success_envelope(
        data=items,
        status_code=200,
        meta={"count": len(items)},
    )


def api_get_instrument(instrument_id: str) -> Dict[str, Any]:
    """Retrieves full details of an instrument with live operational status evaluation."""
    inst = INSTRUMENT_SERVICE.get_instrument(instrument_id)
    if not inst:
        return error_envelope(
            code="INSTRUMENT_NOT_FOUND",
            message=f"Instrument '{instrument_id}' not found in registry.",
            status_code=404,
        )
    return success_envelope(data=inst, status_code=200)


def api_update_instrument(instrument_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Updates an instrument specification (PUT/PATCH)."""
    res = INSTRUMENT_SERVICE.update_instrument(instrument_id, payload)
    if not res.get("success"):
        return error_envelope(
            code="UPDATE_FAILED",
            message=res.get("message", f"Failed to update instrument '{instrument_id}'."),
            status_code=res.get("status_code", 400),
            details=res.get("validation_errors"),
        )
    return success_envelope(
        data=res.get("data"),
        status_code=200,
        message=res.get("message", f"Instrument '{instrument_id}' updated successfully."),
    )


def api_delete_instrument(instrument_id: str) -> Dict[str, Any]:
    """Removes an instrument from the registry."""
    ok = INSTRUMENT_SERVICE.delete_instrument(instrument_id)
    if not ok:
        return error_envelope(
            code="INSTRUMENT_NOT_FOUND",
            message=f"Instrument '{instrument_id}' not found for deletion.",
            status_code=404,
        )
    return success_envelope(
        data={"instrument_id": instrument_id},
        status_code=200,
        message=f"Instrument '{instrument_id}' successfully deleted.",
    )


# =============================================================================
# 2. Model Approval Handlers
# =============================================================================

def api_register_model_approval(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Registers a statutory Model Approval Record."""
    valid, errors = validate_model_approval_create_payload(payload)
    if not valid:
        return error_envelope(
            code="VALIDATION_ERROR",
            message="Required model approval fields are missing or invalid.",
            status_code=422,
            details=errors,
        )

    res = INSTRUMENT_SERVICE.create_model_approval(payload)
    if not res.get("success"):
        return error_envelope(
            code="REGISTRATION_FAILED",
            message=res.get("message", "Model approval registration failed."),
            status_code=res.get("status_code", 400),
        )
    return success_envelope(
        data=res.get("data"),
        status_code=201,
        message=res.get("message", "Model approval registered successfully."),
    )


def api_list_model_approvals(
    manufacturer: Optional[str] = None,
    accuracy_class: Optional[str] = None,
    status: Optional[str] = None,
    instrument_type: Optional[str] = None,
    search: Optional[str] = None,
    valid_only: bool = False,
) -> Dict[str, Any]:
    """Lists registered Model Approval records."""
    records = INSTRUMENT_SERVICE.list_model_approvals(
        manufacturer=manufacturer,
        accuracy_class=accuracy_class,
        status=status,
        instrument_type=instrument_type,
        search=search,
        valid_only=valid_only,
    )
    return success_envelope(
        data=records,
        status_code=200,
        meta={"count": len(records)},
    )


def api_get_model_approval(approval_id: str) -> Dict[str, Any]:
    """Retrieves a specific Model Approval by approval_id, reference, or approval_number."""
    record = INSTRUMENT_SERVICE.get_model_approval(approval_id)
    if not record:
        return error_envelope(
            code="MODEL_APPROVAL_NOT_FOUND",
            message=f"Model approval '{approval_id}' not found.",
            status_code=404,
        )
    return success_envelope(data=record, status_code=200)


def api_update_model_approval(approval_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Updates a Model Approval record (PUT/PATCH)."""
    res = INSTRUMENT_SERVICE.update_model_approval(approval_id, payload)
    if not res.get("success"):
        return error_envelope(
            code="UPDATE_FAILED",
            message=res.get("message", f"Failed to update model approval '{approval_id}'."),
            status_code=res.get("status_code", 400),
        )
    return success_envelope(
        data=res.get("data"),
        status_code=200,
        message=res.get("message", f"Model approval '{approval_id}' updated successfully."),
    )


# =============================================================================
# 3. Test Job Handlers
# =============================================================================

def api_create_test_job(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Creates a statutory verification test job with routing and test plan generation."""
    valid, errors = validate_test_job_create_payload(payload)
    if not valid:
        return error_envelope(
            code="VALIDATION_ERROR",
            message="Required test job fields are missing or invalid.",
            status_code=422,
            details=errors,
        )

    res = TEST_JOB_SERVICE.create_job(payload)
    if not res.get("success"):
        return error_envelope(
            code="JOB_CREATION_FAILED",
            message=res.get("message", "Failed to create test job."),
            status_code=res.get("status_code", 400),
            details={"active_job_ids": res.get("active_job_ids")} if res.get("active_job_ids") else None,
        )
    return success_envelope(
        data=res.get("data"),
        status_code=201,
        message=res.get("message", "Test job created successfully."),
        meta={
            "job_id": res.get("job_id"),
            "job_number": res.get("job_number"),
            "status": res.get("status"),
            "job_type": res.get("job_type"),
            "has_test_plan": res.get("has_test_plan"),
            "test_plan_reference": res.get("test_plan_reference"),
            "statutory_routing": res.get("statutory_routing"),
        },
    )


def api_list_test_jobs(
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    instrument_id: Optional[str] = None,
    inspector_id: Optional[str] = None,
    testing_centre_id: Optional[str] = None,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    """Lists test jobs with multi-parameter filtering."""
    jobs = TEST_JOB_SERVICE.list_jobs(
        status=status,
        job_type=job_type,
        instrument_id=instrument_id,
        inspector_id=inspector_id,
        testing_centre_id=testing_centre_id,
        search=search,
    )
    return success_envelope(
        data=jobs,
        status_code=200,
        meta={"count": len(jobs)},
    )


def api_get_test_job(job_id: str) -> Dict[str, Any]:
    """Retrieves full details of a test job."""
    job = TEST_JOB_SERVICE.get_job(job_id)
    if not job:
        return error_envelope(
            code="JOB_NOT_FOUND",
            message=f"Test job '{job_id}' not found.",
            status_code=404,
        )
    return success_envelope(data=job, status_code=200)


def api_update_test_job(
    job_id: str,
    payload: Dict[str, Any],
    updated_by: str = "SYSTEM",
) -> Dict[str, Any]:
    """Updates an existing test job (PUT/PATCH)."""
    res = TEST_JOB_SERVICE.update_job(job_id, payload, updated_by=updated_by)
    if not res.get("success"):
        return error_envelope(
            code="JOB_UPDATE_FAILED",
            message=res.get("message", f"Failed to update test job '{job_id}'."),
            status_code=res.get("status_code", 400),
        )
    return success_envelope(
        data=res.get("data"),
        status_code=200,
        message=res.get("message", f"Job '{job_id}' updated successfully."),
    )


def api_validate_test_job(job_id: str, user_id: str = "SYSTEM") -> Dict[str, Any]:
    """Performs comprehensive pre-test statutory validation on a test job."""
    res = TEST_JOB_SERVICE.validate_job(job_id, user_id=user_id)
    if not res.get("success"):
        return error_envelope(
            code="VALIDATION_FAILED",
            message=res.get("message", f"Job '{job_id}' statutory validation failed."),
            status_code=res.get("status_code", 400),
        )
    return success_envelope(
        data=res.get("data"),
        status_code=200,
        message=f"Statutory validation completed for job '{job_id}'.",
    )


def api_generate_job_test_plan(
    job_id: str,
    user_id: str = "SYSTEM",
    force_regenerate: bool = False,
) -> Dict[str, Any]:
    """Generates or re-generates statutory test plan for a test job via Person 2 engine."""
    res = TEST_JOB_SERVICE.generate_job_test_plan(job_id, user_id=user_id, force_regenerate=force_regenerate)
    if not res.get("success"):
        return error_envelope(
            code="TEST_PLAN_GENERATION_FAILED",
            message=res.get("message", f"Failed to generate test plan for job '{job_id}'."),
            status_code=res.get("status_code", 400),
        )
    return success_envelope(
        data=res.get("data"),
        status_code=200,
        message=res.get("message", f"Test plan generated for job '{job_id}'."),
        meta={
            "job_id": res.get("job_id"),
            "test_plan_reference": res.get("test_plan_reference"),
            "status": res.get("status"),
        },
    )


def api_get_job_test_plan(job_id: str) -> Dict[str, Any]:
    """Endpoint for Person 4 (Test Execution Engine) to retrieve statutory test plan."""
    plan = TEST_JOB_SERVICE.get_job_test_plan(job_id)
    if not plan:
        return error_envelope(
            code="TEST_PLAN_NOT_FOUND",
            message=f"Test plan not found or not yet generated for job '{job_id}'.",
            status_code=404,
        )
    return success_envelope(
        data=plan,
        status_code=200,
        meta={"job_id": job_id},
    )


# =============================================================================
# 4. Lifecycle & Verification Handlers
# =============================================================================

def api_get_instrument_lifecycle(instrument_id: str) -> Dict[str, Any]:
    """Retrieves full immutable statutory lifecycle history for an instrument."""
    res = INSTRUMENT_SERVICE.get_instrument_lifecycle_history(instrument_id)
    if not res.get("success"):
        return error_envelope(
            code="INSTRUMENT_NOT_FOUND",
            message=res.get("message", f"Instrument '{instrument_id}' not found."),
            status_code=res.get("status_code", 404),
        )
    return success_envelope(
        data=res.get("data"),
        status_code=200,
        meta={
            "instrument_id": instrument_id,
            "event_count": res.get("event_count", len(res.get("data", []))),
        },
    )


def api_record_lifecycle_event(instrument_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Records a statutory lifecycle event with state transition validation."""
    valid, errors = validate_lifecycle_event_payload(payload)
    if not valid:
        return error_envelope(
            code="VALIDATION_ERROR",
            message="Required lifecycle event fields are missing or invalid.",
            status_code=422,
            details=errors,
        )

    res = INSTRUMENT_SERVICE.record_lifecycle_event(
        instrument_id=instrument_id,
        event_type=payload["event_type"],
        new_status=payload["new_status"],
        actor=payload.get("actor", "SYSTEM"),
        event_date=payload.get("event_date"),
        related_job_id=payload.get("related_job_id"),
        notes=payload.get("notes", ""),
        metadata=payload.get("metadata"),
    )
    if not res.get("success"):
        return error_envelope(
            code="LIFECYCLE_TRANSITION_REJECTED",
            message=res.get("message", "Lifecycle event transition was rejected."),
            status_code=res.get("status_code", 400),
        )
    return success_envelope(
        data=res.get("data"),
        status_code=200,
        message=res.get("message", "Lifecycle event recorded successfully."),
    )


def api_get_due_for_verification(
    as_of_date: Optional[str] = None,
    state: Optional[str] = None,
    reminder_window_days: int = 30,
    include_manual_review: bool = True,
) -> Dict[str, Any]:
    """Identifies all instruments currently requiring statutory verification."""
    res = INSTRUMENT_SERVICE.identify_instruments_requiring_verification(
        as_of_date=as_of_date,
        state=state,
        reminder_window_days=reminder_window_days,
        include_manual_review=include_manual_review,
    )
    return success_envelope(
        data=res.get("instruments", []),
        status_code=200,
        meta={
            "counts": res.get("counts", {}),
            "as_of_date": res.get("as_of_date"),
            "reminder_window_days": res.get("reminder_window_days"),
        },
    )


def api_create_verification_job(instrument_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Provisions a verification test job and binds it to the instrument."""
    res = INSTRUMENT_SERVICE.create_verification_job(
        instrument_id=instrument_id,
        job_type=payload.get("job_type", "RE_VERIFICATION"),
        reason=payload.get("reason") or payload.get("verification_reason", "PERIODIC_EXPIRY"),
        scheduled_date=payload.get("scheduled_date"),
        user_id=payload.get("user_id") or payload.get("created_by", "SYSTEM"),
        priority=payload.get("priority"),
        notes=payload.get("notes", ""),
        inspector_id=payload.get("inspector_id"),
        inspector_name=payload.get("inspector_name"),
        testing_centre_name=payload.get("testing_centre_name"),
    )
    if not res.get("success"):
        return error_envelope(
            code="VERIFICATION_JOB_CREATION_FAILED",
            message=res.get("message", "Failed to create verification job."),
            status_code=res.get("status_code", 400),
        )
    return success_envelope(
        data=res.get("data"),
        status_code=201,
        message=res.get("message", "Verification job created successfully."),
        meta={"job_id": res.get("job_id"), "instrument_id": instrument_id},
    )


def api_complete_verification_job(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronizes verification outcome, certificate number, and next re-verification due date."""
    outcome = payload.get("outcome") or payload.get("job_outcome", "PASSED")
    cert_num = payload.get("certificate_number") or payload.get("verification_certificate_number")
    res = INSTRUMENT_SERVICE.complete_verification_job(
        job_id=job_id,
        outcome=outcome,
        certificate_number=cert_num,
        verification_date=payload.get("verification_date"),
        inspecting_officer=payload.get("inspecting_officer") or payload.get("completed_by"),
        stamping_authority=payload.get("stamping_authority"),
        metadata=payload.get("metadata"),
    )
    if not res.get("success"):
        return error_envelope(
            code="COMPLETION_SYNC_FAILED",
            message=res.get("message", "Failed to complete verification job synchronization."),
            status_code=res.get("status_code", 400),
        )
    return success_envelope(
        data=res.get("data"),
        status_code=200,
        message=res.get("message", f"Verification job '{job_id}' completed and instrument synchronized."),
    )


# =============================================================================
# Unified Person 3 API Facade Class
# =============================================================================

class Person3API:
    """
    Authoritative facade for Person 1 (Team Lead), Person 4, and Person 5.
    Provides direct method access and HTTP-like dispatch handling for all Person 3 APIs.
    """

    # Direct Method Aliases
    register_instrument = staticmethod(api_register_instrument)
    list_instruments = staticmethod(api_list_instruments)
    get_instrument = staticmethod(api_get_instrument)
    update_instrument = staticmethod(api_update_instrument)
    delete_instrument = staticmethod(api_delete_instrument)

    register_model_approval = staticmethod(api_register_model_approval)
    list_model_approvals = staticmethod(api_list_model_approvals)
    get_model_approval = staticmethod(api_get_model_approval)
    update_model_approval = staticmethod(api_update_model_approval)

    create_test_job = staticmethod(api_create_test_job)
    list_test_jobs = staticmethod(api_list_test_jobs)
    get_test_job = staticmethod(api_get_test_job)
    update_test_job = staticmethod(api_update_test_job)
    validate_test_job = staticmethod(api_validate_test_job)
    generate_job_test_plan = staticmethod(api_generate_job_test_plan)
    get_job_test_plan = staticmethod(api_get_job_test_plan)

    get_instrument_lifecycle = staticmethod(api_get_instrument_lifecycle)
    record_lifecycle_event = staticmethod(api_record_lifecycle_event)

    get_due_for_verification = staticmethod(api_get_due_for_verification)
    create_verification_job = staticmethod(api_create_verification_job)
    complete_verification_job = staticmethod(api_complete_verification_job)

    @classmethod
    def dispatch(
        cls,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Routes an HTTP-like request path and method to the corresponding service handler.

        :param method: 'GET', 'POST', 'PUT', 'PATCH', or 'DELETE'
        :param path: Canonical API path (e.g. '/instruments', '/test-jobs/JOB-1/validate')
        :param body: JSON dictionary body for write operations
        :param params: Optional query parameters dictionary
        :return: Standard response envelope with status_code and data/error
        """
        clean_method = str(method).upper().strip()
        clean_path = str(path).strip()
        if not clean_path.startswith("/"):
            clean_path = "/" + clean_path

        # Normalize prefix if present (e.g. /api/v1/...)
        norm_path = re.sub(r"^/api(?:/v\d+)?", "", clean_path)
        body = body or {}
        params = params or {}

        # ---------------------------------------------------------------------
        # 1. INSTRUMENTS Endpoints
        # ---------------------------------------------------------------------
        if norm_path == "/instruments":
            if clean_method == "POST":
                enforce_ma = params.get("enforce_model_approval", True)
                return cls.register_instrument(body, enforce_model_approval=enforce_ma)
            elif clean_method == "GET":
                return cls.list_instruments(
                    status=params.get("status"),
                    accuracy_class=params.get("accuracy_class"),
                    instrument_type=params.get("instrument_type"),
                    usage_type=params.get("usage_type"),
                    verification_status=params.get("verification_status"),
                    approval_status=params.get("approval_status"),
                    gatc_code=params.get("gatc_code"),
                    manufacturer=params.get("manufacturer"),
                    customer=params.get("customer"),
                    search=params.get("search"),
                )
            else:
                return error_envelope("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for /instruments.", 405)

        # Verification Due
        if norm_path in ("/instruments/due-for-verification", "/instruments/requiring-verification"):
            if clean_method == "GET":
                return cls.get_due_for_verification(
                    as_of_date=params.get("as_of_date"),
                    state=params.get("state"),
                    reminder_window_days=int(params.get("reminder_window_days", 30)),
                    include_manual_review=bool(params.get("include_manual_review", True)),
                )
            return error_envelope("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for {norm_path}.", 405)

        # /instruments/{id}/verification-job
        m_vjob = re.match(r"^/instruments/([^/]+)/(?:verification-job|create-verification-job)/?$", norm_path)
        if m_vjob:
            if clean_method == "POST":
                return cls.create_verification_job(m_vjob.group(1), body)
            return error_envelope("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for verification job creation.", 405)

        # /instruments/{id}/lifecycle
        m_life = re.match(r"^/instruments/([^/]+)/(?:lifecycle|lifecycle-history)/?$", norm_path)
        if m_life:
            if clean_method == "GET":
                return cls.get_instrument_lifecycle(m_life.group(1))
            return error_envelope("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for lifecycle query.", 405)

        # /instruments/{id}/lifecycle-events
        m_events = re.match(r"^/instruments/([^/]+)/lifecycle-events/?$", norm_path)
        if m_events:
            if clean_method == "POST":
                return cls.record_lifecycle_event(m_events.group(1), body)
            return error_envelope("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for lifecycle event creation.", 405)

        # /instruments/{id}
        m_inst = re.match(r"^/instruments/([^/]+)/?$", norm_path)
        if m_inst:
            inst_id = m_inst.group(1)
            if clean_method == "GET":
                return cls.get_instrument(inst_id)
            elif clean_method in ("PUT", "PATCH"):
                return cls.update_instrument(inst_id, body)
            elif clean_method == "DELETE":
                return cls.delete_instrument(inst_id)
            else:
                return error_envelope("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for /instruments/{inst_id}.", 405)

        # ---------------------------------------------------------------------
        # 2. MODEL APPROVALS Endpoints
        # ---------------------------------------------------------------------
        if norm_path == "/model-approvals":
            if clean_method == "POST":
                return cls.register_model_approval(body)
            elif clean_method == "GET":
                return cls.list_model_approvals(
                    manufacturer=params.get("manufacturer"),
                    accuracy_class=params.get("accuracy_class"),
                    status=params.get("status"),
                    instrument_type=params.get("instrument_type"),
                    search=params.get("search"),
                    valid_only=bool(params.get("valid_only", False)),
                )
            else:
                return error_envelope("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for /model-approvals.", 405)

        m_ma = re.match(r"^/model-approvals/([^/]+)/?$", norm_path)
        if m_ma:
            ma_id = m_ma.group(1)
            if clean_method == "GET":
                return cls.get_model_approval(ma_id)
            elif clean_method in ("PUT", "PATCH"):
                return cls.update_model_approval(ma_id, body)
            else:
                return error_envelope("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for /model-approvals/{ma_id}.", 405)

        # ---------------------------------------------------------------------
        # 3. TEST JOBS Endpoints (/test-jobs and /jobs)
        # ---------------------------------------------------------------------
        if norm_path in ("/test-jobs", "/jobs"):
            if clean_method == "POST":
                return cls.create_test_job(body)
            elif clean_method == "GET":
                return cls.list_test_jobs(
                    status=params.get("status"),
                    job_type=params.get("job_type"),
                    instrument_id=params.get("instrument_id"),
                    inspector_id=params.get("inspector_id"),
                    testing_centre_id=params.get("testing_centre_id"),
                    search=params.get("search"),
                )
            else:
                return error_envelope("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for {norm_path}.", 405)

        # /test-jobs/{id}/validate
        m_val = re.match(r"^/(?:test-jobs|jobs)/([^/]+)/validate/?$", norm_path)
        if m_val:
            if clean_method == "POST":
                return cls.validate_test_job(m_val.group(1), user_id=body.get("user_id", "SYSTEM"))
            return error_envelope("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for job validation.", 405)

        # /test-jobs/{id}/generate-plan
        m_gp = re.match(r"^/(?:test-jobs|jobs)/([^/]+)/generate-plan/?$", norm_path)
        if m_gp:
            if clean_method == "POST":
                return cls.generate_job_test_plan(
                    m_gp.group(1),
                    user_id=body.get("user_id", "SYSTEM"),
                    force_regenerate=bool(body.get("force_regenerate", False)),
                )
            return error_envelope("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for test plan generation.", 405)

        # /test-jobs/{id}/test-plan
        m_tp = re.match(r"^/(?:test-jobs|jobs)/([^/]+)/test-plan/?$", norm_path)
        if m_tp:
            if clean_method == "GET":
                return cls.get_job_test_plan(m_tp.group(1))
            return error_envelope("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for test plan retrieval.", 405)

        # /test-jobs/{id}/transition
        m_trans = re.match(r"^/(?:test-jobs|jobs)/([^/]+)/transition/?$", norm_path)
        if m_trans:
            if clean_method == "POST":
                to_status = body.get("to_status")
                if not to_status:
                    return error_envelope("VALIDATION_ERROR", "Missing required field 'to_status'.", 422)
                res = TEST_JOB_SERVICE.transition_job_status(
                    job_id=m_trans.group(1),
                    to_status=to_status,
                    user_id=body.get("user_id", "SYSTEM"),
                    reason=body.get("reason", ""),
                    metadata=body.get("metadata"),
                )
                if not res.get("success"):
                    return error_envelope("TRANSITION_FAILED", res.get("message", "Job status transition failed."), res.get("status_code", 400))
                return success_envelope(data=res.get("data"), status_code=200, message=res.get("message"))
            return error_envelope("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for transition.", 405)

        # /test-jobs/{id}/assign
        m_asn = re.match(r"^/(?:test-jobs|jobs)/([^/]+)/assign/?$", norm_path)
        if m_asn:
            if clean_method == "POST":
                insp_id = body.get("inspector_id")
                insp_name = body.get("inspector_name")
                if not insp_id or not insp_name:
                    return error_envelope("VALIDATION_ERROR", "Fields 'inspector_id' and 'inspector_name' are required.", 422)
                res = TEST_JOB_SERVICE.assign_inspector(
                    job_id=m_asn.group(1),
                    inspector_id=insp_id,
                    inspector_name=insp_name,
                    testing_centre_id=body.get("testing_centre_id"),
                    testing_centre_name=body.get("testing_centre_name"),
                    scheduled_date=body.get("scheduled_date"),
                    assigned_by=body.get("assigned_by", "SYSTEM"),
                    verification_location_type=body.get("verification_location_type"),
                    gatc_reference=body.get("gatc_reference"),
                )
                if not res.get("success"):
                    return error_envelope("ASSIGNMENT_FAILED", res.get("message", "Inspector assignment failed."), res.get("status_code", 400))
                return success_envelope(data=res.get("data"), status_code=200, message=res.get("message"))
            return error_envelope("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for assign.", 405)

        # /jobs/{id}/complete-verification
        m_comp = re.match(r"^/(?:test-jobs|jobs)/([^/]+)/complete-verification/?$", norm_path)
        if m_comp:
            if clean_method == "POST":
                return cls.complete_verification_job(m_comp.group(1), body)
            return error_envelope("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for verification completion.", 405)

        # /test-jobs/{id} or /jobs/{id}
        m_job = re.match(r"^/(?:test-jobs|jobs)/([^/]+)/?$", norm_path)
        if m_job:
            job_id = m_job.group(1)
            if clean_method == "GET":
                return cls.get_test_job(job_id)
            elif clean_method in ("PUT", "PATCH"):
                return cls.update_test_job(job_id, body)
            else:
                return error_envelope("METHOD_NOT_ALLOWED", f"Method {clean_method} not allowed for test job.", 405)

        return error_envelope(
            code="ROUTE_NOT_FOUND",
            message=f"Endpoint '{clean_path}' with method '{clean_method}' was not found in Person 3 API.",
            status_code=404,
        )
