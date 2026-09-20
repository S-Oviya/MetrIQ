"""
MetrIQ Test Jobs API Router — Person 3 (Job / Instrument Engineer)
==================================================================
Exposes RESTful endpoints for Test Job creation, statutory routing,
Inspector assignment, state machine lifecycle transitions, pre-test validation,
automatic test plan generation, and test plan access.

Supports both canonical `/test-jobs` and legacy/convenience `/jobs` prefixes.
"""

from typing import Any, Dict, List, Optional, Union

try:
    from fastapi import APIRouter, Body, HTTPException, Path, Query, status
    HAS_FASTAPI = True
    router = APIRouter(tags=["Test Jobs & Verification Workflows"])
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

from app.jobs.service import TEST_JOB_SERVICE, TestJobService


# =============================================================================
# Router/API boundary helper
# =============================================================================

def _q(value, default=None):
    """
    Strips FastAPI FieldInfo (Query/Path/Body) objects at the router boundary so
    that direct Python calls from tests receive plain Python defaults instead of
    FastAPI annotation objects.

    When FastAPI processes an HTTP request, it injects the real parsed value and
    this function is a no-op.  When a test calls the router function directly as
    a plain Python function, the un-injected parameter retains its FieldInfo
    default; _q() detects that and returns the caller-supplied `default` instead.
    """
    try:
        from fastapi.fields import FieldInfo
        if isinstance(value, FieldInfo):
            return default
    except ImportError:
        pass
    try:
        from pydantic.fields import FieldInfo as PydanticFieldInfo
        if isinstance(value, PydanticFieldInfo):
            return default
    except ImportError:
        pass
    return value


# =============================================================================
# Test Job CRUD Endpoints
# =============================================================================

@_post("/test-jobs", status_code=status.HTTP_201_CREATED)
@_post("/jobs", status_code=status.HTTP_201_CREATED)
def create_test_job(
    payload: Dict[str, Any] = Body(..., description="Job creation payload including instrument_id and job_type"),
):
    """
    Creates a statutory test job:
    1. Resolves instrument from registry.
    2. Evaluates GATC routing (Rule 3 & First Schedule).
    3. Generates and attaches Person 2 statutory test plan.
    4. Transitions instrument status to IN_VERIFICATION.
    """
    res = TEST_JOB_SERVICE.create_job(payload)
    if not res.get("success"):
        raise HTTPException(status_code=res.get("status_code", 400), detail=res)
    return res


@_get("/test-jobs")
@_get("/jobs")
def list_jobs(
    status: Optional[str] = Query(None, description="Filter by job status"),
    job_type: Optional[str] = Query(None, description="Filter by job type"),
    instrument_id: Optional[str] = Query(None, description="Filter by instrument ID"),
    inspector_id: Optional[str] = Query(None, description="Filter by inspector ID"),
    testing_centre_id: Optional[str] = Query(None, description="Filter by test centre ID"),
    search: Optional[str] = Query(None, description="Search across job ID, instrument ID, names"),
):
    """Lists test jobs with optional multi-parameter filters."""
    jobs = TEST_JOB_SERVICE.list_jobs(
        status=_q(status),
        job_type=_q(job_type),
        instrument_id=_q(instrument_id),
        inspector_id=_q(inspector_id),
        testing_centre_id=_q(testing_centre_id),
        search=_q(search),
    )
    return {
        "success": True,
        "count": len(jobs),
        "data": jobs,
    }


@_get("/test-jobs/{job_id}")
@_get("/jobs/{job_id}")
def get_job_details(job_id: str = Path(...)):
    """Retrieves full details of a test job, including attached test plan and state history."""
    job = TEST_JOB_SERVICE.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return {"success": True, "data": job}


@_put("/test-jobs/{job_id}")
@_patch("/test-jobs/{job_id}")
@_put("/jobs/{job_id}")
@_patch("/jobs/{job_id}")
def update_test_job(
    job_id: str = Path(...),
    payload: Dict[str, Any] = Body(..., description="Job fields to update"),
):
    """Updates an existing test job (PUT/PATCH) with location validation."""
    res = TEST_JOB_SERVICE.update_job(job_id, payload)
    if not res.get("success"):
        raise HTTPException(status_code=res.get("status_code", 400), detail=res.get("message"))
    return res


# =============================================================================
# Statutory Pre-Test Validation & Test Plan Generation
# =============================================================================

@_post("/test-jobs/{job_id}/validate")
@_post("/jobs/{job_id}/validate")
def validate_test_job_api(
    job_id: str = Path(...),
    payload: Optional[Dict[str, Any]] = Body(None),
):
    """
    Performs statutory pre-test validation on a job:
    1. Instrument existence & metrology feasibility via Person 2.
    2. Regulatory profile validity and active status.
    3. Statutory GATC / location routing compliance.
    4. Model approval envelope compliance.
    Transitions status to VALIDATED upon success.
    """
    user_id = (payload or {}).get("user_id", "SYSTEM")
    res = TEST_JOB_SERVICE.validate_job(job_id, user_id=user_id)
    if not res.get("success"):
        raise HTTPException(status_code=res.get("status_code", 400), detail=res.get("message"))
    return res


@_post("/test-jobs/{job_id}/generate-plan")
@_post("/jobs/{job_id}/generate-plan")
def generate_job_test_plan_api(
    job_id: str = Path(...),
    payload: Optional[Dict[str, Any]] = Body(None),
):
    """
    Generates or re-generates statutory test plan for a test job via Person 2 engine.
    Binds test plan and reference, and transitions status to TEST_PLAN_GENERATED.
    """
    payload = payload or {}
    user_id = payload.get("user_id", "SYSTEM")
    force_regenerate = bool(payload.get("force_regenerate", False))
    res = TEST_JOB_SERVICE.generate_job_test_plan(job_id, user_id=user_id, force_regenerate=force_regenerate)
    if not res.get("success"):
        raise HTTPException(status_code=res.get("status_code", 400), detail=res.get("message"))
    return res


@_get("/test-jobs/{job_id}/test-plan")
@_get("/jobs/{job_id}/test-plan")
def get_job_test_plan(job_id: str = Path(...)):
    """
    Endpoint for Person 4 (Test Execution Engine) to retrieve the pre-calculated
    statutory test plan (load points, eccentricity corners, repeatability runs, MPE limits).
    """
    plan = TEST_JOB_SERVICE.get_job_test_plan(job_id)
    if not plan:
        raise HTTPException(
            status_code=404,
            detail=f"Test plan not found or not yet generated for job '{job_id}'.",
        )
    return {"success": True, "job_id": job_id, "data": plan}


# =============================================================================
# Lifecycle State Machine & Inspector Assignment
# =============================================================================

@_post("/test-jobs/{job_id}/transition")
@_post("/jobs/{job_id}/transition")
def transition_job_status(
    job_id: str = Path(...),
    to_status: str = Body(..., embed=True, description="Target lifecycle state"),
    user_id: str = Body("SYSTEM", embed=True),
    reason: str = Body("", embed=True),
    metadata: Optional[Dict[str, Any]] = Body(None, embed=True),
):
    """
    Executes a formal state machine transition on a job.
    Updates instrument operational status upon certification or rejection.
    """
    res = TEST_JOB_SERVICE.transition_job_status(
        job_id=job_id,
        to_status=to_status,
        user_id=user_id,
        reason=reason,
        metadata=metadata,
    )
    if not res.get("success"):
        raise HTTPException(status_code=res.get("status_code", 400), detail=res)
    return res


@_post("/test-jobs/{job_id}/assign")
@_post("/jobs/{job_id}/assign")
def assign_job_inspector(
    job_id: str = Path(...),
    inspector_id: str = Body(..., embed=True),
    inspector_name: str = Body(..., embed=True),
    testing_centre_id: Optional[str] = Body(None, embed=True),
    testing_centre_name: Optional[str] = Body(None, embed=True),
    scheduled_date: Optional[str] = Body(None, embed=True),
    assigned_by: str = Body("SYSTEM", embed=True),
    verification_location_type: Optional[str] = Body(None, embed=True),
    gatc_reference: Optional[str] = Body(None, embed=True),
):
    """Assigns an inspector / test centre to a job and transitions to ASSIGNED status."""
    res = TEST_JOB_SERVICE.assign_inspector(
        job_id=job_id,
        inspector_id=inspector_id,
        inspector_name=inspector_name,
        testing_centre_id=testing_centre_id,
        testing_centre_name=testing_centre_name,
        scheduled_date=scheduled_date,
        assigned_by=assigned_by,
        verification_location_type=verification_location_type,
        gatc_reference=gatc_reference,
    )
    if not res.get("success"):
        raise HTTPException(status_code=res.get("status_code", 400), detail=res)
    return res


@_get("/test-jobs/instrument/{instrument_id}")
@_get("/jobs/instrument/{instrument_id}")
def get_jobs_for_instrument(instrument_id: str = Path(...)):
    """Retrieves complete historical testing and verification jobs for an instrument."""
    jobs = TEST_JOB_SERVICE.list_jobs(instrument_id=instrument_id)
    return {"success": True, "instrument_id": instrument_id, "count": len(jobs), "data": jobs}


@_get("/test-jobs/{job_id}/regulatory-context")
@_get("/jobs/{job_id}/regulatory-context")
def get_job_regulatory_context(job_id: str = Path(...)):
    """Retrieves the regulatory profile, version, applicable tests, and rule references for a job."""
    job = TEST_JOB_SERVICE.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return {
        "success": True,
        "job_id": job_id,
        "instrument_id": job.get("instrument_id"),
        "regulatory_profile_id": job.get("regulatory_profile_id"),
        "regulatory_version": job.get("regulatory_version"),
        "applicable_tests": job.get("applicable_tests", []),
        "regulatory_rule_references": job.get("regulatory_rule_references", []),
        "statutory_routing": job.get("statutory_routing"),
        "verification_location_type": job.get("verification_location_type"),
        "laboratory": job.get("laboratory"),
        "test_centre": job.get("test_centre"),
        "gatc_reference": job.get("gatc_reference"),
        "installation_location": job.get("installation_location"),
        "reason_for_verification": job.get("reason_for_verification"),
        "routing_decision": job.get("routing_decision"),
        "regulatory_rule_reference": job.get("regulatory_rule_reference"),
        "manual_review_flag": job.get("manual_review_flag"),
        "manual_review_reason": job.get("manual_review_reason"),
    }


@_post("/test-jobs/evaluate-location-routing")
@_post("/jobs/evaluate-location-routing")
def evaluate_job_location_routing(
    payload: Dict[str, Any] = Body(..., description="Evaluation payload with instrument_id, job_type, and location preferences"),
):
    """
    Evaluates statutory verification location and GATC routing recommendations
    without creating a job, using Person 2's GATC evaluation engine.
    """
    inst_id = payload.get("instrument_id")
    if not inst_id:
        raise HTTPException(status_code=422, detail="instrument_id is required")
    res = TEST_JOB_SERVICE.evaluate_job_routing(
        instrument_id=inst_id,
        job_type=payload.get("job_type", "RE_VERIFICATION"),
        profile_id=payload.get("profile_id"),
        preferred_location_type=payload.get("preferred_location_type") or payload.get("verification_location_type"),
        testing_centre_id=payload.get("testing_centre_id"),
        testing_centre_name=payload.get("testing_centre_name"),
        gatc_reference=payload.get("gatc_reference") or payload.get("gatc_code"),
        strict_gatc_validation=payload.get("strict_gatc_validation", False),
    )
    if not res.get("success"):
        raise HTTPException(status_code=res.get("status_code", 400), detail=res.get("message"))
    return res
