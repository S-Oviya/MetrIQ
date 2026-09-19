"""
MetrIQ P5 Evidence & Attachment REST API Router
===============================================
Person 5: Workflow + Evidence Engineer

Exposes RESTful endpoints for:
- Uploading evidence attachments linked to Jobs, Tests, and Attempts
- Listing evidence metadata with multi-attribute filtering
- Fetching evidence metadata by ID
- Secure file download with MIME and filename headers
- Soft-deletion / archiving of evidence records
"""

import base64
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, Body, Header, Path, Query, Request, Response
from fastapi.responses import JSONResponse

from app.attempts.service import AttemptNotFoundError
from app.workflow.service import JobNotFoundError
from .models import EvidenceType
from .service import (
    EVIDENCE_SERVICE,
    EvidenceNotFoundError,
    EvidenceSecurityError,
    EvidenceValidationError,
    EvidenceWorkflowStateError,
)

router = APIRouter(tags=["Evidence & Attachments"])


# =============================================================================
# Helper Handlers
# =============================================================================

async def _process_upload(job_id: str, request: Request, payload: Optional[Dict[str, Any]] = None):
    """
    Parses upload payload from JSON or raw request body.
    Supports base64-encoded content, plain text content, or raw binary streams.
    """
    try:
        body_dict = payload or {}
        if not body_dict:
            try:
                body_dict = await request.json()
            except Exception:
                body_dict = {}

        # 1. Extract file content
        content_bytes: bytes = b""
        raw_b64 = body_dict.get("content_base64") or body_dict.get("file_base64")
        if raw_b64:
            try:
                content_bytes = base64.b64decode(raw_b64)
            except Exception:
                raise EvidenceValidationError("Invalid base64 encoding in content_base64.", field="content_base64")
        elif "content" in body_dict:
            raw_c = body_dict["content"]
            if isinstance(raw_c, bytes):
                content_bytes = raw_c
            elif isinstance(raw_c, str):
                content_bytes = raw_c.encode("utf-8")
        elif "file" in body_dict:
            raw_c = body_dict["file"]
            if isinstance(raw_c, bytes):
                content_bytes = raw_c
            elif isinstance(raw_c, str):
                content_bytes = raw_c.encode("utf-8")
        else:
            # Check raw binary body
            raw_body = await request.body()
            if raw_body and len(raw_body) > 0:
                content_bytes = raw_body

        file_name = body_dict.get("file_name") or body_dict.get("filename") or request.query_params.get("file_name")
        if not file_name:
            raise EvidenceValidationError("Field 'file_name' is required.", field="file_name")

        ev_type = (
            body_dict.get("type")
            or body_dict.get("evidence_type")
            or request.query_params.get("type")
            or request.query_params.get("evidence_type")
            or "OTHER"
        )
        test_id = body_dict.get("test_id") or request.query_params.get("test_id")
        attempt_id = body_dict.get("attempt_id") or request.query_params.get("attempt_id")
        description = body_dict.get("description") or request.query_params.get("description") or ""
        uploaded_by = (
            body_dict.get("uploaded_by")
            or body_dict.get("operator")
            or body_dict.get("user")
            or request.query_params.get("uploaded_by")
            or "SYSTEM"
        )
        mime_type = body_dict.get("mime_type")
        if not mime_type:
            raw_ct = request.headers.get("content-type", "")
            if raw_ct and not raw_ct.startswith("application/json") and not raw_ct.startswith("application/x-www-form-urlencoded"):
                mime_type = raw_ct.split(";")[0].strip()

        evidence = EVIDENCE_SERVICE.upload_evidence(
            job_id=job_id,
            file_name=file_name,
            content=content_bytes,
            evidence_type=ev_type,
            test_id=test_id,
            attempt_id=attempt_id,
            description=description,
            uploaded_by=uploaded_by,
            mime_type=mime_type,
        )

        return {
            "success": True,
            "status_code": 201,
            "message": f"Evidence '{evidence.file_name}' successfully uploaded and linked.",
            "data": evidence.to_dict(),
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
    except EvidenceValidationError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "VALIDATION_ERROR", "message": e.message, "field": e.field, "success": False, "status_code": 400},
        )
    except EvidenceWorkflowStateError as e:
        return JSONResponse(
            status_code=400,
            content={"error": e.error_code, "message": e.message, "success": False, "status_code": 400},
        )
    except EvidenceSecurityError as e:
        return JSONResponse(
            status_code=403,
            content={"error": e.error_code, "message": e.message, "success": False, "status_code": 403},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_SERVER_ERROR", "message": str(e), "success": False, "status_code": 500},
        )


# =============================================================================
# 1. Upload Endpoints
# =============================================================================

@router.post("/jobs/{job_id}/evidence", status_code=201)
async def upload_job_evidence_endpoint(
    request: Request,
    job_id: str = Path(..., description="Job ID"),
    payload: Optional[Dict[str, Any]] = Body(None),
):
    """Uploads and links evidence to a Job (with optional test_id and attempt_id)."""
    return await _process_upload(job_id, request, payload)


@router.post("/test-jobs/{job_id}/evidence", status_code=201)
async def upload_test_job_evidence_endpoint(
    request: Request,
    job_id: str = Path(..., description="Job ID"),
    payload: Optional[Dict[str, Any]] = Body(None),
):
    """Alias for /jobs/{job_id}/evidence."""
    return await _process_upload(job_id, request, payload)


# =============================================================================
# 2. List & Query Endpoints
# =============================================================================

@router.get("/jobs/{job_id}/evidence")
def list_job_evidence_endpoint(
    job_id: str = Path(...),
    test_id: Optional[str] = Query(None),
    attempt_id: Optional[str] = Query(None),
    evidence_type: Optional[str] = Query(None),
    include_archived: bool = Query(False),
):
    """Lists evidence attachments associated with a Job."""
    try:
        items = EVIDENCE_SERVICE.list_job_evidence(
            job_id=job_id,
            test_id=test_id,
            attempt_id=attempt_id,
            evidence_type=evidence_type,
            include_archived=include_archived,
        )
        return {
            "success": True,
            "status_code": 200,
            "job_id": job_id,
            "count": len(items),
            "data": [e.to_dict() for e in items],
        }
    except JobNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "JOB_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )


@router.get("/jobs/{job_id}/tests/{test_id}/evidence")
def list_test_evidence_endpoint(
    job_id: str = Path(...),
    test_id: str = Path(...),
    include_archived: bool = Query(False),
):
    """Lists all evidence attachments linked to a specific test on a Job."""
    try:
        items = EVIDENCE_SERVICE.list_test_evidence(job_id, test_id, include_archived=include_archived)
        return {
            "success": True,
            "status_code": 200,
            "job_id": job_id,
            "test_id": test_id,
            "count": len(items),
            "data": [e.to_dict() for e in items],
        }
    except JobNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "JOB_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )


# =============================================================================
# 3. Single Evidence Retrieval & Download Endpoints
# =============================================================================

@router.get("/evidence/{evidence_id}")
def get_evidence_metadata_endpoint(evidence_id: str = Path(...)):
    """Retrieves metadata for a single evidence attachment by ID."""
    evidence = EVIDENCE_SERVICE.get_evidence(evidence_id)
    if not evidence:
        return JSONResponse(
            status_code=404,
            content={"error": "EVIDENCE_NOT_FOUND", "message": f"Evidence '{evidence_id}' not found.", "success": False, "status_code": 404},
        )
    return {"success": True, "status_code": 200, "data": evidence.to_dict()}


@router.get("/jobs/{job_id}/evidence/{evidence_id}")
def get_job_evidence_metadata_endpoint(job_id: str = Path(...), evidence_id: str = Path(...)):
    """Retrieves evidence metadata verifying it belongs to the specified job."""
    evidence = EVIDENCE_SERVICE.get_evidence(evidence_id)
    if not evidence or evidence.job_id != job_id:
        return JSONResponse(
            status_code=404,
            content={"error": "EVIDENCE_NOT_FOUND", "message": f"Evidence '{evidence_id}' not found for job '{job_id}'.", "success": False, "status_code": 404},
        )
    return {"success": True, "status_code": 200, "data": evidence.to_dict()}


@router.get("/evidence/{evidence_id}/download")
def download_evidence_endpoint(
    evidence_id: str = Path(...),
    job_id: Optional[str] = Query(None, description="Optional job ID check"),
):
    """Downloads the physical file content with proper MIME and disposition headers."""
    try:
        content, filename, mime_type = EVIDENCE_SERVICE.download_evidence(
            evidence_id=evidence_id,
            requesting_job_id=job_id,
        )
        return Response(
            content=content,
            media_type=mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(content)),
            },
        )
    except EvidenceNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "EVIDENCE_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except EvidenceSecurityError as e:
        return JSONResponse(
            status_code=403,
            content={"error": e.error_code, "message": e.message, "success": False, "status_code": 403},
        )


@router.get("/jobs/{job_id}/evidence/{evidence_id}/download")
def download_job_evidence_endpoint(job_id: str = Path(...), evidence_id: str = Path(...)):
    """Downloads file content verifying it belongs to job_id."""
    return download_evidence_endpoint(evidence_id=evidence_id, job_id=job_id)


# =============================================================================
# 4. Deletion Endpoint (Soft Delete)
# =============================================================================

@router.delete("/jobs/{job_id}/evidence/{evidence_id}")
def delete_job_evidence_endpoint(
    job_id: str = Path(...),
    evidence_id: str = Path(...),
    reason: Optional[str] = Query("", description="Reason for deletion"),
    user_id: Optional[str] = Query("SYSTEM", description="User ID"),
):
    """Soft-deletes / archives an evidence record."""
    try:
        # Check job matches
        evidence = EVIDENCE_SERVICE.get_evidence(evidence_id)
        if not evidence or evidence.job_id != job_id:
            return JSONResponse(
                status_code=404,
                content={"error": "EVIDENCE_NOT_FOUND", "message": f"Evidence '{evidence_id}' not found for job '{job_id}'.", "success": False, "status_code": 404},
            )
        archived = EVIDENCE_SERVICE.delete_evidence(evidence_id, user_id=user_id, reason=reason)
        return {
            "success": True,
            "status_code": 200,
            "message": f"Evidence '{evidence_id}' successfully archived.",
            "data": archived.to_dict(),
        }
    except EvidenceWorkflowStateError as e:
        return JSONResponse(
            status_code=400,
            content={"error": e.error_code, "message": e.message, "success": False, "status_code": 400},
        )
    except EvidenceNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "EVIDENCE_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )


@router.delete("/evidence/{evidence_id}")
def delete_evidence_direct_endpoint(
    evidence_id: str = Path(...),
    reason: Optional[str] = Query(""),
    user_id: Optional[str] = Query("SYSTEM"),
):
    """Direct soft-delete endpoint by evidence ID."""
    try:
        archived = EVIDENCE_SERVICE.delete_evidence(evidence_id, user_id=user_id, reason=reason)
        return {
            "success": True,
            "status_code": 200,
            "message": f"Evidence '{evidence_id}' successfully archived.",
            "data": archived.to_dict(),
        }
    except EvidenceWorkflowStateError as e:
        return JSONResponse(
            status_code=400,
            content={"error": e.error_code, "message": e.message, "success": False, "status_code": 400},
        )
    except EvidenceNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "EVIDENCE_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
