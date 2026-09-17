"""
MetrIQ Instruments API Router — Person 3 (Job / Instrument Engineer)
====================================================================
Exposes RESTful endpoints for Weighing Instrument Registry, Model Approval
Certificates, Physical Seals, and Metrological Pre-validation.
"""

try:
    from fastapi import APIRouter, Body, HTTPException, Path, Query, status
    HAS_FASTAPI = True
    router = APIRouter(tags=["Instruments & Model Approvals"])
    _post = router.post
    _get = router.get
    _put = router.put
    _patch = router.patch
    _delete = router.delete
except ImportError:
    HAS_FASTAPI = False
    router = None
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: Any):
            self.status_code = status_code
            self.detail = detail
            super().__init__(f"HTTP {status_code}: {detail}")
    class _DummyStatus:
        HTTP_201_CREATED = 201
        HTTP_200_OK = 200
        HTTP_400_BAD_REQUEST = 400
        HTTP_404_NOT_FOUND = 404
        HTTP_422_UNPROCESSABLE_ENTITY = 422
    status = _DummyStatus()
    def Body(default=..., **kwargs):
        return default
    def Query(default=None, **kwargs):
        return default
    def Path(default=..., **kwargs):
        return default
    def _noop_dec(*args, **kwargs):
        def wrap(f):
            return f
        return wrap
    _post = _get = _put = _patch = _delete = _noop_dec

from app.instruments.service import INSTRUMENT_SERVICE, InstrumentService
from app.instruments.model_approval import MODEL_APPROVAL_REGISTRY, ModelApprovalCertificate
from app.instruments.models import Instrument


# =============================================================================
# Instrument Registry Endpoints
# =============================================================================

@_post("/instruments", status_code=status.HTTP_201_CREATED)
def register_instrument(
    payload: Dict[str, Any] = Body(..., description="Complete instrument metrological and physical specification"),
    enforce_model_approval: bool = Query(True, description="Strictly reject if model approval envelope is violated"),
):
    """
    Registers a new weighing instrument:
    - Validates metrology via Person 2 Regulatory Engine.
    - Validates against Model Approval envelope if declared.
    - Computes next statutory re-verification date.
    - Persists into registry.
    """
    res = INSTRUMENT_SERVICE.create_instrument(payload, enforce_model_approval=enforce_model_approval)
    if not res.get("success"):
        code = res.get("status_code", 400)
        raise HTTPException(status_code=code, detail=res)
    return res


@_get("/instruments")
def list_instruments(
    status: Optional[str] = Query(None, description="Filter by operational status (ACTIVE, RE_VERIFICATION_DUE, etc.)"),
    accuracy_class: Optional[str] = Query(None, description="Filter by accuracy class (I, II, III, IIII)"),
    instrument_type: Optional[str] = Query(None, description="Filter by instrument type"),
    usage_type: Optional[str] = Query(None, description="Filter by usage type"),
    verification_status: Optional[str] = Query(None, description="Filter by verification status"),
    approval_status: Optional[str] = Query(None, description="Filter by approval status"),
    gatc_code: Optional[str] = Query(None, description="Filter by GATC test centre code"),
    manufacturer: Optional[str] = Query(None, description="Filter by manufacturer name substring"),
    customer: Optional[str] = Query(None, description="Filter by customer name substring"),
    search: Optional[str] = Query(None, description="Search across ID, serial number, model, customer, description"),
):
    """Lists registered instruments matching search criteria."""
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
    return {
        "success": True,
        "count": len(items),
        "data": items,
    }


@_get("/instruments/by-serial/{serial_number}")
def get_instrument_by_serial(
    serial_number: str = Path(..., description="Unique manufacturer serial number"),
):
    """Retrieves an instrument by its unique serial number."""
    inst = INSTRUMENT_SERVICE.get_by_serial(serial_number)
    if not inst:
        raise HTTPException(status_code=404, detail=f"Instrument with serial '{serial_number}' not found.")
    return {
        "success": True,
        "data": inst,
    }


@_get("/instruments/due-for-verification")
@_get("/instruments/requiring-verification")
def identify_instruments_requiring_verification(
    as_of_date: Optional[str] = Query(None, description="Reference date for due/overdue check (YYYY-MM-DD)"),
    state: Optional[str] = Query(None, description="Filter by Indian State/UT location"),
    reminder_window_days: int = Query(30, description="Notice window in days before deadline"),
    include_manual_review: bool = Query(True, description="Include instruments requiring manual interval review"),
):
    """Identifies all instruments currently requiring statutory verification."""
    return INSTRUMENT_SERVICE.identify_instruments_requiring_verification(
        as_of_date=as_of_date,
        state=state,
        reminder_window_days=reminder_window_days,
        include_manual_review=include_manual_review,
    )


@_get("/instruments/{instrument_id}")
def get_instrument_details(
    instrument_id: str = Path(..., description="Unique instrument identifier"),
):
    """Retrieves full specification, physical seals, and live status of an instrument."""
    inst = INSTRUMENT_SERVICE.get_instrument(instrument_id)
    if not inst:
        raise HTTPException(status_code=404, detail=f"Instrument '{instrument_id}' not found.")
    return {
        "success": True,
        "data": inst,
    }


@_put("/instruments/{instrument_id}")
@_patch("/instruments/{instrument_id}")
def update_instrument(
    instrument_id: str = Path(...),
    payload: Dict[str, Any] = Body(...),
):
    """Updates instrument specification; re-validates with Person 2 if metrology changed."""
    res = INSTRUMENT_SERVICE.update_instrument(instrument_id, payload)
    if not res.get("success"):
        raise HTTPException(status_code=res.get("status_code", 400), detail=res)
    return res


@_delete("/instruments/{instrument_id}")
def delete_instrument(instrument_id: str = Path(...)):
    """Deletes an instrument from the registry."""
    ok = INSTRUMENT_SERVICE.delete_instrument(instrument_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Instrument '{instrument_id}' not found.")
    return {"success": True, "message": f"Instrument '{instrument_id}' deleted."}


@_post("/instruments/validate-feasibility")
def pre_validate_instrument(
    payload: Dict[str, Any] = Body(..., description="Instrument metrology to validate"),
):
    """Statutory pre-check of instrument parameters via Person 2 without saving to registry."""
    res = INSTRUMENT_SERVICE.validate_metrology(payload)
    return res


# =============================================================================
# Statutory Physical & Electronic Seal Endpoints
# =============================================================================

@_post("/instruments/{instrument_id}/seals")
def apply_seal(
    instrument_id: str = Path(...),
    seal_payload: Dict[str, Any] = Body(...),
):
    """Applies a verification seal to an instrument."""
    res = INSTRUMENT_SERVICE.add_seal(instrument_id, seal_payload)
    if not res.get("success"):
        raise HTTPException(status_code=res.get("status_code", 400), detail=res)
    return res


@_post("/instruments/{instrument_id}/seals/report-broken")
def report_broken_seal(
    instrument_id: str = Path(...),
    seal_id: str = Body(..., embed=True),
    reason: str = Body("Tampered or broken during maintenance", embed=True),
    reported_by: str = Body("Inspector / Owner", embed=True),
):
    """
    Reports a broken statutory seal.
    Immediately invalidates commercial trade eligibility and sets status to REPAIR_REQUIRED.
    """
    res = INSTRUMENT_SERVICE.report_broken_seal(instrument_id, seal_id, reason, reported_by)
    if not res.get("success"):
        raise HTTPException(status_code=res.get("status_code", 400), detail=res)
    return res


# =============================================================================
# Model Approval (Pattern Approval) Endpoints
# =============================================================================

@_post("/model-approvals", status_code=status.HTTP_201_CREATED)
def register_model_approval(
    payload: Dict[str, Any] = Body(...),
):
    """Registers a statutory Model Approval Record under Legal Metrology Rules 2011."""
    res = INSTRUMENT_SERVICE.create_model_approval(payload)
    if not res.get("success"):
        raise HTTPException(status_code=res.get("status_code", 400), detail=res.get("message"))
    return res


@_get("/model-approvals")
def list_model_approvals(
    manufacturer: Optional[str] = Query(None),
    accuracy_class: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    instrument_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    valid_only: bool = Query(False),
):
    """Lists registered Model Approval records with multi-field filtering."""
    records = INSTRUMENT_SERVICE.list_model_approvals(
        manufacturer=manufacturer,
        accuracy_class=accuracy_class,
        status=status,
        instrument_type=instrument_type,
        search=search,
        valid_only=valid_only,
    )
    return {
        "success": True,
        "count": len(records),
        "data": records,
    }


@_get("/model-approvals/{reference}")
def get_model_approval(reference: str = Path(...)):
    """Retrieves a specific Model Approval record by certificate number or application reference."""
    record = INSTRUMENT_SERVICE.get_model_approval(reference)
    if not record:
        raise HTTPException(status_code=404, detail=f"Model approval '{reference}' not found.")
    return {"success": True, "data": record}


@_put("/model-approvals/{reference}")
@_patch("/model-approvals/{reference}")
def update_model_approval(
    reference: str = Path(...),
    payload: Dict[str, Any] = Body(...),
):
    """Updates a Model Approval record with state transition and metrology checks."""
    res = INSTRUMENT_SERVICE.update_model_approval(reference, payload)
    if not res.get("success"):
        raise HTTPException(status_code=res.get("status_code", 400), detail=res.get("message"))
    return res


@_post("/model-approvals/{reference}/transition")
def transition_model_approval(
    reference: str = Path(...),
    payload: Dict[str, Any] = Body(...),
):
    """Transitions a Model Approval lifecycle status (e.g. SUBMITTED -> UNDER_TESTING -> APPROVED)."""
    to_status = payload.get("to_status") or payload.get("status")
    if not to_status:
        raise HTTPException(status_code=422, detail="Missing required field 'to_status'.")
    extra = {k: v for k, v in payload.items() if k not in ("to_status", "status")}
    res = INSTRUMENT_SERVICE.transition_model_approval(reference, to_status, **extra)
    if not res.get("success"):
        raise HTTPException(status_code=res.get("status_code", 400), detail=res.get("message"))
    return res


@_post("/model-approvals/{reference}/link-instrument")
def link_instrument_to_model_approval(
    reference: str = Path(...),
    payload: Dict[str, Any] = Body(...),
):
    """Associates an instrument with a model approval."""
    instrument_id = payload.get("instrument_id")
    if not instrument_id:
        raise HTTPException(status_code=422, detail="Missing required field 'instrument_id'.")
    res = INSTRUMENT_SERVICE.link_model_approval_instrument(reference, instrument_id)
    if not res.get("success"):
        raise HTTPException(status_code=res.get("status_code", 404), detail=res.get("message"))
    return res


@_get("/model-approvals/{reference}/instruments")
def get_model_approval_instruments(reference: str = Path(...)):
    """Lists all instruments associated with this model approval."""
    record = INSTRUMENT_SERVICE.get_model_approval(reference)
    if not record:
        raise HTTPException(status_code=404, detail=f"Model approval '{reference}' not found.")
    return {
        "success": True,
        "reference": reference,
        "count": len(record.get("associated_instrument_ids", [])),
        "data": record.get("associated_instrument_ids", []),
    }


@_post("/model-approvals/verify-instrument")
def verify_instrument_against_model(
    instrument_payload: Dict[str, Any] = Body(...),
):
    """Checks whether an instrument falls within its declared Model Approval envelope."""
    inst = Instrument.from_dict(instrument_payload)
    is_valid, cert, reasons = MODEL_APPROVAL_REGISTRY.verify_instrument(inst)
    return {
        "success": True,
        "compliant": is_valid,
        "approval_number": inst.model_approval_number,
        "certificate_found": cert is not None,
        "reasons": reasons,
    }


@_post("/instruments/{instrument_id}/lifecycle-events")
def record_instrument_lifecycle_event(
    instrument_id: str = Path(...),
    payload: Dict[str, Any] = Body(...),
):
    """Records a statutory lifecycle event (e.g. dismantling, relocation, repair, retirement)."""
    event_type = payload.get("event_type")
    new_status = payload.get("new_status")
    if not event_type or not new_status:
        raise HTTPException(status_code=422, detail="Fields 'event_type' and 'new_status' are required.")

    res = INSTRUMENT_SERVICE.record_lifecycle_event(
        instrument_id=instrument_id,
        event_type=event_type,
        new_status=new_status,
        actor=payload.get("actor", "SYSTEM"),
        event_date=payload.get("event_date"),
        related_job_id=payload.get("related_job_id"),
        notes=payload.get("notes", ""),
        metadata=payload.get("metadata"),
    )
    if not res.get("success"):
        raise HTTPException(status_code=res.get("status_code", 400), detail=res.get("message"))
    return res


@_get("/instruments/{instrument_id}/lifecycle")
@_get("/instruments/{instrument_id}/lifecycle-history")
def get_instrument_lifecycle_history(instrument_id: str = Path(...)):
    """Retrieves full immutable statutory lifecycle history of an instrument."""
    res = INSTRUMENT_SERVICE.get_instrument_lifecycle_history(instrument_id)
    if not res.get("success"):
        raise HTTPException(status_code=res.get("status_code", 404), detail=res.get("message"))
    return res


@_post("/instruments/{instrument_id}/schedule-verification")
def schedule_instrument_verification(
    instrument_id: str = Path(...),
    payload: Optional[Dict[str, Any]] = Body(None),
):
    """Calculates and stores next verification due date from applicable regulatory profile."""
    payload = payload or {}
    base_date = payload.get("base_date") or payload.get("last_verification_date")
    res = INSTRUMENT_SERVICE.schedule_verification(
        instrument_id=instrument_id,
        base_date=base_date,
        profile_id=payload.get("profile_id"),
    )
    return res


@_post("/instruments/{instrument_id}/verification-job")
@_post("/instruments/{instrument_id}/create-verification-job")
def create_instrument_verification_job(
    instrument_id: str = Path(...),
    payload: Dict[str, Any] = Body(...),
):
    """Provisions a statutory verification Test Job for an instrument."""
    job_type = payload.get("job_type", "RE_VERIFICATION")
    reason = payload.get("reason") or payload.get("verification_reason", "PERIODIC_EXPIRY")
    res = INSTRUMENT_SERVICE.create_verification_job(
        instrument_id=instrument_id,
        job_type=job_type,
        reason=reason,
        scheduled_date=payload.get("scheduled_date"),
        user_id=payload.get("user_id") or payload.get("created_by", "SYSTEM"),
        priority=payload.get("priority"),
        notes=payload.get("notes", ""),
        inspector_id=payload.get("inspector_id"),
        inspector_name=payload.get("inspector_name"),
        testing_centre_name=payload.get("testing_centre_name"),
    )
    if not res.get("success"):
        raise HTTPException(status_code=res.get("status_code", 400), detail=res.get("message"))
    return res


@_post("/jobs/{job_id}/complete-verification")
def complete_verification_job_api(
    job_id: str = Path(...),
    payload: Dict[str, Any] = Body(...),
):
    """Synchronizes instrument verification status and schedules next due date after job completion."""
    outcome = payload.get("outcome") or payload.get("job_outcome", "PASSED")
    certificate_number = payload.get("certificate_number") or payload.get("verification_certificate_number")
    res = INSTRUMENT_SERVICE.complete_verification_job(
        job_id=job_id,
        outcome=outcome,
        certificate_number=certificate_number,
        verification_date=payload.get("verification_date"),
        inspecting_officer=payload.get("inspecting_officer") or payload.get("completed_by"),
        stamping_authority=payload.get("stamping_authority"),
        metadata=payload.get("metadata"),
    )
    if not res.get("success"):
        raise HTTPException(status_code=res.get("status_code", 400), detail=res.get("message"))
    return res

