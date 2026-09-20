"""
MetrIQ P5 Test-Job Workflow API Router
======================================
Person 5: Workflow + Evidence Engineer

Exposes RESTful endpoints for Test Job lifecycle state transitions:
- POST /jobs/{job_id}/transition
- POST /test-jobs/{job_id}/transition
- GET  /jobs/{job_id}/state
- GET  /test-jobs/{job_id}/state
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Body, Path
from fastapi.responses import JSONResponse

from app.jobs.models import JobStatus
from .service import WORKFLOW_SERVICE, JobNotFoundError
from .state_machine import WorkflowStateTransitionError


router = APIRouter(tags=["Workflow & Lifecycle"])


@router.post("/jobs/{job_id}/transition")
@router.post("/test-jobs/{job_id}/transition")
def transition_job_endpoint(
    job_id: str = Path(..., description="Unique job identifier"),
    payload: Dict[str, Any] = Body(..., description="State transition payload"),
):
    """
    Executes a formal state machine transition on a test job.

    Request Payload:
    ```json
    {
      "target_state": "IN_PROGRESS",
      "reason": "Physical testing begun",
      "actor": "OFFICER_01",
      "metadata": {},
      "test_execution_data": {}
    }
    ```
    """
    target_state = payload.get("target_state") or payload.get("to_status")
    if not target_state:
        return JSONResponse(
            status_code=400,
            content={
                "error": "MISSING_TARGET_STATE",
                "message": "Field 'target_state' is required.",
                "success": False,
                "status_code": 400,
            },
        )

    actor = payload.get("actor") or payload.get("user_id") or "SYSTEM"
    reason = payload.get("reason")
    metadata = payload.get("metadata")
    test_execution_data = payload.get("test_execution_data")

    try:
        updated_job = WORKFLOW_SERVICE.transition_job(
            job_id=job_id,
            target_state=target_state,
            actor=actor,
            reason=reason,
            metadata=metadata,
            test_execution_data=test_execution_data,
        )
        return {
            "success": True,
            "status_code": 200,
            "message": f"Job '{job_id}' successfully transitioned to {updated_job.status.value}",
            "job_id": updated_job.job_id,
            "current_state": updated_job.status.value,
            "data": updated_job.to_dict(),
        }
    except JobNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={
                "error": "JOB_NOT_FOUND",
                "message": e.message,
                "success": False,
                "status_code": 404,
            },
        )
    except WorkflowStateTransitionError as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": e.error_code,
                "message": e.message,
                "success": False,
                "status_code": 400,
                "current_state": e.current_state,
                "target_state": e.target_state,
            },
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_SERVER_ERROR",
                "message": str(e),
                "success": False,
                "status_code": 500,
            },
        )


@router.get("/jobs/{job_id}/state")
@router.get("/test-jobs/{job_id}/state")
def get_job_state_endpoint(job_id: str = Path(...)):
    """Retrieves current lifecycle state and state transition history for a job."""
    job = WORKFLOW_SERVICE.jobs.get(job_id)
    if not job:
        return JSONResponse(
            status_code=404,
            content={
                "error": "JOB_NOT_FOUND",
                "message": f"Job '{job_id}' was not found.",
                "success": False,
                "status_code": 404,
            },
        )
    return {
        "success": True,
        "status_code": 200,
        "job_id": job.job_id,
        "current_state": job.status.value,
        "state_changed_at": job.state_changed_at,
        "state_history": [t.to_dict() for t in job.state_history],
    }
