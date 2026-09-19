"""
MetrIQ P5 Environment Condition REST API Router
===============================================
Person 5: Workflow + Evidence Engineer

Exposes RESTful endpoints for:
- Recording ambient environment conditions for a test job
- Fetching the current/latest condition
- Fetching chronological observation history
- Updating existing environment records
- Inspecting records by ID
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Body, Path, Query
from fastapi.responses import JSONResponse

from app.workflow.service import JobNotFoundError
from .service import (
    ENVIRONMENT_SERVICE,
    EnvironmentNotFoundError,
    EnvironmentStageError,
    EnvironmentUpdateRestrictedError,
    EnvironmentValidationError,
)

router = APIRouter(tags=["Environment Conditions"])


# =============================================================================
# Helper Handlers
# =============================================================================

def _record_env(job_id: str, payload: Dict[str, Any]):
    try:
        record = ENVIRONMENT_SERVICE.record_environment(job_id, payload)
        return {
            "success": True,
            "status_code": 201,
            "message": "Environment condition successfully recorded.",
            "data": record.to_dict(),
        }
    except JobNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "JOB_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except EnvironmentStageError as e:
        return JSONResponse(
            status_code=400,
            content={"error": e.error_code, "message": e.message, "success": False, "status_code": 400},
        )
    except EnvironmentValidationError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "VALIDATION_ERROR", "message": e.message, "field": e.field, "success": False, "status_code": 400},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_SERVER_ERROR", "message": str(e), "success": False, "status_code": 500},
        )


def _get_latest_env(job_id: str):
    try:
        record = ENVIRONMENT_SERVICE.get_latest_environment(job_id)
        if not record:
            return JSONResponse(
                status_code=404,
                content={
                    "error": "ENVIRONMENT_RECORD_NOT_FOUND",
                    "message": f"No environment records found for job '{job_id}'.",
                    "success": False,
                    "status_code": 404,
                },
            )
        return {"success": True, "status_code": 200, "data": record.to_dict()}
    except JobNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "JOB_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_SERVER_ERROR", "message": str(e), "success": False, "status_code": 500},
        )


def _get_history_env(job_id: str):
    try:
        history = ENVIRONMENT_SERVICE.get_environment_history(job_id)
        return {
            "success": True,
            "status_code": 200,
            "job_id": job_id,
            "count": len(history),
            "data": [r.to_dict() for r in history],
        }
    except JobNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "JOB_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_SERVER_ERROR", "message": str(e), "success": False, "status_code": 500},
        )


def _update_env(job_id: str, record_id: str, payload: Dict[str, Any]):
    try:
        updated = ENVIRONMENT_SERVICE.update_environment(job_id, record_id, payload)
        return {
            "success": True,
            "status_code": 200,
            "message": f"Environment record '{record_id}' successfully updated.",
            "data": updated.to_dict(),
        }
    except JobNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "JOB_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except EnvironmentNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "ENVIRONMENT_RECORD_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except EnvironmentUpdateRestrictedError as e:
        return JSONResponse(
            status_code=400,
            content={"error": e.error_code, "message": e.message, "success": False, "status_code": 400},
        )
    except EnvironmentValidationError as e:
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
# Primary /jobs/... Endpoints
# =============================================================================

@router.post("/jobs/{job_id}/environment", status_code=201)
def record_job_environment_endpoint(
    job_id: str = Path(..., description="ID of the TestJob"),
    payload: Dict[str, Any] = Body(...),
):
    """Records a new ambient condition measurement for a Test Job."""
    return _record_env(job_id, payload)


@router.get("/jobs/{job_id}/environment")
def get_job_environment_endpoint(job_id: str = Path(..., description="ID of the TestJob")):
    """Retrieves the latest ambient condition record for a Test Job."""
    return _get_latest_env(job_id)


@router.get("/jobs/{job_id}/environment/history")
def get_job_environment_history_endpoint(job_id: str = Path(..., description="ID of the TestJob")):
    """Retrieves chronological environment condition history for a Test Job."""
    return _get_history_env(job_id)


@router.put("/jobs/{job_id}/environment/{record_id}")
def update_job_environment_endpoint(
    job_id: str = Path(..., description="ID of the TestJob"),
    record_id: str = Path(..., description="ID of the environment record"),
    payload: Dict[str, Any] = Body(...),
):
    """Updates an existing environment record, if the job status permits."""
    return _update_env(job_id, record_id, payload)


# =============================================================================
# Global /environment/{record_id} Endpoint
# =============================================================================

@router.get("/environment/{record_id}")
def get_environment_by_id_endpoint(record_id: str = Path(..., description="ID of the environment record")):
    """Retrieves an individual environment record by ID."""
    record = ENVIRONMENT_SERVICE.get_environment_by_id(record_id)
    if not record:
        return JSONResponse(
            status_code=404,
            content={
                "error": "ENVIRONMENT_RECORD_NOT_FOUND",
                "message": f"Environment record '{record_id}' not found.",
                "success": False,
                "status_code": 404,
            },
        )
    return {"success": True, "status_code": 200, "data": record.to_dict()}


# =============================================================================
# Compatibility /test-jobs/... Endpoints
# =============================================================================

@router.post("/test-jobs/{job_id}/environment", status_code=201)
def record_test_job_environment_endpoint(
    job_id: str = Path(..., description="ID of the TestJob"),
    payload: Dict[str, Any] = Body(...),
):
    """Alias for /jobs/{job_id}/environment."""
    return _record_env(job_id, payload)


@router.get("/test-jobs/{job_id}/environment")
def get_test_job_environment_endpoint(job_id: str = Path(..., description="ID of the TestJob")):
    """Alias for /jobs/{job_id}/environment."""
    return _get_latest_env(job_id)


@router.get("/test-jobs/{job_id}/environment/history")
def get_test_job_environment_history_endpoint(job_id: str = Path(..., description="ID of the TestJob")):
    """Alias for /jobs/{job_id}/environment/history."""
    return _get_history_env(job_id)


@router.put("/test-jobs/{job_id}/environment/{record_id}")
def update_test_job_environment_endpoint(
    job_id: str = Path(..., description="ID of the TestJob"),
    record_id: str = Path(..., description="ID of the environment record"),
    payload: Dict[str, Any] = Body(...),
):
    """Alias for /jobs/{job_id}/environment/{record_id}."""
    return _update_env(job_id, record_id, payload)
