"""
MetrIQ P5 Audit Trail REST API Router
=====================================
Person 5: Workflow + Evidence Engineer

Exposes read-only RESTful endpoints for:
- Querying job-centric audit trail (/jobs/{jobId}/audit)
- Querying entity-centric audit trail (/audit/{entityType}/{entityId})
- Filtering audit logs (/audit)
- Strictly rejects mutations (append-only statutory immutability)
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Header, HTTPException, Path, Query
from fastapi.responses import JSONResponse

from .models import AuditAction, EntityType
from .service import AUDIT_SERVICE

router = APIRouter(tags=["Audit Trail & Traceability"])


# =============================================================================
# 1. Job Audit Trail Endpoint
# =============================================================================

@router.get("/jobs/{job_id}/audit", status_code=200)
def get_job_audit_trail_endpoint(job_id: str = Path(..., description="Job ID")):
    """
    Retrieves the complete, chronological statutory audit trail for a test job.
    Includes state changes, equipment associations, environment readings,
    test attempts, evidence uploads, and supervisory review actions.
    """
    clean_id = str(job_id).strip()
    logs = AUDIT_SERVICE.get_job_audit_trail(clean_id)
    return {
        "success": True,
        "status_code": 200,
        "job_id": clean_id,
        "count": len(logs),
        "data": [log.to_dict() for log in logs],
    }


@router.get("/test-jobs/{job_id}/audit", status_code=200)
def get_test_job_audit_trail_endpoint(job_id: str = Path(...)):
    """Alias for /jobs/{job_id}/audit."""
    return get_job_audit_trail_endpoint(job_id=job_id)


# =============================================================================
# 2. Entity Audit Trail Endpoint
# =============================================================================

@router.get("/audit/{entity_type}/{entity_id}", status_code=200)
def get_entity_audit_trail_endpoint(
    entity_type: str = Path(..., description="Entity category: JOB, EQUIPMENT, TEST_STANDARD, ENVIRONMENT, TEST_ATTEMPT, EVIDENCE, REVIEW"),
    entity_id: str = Path(..., description="Target entity identifier"),
):
    """Retrieves chronological audit trail for a specific domain entity."""
    try:
        clean_etype = EntityType.from_value(entity_type)
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "INVALID_ENTITY_TYPE", "message": str(e), "success": False, "status_code": 400},
        )

    clean_id = str(entity_id).strip()
    logs = AUDIT_SERVICE.get_entity_audit_trail(clean_etype, clean_id)
    return {
        "success": True,
        "status_code": 200,
        "entity_type": clean_etype.value,
        "entity_id": clean_id,
        "count": len(logs),
        "data": [log.to_dict() for log in logs],
    }


# =============================================================================
# 3. Filtered Audit Query Endpoint
# =============================================================================

@router.get("/audit", status_code=200)
def query_audit_logs_endpoint(
    action: Optional[str] = Query(None, description="Filter by AuditAction"),
    actor: Optional[str] = Query(None, description="Filter by user/actor ID"),
    entity_type: Optional[str] = Query(None, description="Filter by EntityType"),
    from_date: Optional[str] = Query(None, description="ISO-8601 start timestamp filter"),
    to_date: Optional[str] = Query(None, description="ISO-8601 end timestamp filter"),
):
    """Queries statutory audit logs across all entities with optional filters."""
    try:
        logs = AUDIT_SERVICE.query_audit_logs(
            action=action,
            actor=actor,
            entity_type=entity_type,
            from_date=from_date,
            to_date=to_date,
        )
        return {
            "success": True,
            "status_code": 200,
            "count": len(logs),
            "data": [log.to_dict() for log in logs],
        }
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "VALIDATION_ERROR", "message": str(e), "success": False, "status_code": 400},
        )
