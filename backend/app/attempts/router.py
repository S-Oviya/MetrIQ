"""
MetrIQ P5 Test Attempt & Retest REST API Router
===============================================
Person 5: Workflow + Evidence Engineer

Exposes RESTful endpoints for:
- Starting a sequential test attempt
- Completing an attempt with PASS/FAIL/INCONCLUSIVE verdict
- Listing attempts for a test in chronological/sequential order
- Fetching single attempt details
- Requesting retests for failed attempts and progressing workflow to RETEST_REQUIRED
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Body, Path, Query
from fastapi.responses import JSONResponse

from app.workflow.service import JobNotFoundError
from .repository import DuplicateAttemptNumberError
from .service import (
    ATTEMPT_SERVICE,
    AttemptAlreadyCompletedError,
    AttemptJobStateError,
    AttemptNotFoundError,
    AttemptValidationError,
    TestNotFoundError,
)

router = APIRouter(tags=["Test Attempts & Retests"])


# =============================================================================
# Helper Handlers
# =============================================================================

def _start_attempt_handler(job_id: str, test_id: str, payload: Dict[str, Any]):
    try:
        operator = payload.get("operator") or payload.get("user")
        entered_values = payload.get("entered_values")
        test_run_id = payload.get("test_run_id")
        notes = payload.get("notes") or payload.get("comments") or ""

        attempt = ATTEMPT_SERVICE.start_attempt(
            job_id=job_id,
            test_id=test_id,
            operator=operator,
            entered_values=entered_values,
            test_run_id=test_run_id,
            notes=notes,
        )
        return {
            "success": True,
            "status_code": 201,
            "message": f"Test attempt {attempt.attempt_number} started for test '{test_id}'.",
            "data": attempt.to_dict(),
        }
    except JobNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "JOB_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except TestNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "TEST_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except AttemptJobStateError as e:
        return JSONResponse(
            status_code=400,
            content={"error": e.error_code, "message": e.message, "success": False, "status_code": 400},
        )
    except AttemptValidationError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "VALIDATION_ERROR", "message": e.message, "field": e.field, "success": False, "status_code": 400},
        )
    except DuplicateAttemptNumberError as e:
        return JSONResponse(
            status_code=409,
            content={"error": "DUPLICATE_ATTEMPT_NUMBER", "message": str(e), "success": False, "status_code": 409},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_SERVER_ERROR", "message": str(e), "success": False, "status_code": 500},
        )


def _complete_attempt_handler(attempt_id: str, payload: Dict[str, Any]):
    try:
        result = payload.get("result") or payload.get("verdict") or payload.get("status")
        comments = payload.get("comments") or payload.get("reason") or ""
        result_data = payload.get("result_data") or payload.get("results")
        entered_values = payload.get("entered_values")
        test_run_id = payload.get("test_run_id")
        completed_by = payload.get("completed_by") or payload.get("operator") or payload.get("user")

        completed = ATTEMPT_SERVICE.complete_attempt(
            attempt_id=attempt_id,
            result=result,
            comments=comments,
            result_data=result_data,
            entered_values=entered_values,
            test_run_id=test_run_id,
            completed_by=completed_by,
        )
        return {
            "success": True,
            "status_code": 200,
            "message": f"Test attempt '{attempt_id}' completed with result '{completed.result.value}'.",
            "data": completed.to_dict(),
        }
    except AttemptNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "ATTEMPT_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except AttemptAlreadyCompletedError as e:
        return JSONResponse(
            status_code=400,
            content={"error": e.error_code, "message": e.message, "success": False, "status_code": 400},
        )
    except AttemptValidationError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "VALIDATION_ERROR", "message": e.message, "field": e.field, "success": False, "status_code": 400},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_SERVER_ERROR", "message": str(e), "success": False, "status_code": 500},
        )


def _retest_handler(job_id: str, test_id: str, attempt_id: str, payload: Dict[str, Any]):
    try:
        reason = payload.get("reason") or payload.get("comments") or ""
        requested_by = payload.get("requested_by") or payload.get("operator") or payload.get("user") or "SYSTEM"
        metadata = payload.get("metadata")

        req = ATTEMPT_SERVICE.request_retest(
            job_id=job_id,
            test_id=test_id,
            attempt_id=attempt_id,
            reason=reason,
            requested_by=requested_by,
            metadata=metadata,
        )
        return {
            "success": True,
            "status_code": 200,
            "message": f"Retest requested for test '{test_id}'. Job moved to RETEST_REQUIRED.",
            "data": req.to_dict(),
        }
    except JobNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "JOB_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except AttemptNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "ATTEMPT_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except AttemptJobStateError as e:
        return JSONResponse(
            status_code=400,
            content={"error": e.error_code, "message": e.message, "success": False, "status_code": 400},
        )
    except AttemptValidationError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "VALIDATION_ERROR", "message": e.message, "field": e.field, "success": False, "status_code": 400},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_SERVER_ERROR", "message": str(e), "success": False, "status_code": 500},
        )


# =============================================================================
# 1. Start Attempt Endpoints
# =============================================================================

@router.post("/jobs/{job_id}/tests/{test_id}/attempts", status_code=201)
def start_job_test_attempt_endpoint(
    job_id: str = Path(..., description="Job ID"),
    test_id: str = Path(..., description="Test ID"),
    payload: Dict[str, Any] = Body(...),
):
    """Starts a new test attempt for a test under a specific Job."""
    return _start_attempt_handler(job_id, test_id, payload)


@router.post("/tests/{test_id}/attempts", status_code=201)
def start_test_attempt_endpoint(
    test_id: str = Path(..., description="Test ID"),
    job_id: Optional[str] = Query(None, description="Optional job ID query"),
    payload: Dict[str, Any] = Body(...),
):
    """Starts a new test attempt, accepting job_id in query or payload body."""
    target_job_id = job_id or payload.get("job_id")
    if not target_job_id:
        return JSONResponse(
            status_code=400,
            content={"error": "VALIDATION_ERROR", "message": "job_id is required in query or body.", "success": False, "status_code": 400},
        )
    return _start_attempt_handler(target_job_id, test_id, payload)


# =============================================================================
# 2. Complete Attempt Endpoints
# =============================================================================

@router.post("/jobs/{job_id}/tests/{test_id}/attempts/{attempt_id}/complete")
def complete_job_test_attempt_endpoint(
    job_id: str = Path(...),
    test_id: str = Path(...),
    attempt_id: str = Path(...),
    payload: Dict[str, Any] = Body(...),
):
    """Completes a test attempt with PASS/FAIL verdict."""
    return _complete_attempt_handler(attempt_id, payload)


@router.post("/tests/{test_id}/attempts/{attempt_id}/complete")
def complete_test_attempt_endpoint(
    test_id: str = Path(...),
    attempt_id: str = Path(...),
    payload: Dict[str, Any] = Body(...),
):
    """Completes a test attempt with PASS/FAIL verdict."""
    return _complete_attempt_handler(attempt_id, payload)


@router.post("/attempts/{attempt_id}/complete")
def complete_attempt_direct_endpoint(
    attempt_id: str = Path(...),
    payload: Dict[str, Any] = Body(...),
):
    """Direct attempt completion endpoint by attempt ID."""
    return _complete_attempt_handler(attempt_id, payload)


# =============================================================================
# 3. List & Get Attempt Endpoints
# =============================================================================

@router.get("/jobs/{job_id}/tests/{test_id}/attempts")
def list_job_test_attempts_endpoint(
    job_id: str = Path(...),
    test_id: str = Path(...),
):
    """Lists all attempts for a test on a job in chronological/sequential order."""
    try:
        attempts = ATTEMPT_SERVICE.get_attempts_for_test(job_id, test_id)
        return {
            "success": True,
            "status_code": 200,
            "job_id": job_id,
            "test_id": test_id,
            "count": len(attempts),
            "data": [a.to_dict() for a in attempts],
        }
    except JobNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "JOB_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )


@router.get("/tests/{test_id}/attempts")
def list_test_attempts_endpoint(
    test_id: str = Path(...),
    job_id: str = Query(..., description="Required Job ID"),
):
    """Lists all attempts for a test given a Job ID query parameter."""
    try:
        attempts = ATTEMPT_SERVICE.get_attempts_for_test(job_id, test_id)
        return {
            "success": True,
            "status_code": 200,
            "job_id": job_id,
            "test_id": test_id,
            "count": len(attempts),
            "data": [a.to_dict() for a in attempts],
        }
    except JobNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "JOB_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )


@router.get("/jobs/{job_id}/tests/{test_id}/attempts/{attempt_id}")
def get_job_test_attempt_endpoint(
    job_id: str = Path(...),
    test_id: str = Path(...),
    attempt_id: str = Path(...),
):
    """Retrieves a single attempt with its result and execution data."""
    attempt = ATTEMPT_SERVICE.get_attempt(attempt_id)
    if not attempt or attempt.job_id != job_id or attempt.test_id.upper() != test_id.strip().upper():
        return JSONResponse(
            status_code=404,
            content={"error": "ATTEMPT_NOT_FOUND", "message": f"Attempt '{attempt_id}' not found.", "success": False, "status_code": 404},
        )
    return {"success": True, "status_code": 200, "data": attempt.to_dict()}


@router.get("/tests/{test_id}/attempts/{attempt_id}")
def get_test_attempt_endpoint(
    test_id: str = Path(...),
    attempt_id: str = Path(...),
):
    """Retrieves a single attempt by test ID and attempt ID."""
    attempt = ATTEMPT_SERVICE.get_attempt(attempt_id)
    if not attempt or attempt.test_id.upper() != test_id.strip().upper():
        return JSONResponse(
            status_code=404,
            content={"error": "ATTEMPT_NOT_FOUND", "message": f"Attempt '{attempt_id}' not found.", "success": False, "status_code": 404},
        )
    return {"success": True, "status_code": 200, "data": attempt.to_dict()}


@router.get("/attempts/{attempt_id}")
def get_attempt_direct_endpoint(attempt_id: str = Path(...)):
    """Retrieves a single attempt directly by ID."""
    attempt = ATTEMPT_SERVICE.get_attempt(attempt_id)
    if not attempt:
        return JSONResponse(
            status_code=404,
            content={"error": "ATTEMPT_NOT_FOUND", "message": f"Attempt '{attempt_id}' not found.", "success": False, "status_code": 404},
        )
    return {"success": True, "status_code": 200, "data": attempt.to_dict()}


# =============================================================================
# 4. Request Retest Endpoints
# =============================================================================

@router.post("/jobs/{job_id}/tests/{test_id}/attempts/{attempt_id}/retest")
def request_retest_endpoint(
    job_id: str = Path(...),
    test_id: str = Path(...),
    attempt_id: str = Path(...),
    payload: Dict[str, Any] = Body(...),
):
    """Requests a retest following a failed attempt, moving the Job to RETEST_REQUIRED."""
    return _retest_handler(job_id, test_id, attempt_id, payload)


@router.post("/tests/{test_id}/attempts/{attempt_id}/retest")
def request_test_retest_endpoint(
    test_id: str = Path(...),
    attempt_id: str = Path(...),
    job_id: Optional[str] = Query(None),
    payload: Dict[str, Any] = Body(...),
):
    """Requests a retest by attempt ID."""
    attempt = ATTEMPT_SERVICE.get_attempt(attempt_id)
    if not attempt:
        return JSONResponse(
            status_code=404,
            content={"error": "ATTEMPT_NOT_FOUND", "message": f"Attempt '{attempt_id}' not found.", "success": False, "status_code": 404},
        )
    target_job_id = job_id or payload.get("job_id") or attempt.job_id
    return _retest_handler(target_job_id, test_id, attempt_id, payload)


@router.post("/attempts/{attempt_id}/retest")
def request_retest_direct_endpoint(
    attempt_id: str = Path(...),
    payload: Dict[str, Any] = Body(...),
):
    """Direct retest request endpoint by attempt ID."""
    attempt = ATTEMPT_SERVICE.get_attempt(attempt_id)
    if not attempt:
        return JSONResponse(
            status_code=404,
            content={"error": "ATTEMPT_NOT_FOUND", "message": f"Attempt '{attempt_id}' not found.", "success": False, "status_code": 404},
        )
    return _retest_handler(attempt.job_id, attempt.test_id, attempt_id, payload)
