"""
MetrIQ P5 Review & Approval REST API Router
===========================================
Person 5: Workflow + Evidence Engineer

Exposes RESTful endpoints for:
- Submitting a job for review (/jobs/{jobId}/submit-review)
- Rendering review decisions (/jobs/{jobId}/review)
- Retrieving active/current review (/jobs/{jobId}/review)
- Retrieving full review history (/jobs/{jobId}/reviews)
- Querying a specific review by ID (/reviews/{reviewId})
"""

from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, Body, Header, Path, Query, Request
from fastapi.responses import JSONResponse

from app.workflow.service import JobNotFoundError
from app.workflow.state_machine import WorkflowStateTransitionError
from .models import ReviewDecision, ReviewRole, ReviewStatus
from .service import (
    REVIEW_SERVICE,
    InvalidReviewDecisionError,
    ReviewEligibilityError,
    ReviewNotFoundError,
    ReviewWorkflowStateError,
    UnauthorizedReviewerError,
)

router = APIRouter(tags=["Review & Approval"])


# =============================================================================
# 1. Submit for Review
# =============================================================================

@router.post("/jobs/{job_id}/submit-review", status_code=200)
async def submit_job_for_review_endpoint(
    job_id: str = Path(..., description="Job ID to submit for review"),
    payload: Optional[Dict[str, Any]] = Body(None),
):
    """
    Submits an IN_PROGRESS job for supervisory review.
    Validates that test execution data / attempts exist and transitions job to REVIEW.
    """
    try:
        body = payload or {}
        reviewer = body.get("reviewer") or body.get("reviewer_id") or "UNASSIGNED"
        comments = body.get("comments") or body.get("reason") or ""
        submitted_by = body.get("submitted_by") or body.get("operator") or body.get("user") or "SYSTEM"

        review, job = REVIEW_SERVICE.submit_for_review(
            job_id=job_id,
            reviewer=reviewer,
            comments=comments,
            submitted_by=submitted_by,
        )

        return {
            "success": True,
            "status_code": 200,
            "message": f"Job '{job_id}' successfully submitted for review.",
            "data": {
                "job_id": job.job_id,
                "current_state": job.current_state,
                "review": review.to_dict(),
            },
        }
    except JobNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "JOB_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except ReviewEligibilityError as e:
        return JSONResponse(
            status_code=400,
            content={"error": e.error_code, "message": e.message, "success": False, "status_code": 400},
        )
    except WorkflowStateTransitionError as e:
        return JSONResponse(
            status_code=400,
            content={"error": e.error_code, "message": e.message, "success": False, "status_code": 400},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_SERVER_ERROR", "message": str(e), "success": False, "status_code": 500},
        )


@router.post("/test-jobs/{job_id}/submit-review", status_code=200)
async def submit_test_job_for_review_endpoint(
    job_id: str = Path(...),
    payload: Optional[Dict[str, Any]] = Body(None),
):
    """Alias for /jobs/{job_id}/submit-review."""
    return await submit_job_for_review_endpoint(job_id=job_id, payload=payload)


# =============================================================================
# 2. Review Decision Action (APPROVE / REJECT / RETURN_FOR_CORRECTION)
# =============================================================================

@router.post("/jobs/{job_id}/review", status_code=200)
async def execute_job_review_endpoint(
    job_id: str = Path(..., description="Job ID currently in REVIEW"),
    payload: Optional[Dict[str, Any]] = Body(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
):
    """
    Renders a review decision on a job in REVIEW:
    - APPROVE -> transitions to APPROVED
    - REJECT -> transitions to REJECTED
    - RETURN_FOR_CORRECTION -> transitions to IN_PROGRESS
    """
    try:
        body = payload or {}
        decision = body.get("decision")
        if not decision:
            return JSONResponse(
                status_code=400,
                content={"error": "INVALID_REVIEW_DECISION", "message": "Field 'decision' is required.", "field": "decision", "success": False, "status_code": 400},
            )

        reviewer = body.get("reviewer") or body.get("reviewer_id") or x_user_id or "REVIEWER"
        role = body.get("role") or x_user_role
        comments = body.get("comments") or body.get("reason") or ""

        review, job = REVIEW_SERVICE.execute_review(
            job_id=job_id,
            decision=decision,
            comments=comments,
            reviewer=reviewer,
            role=role,
        )

        return {
            "success": True,
            "status_code": 200,
            "message": f"Review decision '{review.decision.value}' recorded for job '{job_id}'.",
            "data": {
                "job_id": job.job_id,
                "current_state": job.current_state,
                "review": review.to_dict(),
            },
        }
    except JobNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "JOB_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except UnauthorizedReviewerError as e:
        return JSONResponse(
            status_code=403,
            content={"error": e.error_code, "message": e.message, "success": False, "status_code": 403},
        )
    except InvalidReviewDecisionError as e:
        return JSONResponse(
            status_code=400,
            content={"error": e.error_code, "message": e.message, "field": e.field, "success": False, "status_code": 400},
        )
    except ReviewWorkflowStateError as e:
        return JSONResponse(
            status_code=400,
            content={"error": e.error_code, "message": e.message, "success": False, "status_code": 400},
        )
    except WorkflowStateTransitionError as e:
        return JSONResponse(
            status_code=400,
            content={"error": e.error_code, "message": e.message, "success": False, "status_code": 400},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_SERVER_ERROR", "message": str(e), "success": False, "status_code": 500},
        )


@router.post("/test-jobs/{job_id}/review", status_code=200)
async def execute_test_job_review_endpoint(
    job_id: str = Path(...),
    payload: Optional[Dict[str, Any]] = Body(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
):
    """Alias for /jobs/{job_id}/review."""
    return await execute_job_review_endpoint(job_id=job_id, payload=payload, x_user_id=x_user_id, x_user_role=x_user_role)


# =============================================================================
# 3. Query Endpoints
# =============================================================================

@router.get("/jobs/{job_id}/review")
def get_job_current_review_endpoint(job_id: str = Path(...)):
    """Retrieves the active or latest review record for a job."""
    review = REVIEW_SERVICE.get_current_review(job_id)
    if not review:
        return JSONResponse(
            status_code=404,
            content={"error": "REVIEW_NOT_FOUND", "message": f"No review found for job '{job_id}'.", "success": False, "status_code": 404},
        )
    return {"success": True, "status_code": 200, "data": review.to_dict()}


@router.get("/jobs/{job_id}/reviews/current")
def get_job_current_review_alias_endpoint(job_id: str = Path(...)):
    """Alias for /jobs/{job_id}/review."""
    return get_job_current_review_endpoint(job_id=job_id)


@router.get("/jobs/{job_id}/reviews")
def get_job_review_history_endpoint(job_id: str = Path(...)):
    """Retrieves chronological review history for a job."""
    try:
        reviews = REVIEW_SERVICE.get_review_history(job_id)
        return {
            "success": True,
            "status_code": 200,
            "job_id": job_id,
            "count": len(reviews),
            "data": [r.to_dict() for r in reviews],
        }
    except JobNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "JOB_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )


@router.get("/reviews/{review_id}")
def get_review_by_id_endpoint(review_id: str = Path(...)):
    """Retrieves a single review by ID."""
    review = REVIEW_SERVICE.get_review(review_id)
    if not review:
        return JSONResponse(
            status_code=404,
            content={"error": "REVIEW_NOT_FOUND", "message": f"Review '{review_id}' not found.", "success": False, "status_code": 404},
        )
    return {"success": True, "status_code": 200, "data": review.to_dict()}
