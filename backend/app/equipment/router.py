"""
MetrIQ P5 Equipment & Test Standards REST API Router
====================================================
Person 5: Workflow + Evidence Engineer

Exposes RESTful endpoints for:
- Equipment CRUD & status updates
- Test Standards CRUD & status updates
- Job association with calibration validity enforcement
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Body, Path, Query
from fastapi.responses import JSONResponse

from app.workflow.service import JobNotFoundError
from .models import EquipmentStatus
from .repository import DuplicateSerialNumberError
from .service import (
    CalibrationExpiredError,
    EQUIPMENT_SERVICE,
    EquipmentNotFoundError,
    EquipmentValidationError,
    StandardNotFoundError,
)

router = APIRouter(tags=["Equipment & Test Standards"])


# =============================================================================
# Equipment Endpoints
# =============================================================================

@router.post("/equipment")
def create_equipment_endpoint(payload: Dict[str, Any] = Body(...)):
    """Registers a new inspection equipment item."""
    try:
        item = EQUIPMENT_SERVICE.create_equipment(payload)
        return {
            "success": True,
            "status_code": 201,
            "message": f"Equipment '{item.name}' successfully registered.",
            "data": item.to_dict(),
        }
    except EquipmentValidationError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "VALIDATION_ERROR", "message": e.message, "field": e.field, "success": False, "status_code": 400},
        )
    except DuplicateSerialNumberError as e:
        return JSONResponse(
            status_code=409,
            content={"error": "DUPLICATE_SERIAL_NUMBER", "message": str(e), "success": False, "status_code": 409},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_SERVER_ERROR", "message": str(e), "success": False, "status_code": 500},
        )


@router.get("/equipment")
def list_equipment_endpoint(
    status: Optional[str] = Query(None),
    equipment_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    """Lists inspection equipment with optional filters."""
    items = EQUIPMENT_SERVICE.list_equipment(status=status, equipment_type=equipment_type, search=search)
    return {
        "success": True,
        "status_code": 200,
        "count": len(items),
        "data": [item.to_dict() for item in items],
    }


@router.get("/equipment/{equipment_id}")
def get_equipment_endpoint(equipment_id: str = Path(...)):
    """Retrieves single equipment by ID."""
    item = EQUIPMENT_SERVICE.get_equipment(equipment_id)
    if not item:
        return JSONResponse(
            status_code=404,
            content={"error": "EQUIPMENT_NOT_FOUND", "message": f"Equipment '{equipment_id}' not found.", "success": False, "status_code": 404},
        )
    return {"success": True, "status_code": 200, "data": item.to_dict()}


@router.put("/equipment/{equipment_id}")
def update_equipment_endpoint(equipment_id: str = Path(...), payload: Dict[str, Any] = Body(...)):
    """Updates equipment details."""
    try:
        updated = EQUIPMENT_SERVICE.update_equipment(equipment_id, payload)
        return {
            "success": True,
            "status_code": 200,
            "message": f"Equipment '{equipment_id}' successfully updated.",
            "data": updated.to_dict(),
        }
    except EquipmentNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "EQUIPMENT_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except EquipmentValidationError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "VALIDATION_ERROR", "message": e.message, "field": e.field, "success": False, "status_code": 400},
        )
    except DuplicateSerialNumberError as e:
        return JSONResponse(
            status_code=409,
            content={"error": "DUPLICATE_SERIAL_NUMBER", "message": str(e), "success": False, "status_code": 409},
        )


@router.patch("/equipment/{equipment_id}/status")
def change_equipment_status_endpoint(equipment_id: str = Path(...), payload: Dict[str, Any] = Body(...)):
    """Updates operational status of an equipment item."""
    new_status = payload.get("status")
    reason = payload.get("reason")
    if not new_status:
        return JSONResponse(
            status_code=400,
            content={"error": "MISSING_STATUS", "message": "Field 'status' is required.", "success": False, "status_code": 400},
        )
    try:
        updated = EQUIPMENT_SERVICE.change_equipment_status(equipment_id, new_status, reason=reason)
        return {
            "success": True,
            "status_code": 200,
            "message": f"Equipment '{equipment_id}' status changed to {updated.status.value}.",
            "data": updated.to_dict(),
        }
    except EquipmentNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "EQUIPMENT_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "INVALID_STATUS", "message": str(e), "success": False, "status_code": 400},
        )


# =============================================================================
# Test Standards Endpoints
# =============================================================================

@router.post("/test-standards")
def create_test_standard_endpoint(payload: Dict[str, Any] = Body(...)):
    """Registers a new test standard / reference weight."""
    try:
        std = EQUIPMENT_SERVICE.create_test_standard(payload)
        return {
            "success": True,
            "status_code": 201,
            "message": f"Test standard '{std.nominal_value} {std.unit}' successfully registered.",
            "data": std.to_dict(),
        }
    except EquipmentValidationError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "VALIDATION_ERROR", "message": e.message, "field": e.field, "success": False, "status_code": 400},
        )
    except DuplicateSerialNumberError as e:
        return JSONResponse(
            status_code=409,
            content={"error": "DUPLICATE_SERIAL_NUMBER", "message": str(e), "success": False, "status_code": 409},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_SERVER_ERROR", "message": str(e), "success": False, "status_code": 500},
        )


@router.get("/test-standards")
def list_test_standards_endpoint(
    status: Optional[str] = Query(None),
    accuracy_class: Optional[str] = Query(None),
    unit: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    """Lists test standards with optional filters."""
    items = EQUIPMENT_SERVICE.list_test_standards(status=status, accuracy_class=accuracy_class, unit=unit, search=search)
    return {
        "success": True,
        "status_code": 200,
        "count": len(items),
        "data": [item.to_dict() for item in items],
    }


@router.get("/test-standards/{standard_id}")
def get_test_standard_endpoint(standard_id: str = Path(...)):
    """Retrieves single test standard by ID."""
    std = EQUIPMENT_SERVICE.get_test_standard(standard_id)
    if not std:
        return JSONResponse(
            status_code=404,
            content={"error": "STANDARD_NOT_FOUND", "message": f"Test standard '{standard_id}' not found.", "success": False, "status_code": 404},
        )
    return {"success": True, "status_code": 200, "data": std.to_dict()}


@router.put("/test-standards/{standard_id}")
def update_test_standard_endpoint(standard_id: str = Path(...), payload: Dict[str, Any] = Body(...)):
    """Updates test standard details."""
    try:
        updated = EQUIPMENT_SERVICE.update_test_standard(standard_id, payload)
        return {
            "success": True,
            "status_code": 200,
            "message": f"Test standard '{standard_id}' successfully updated.",
            "data": updated.to_dict(),
        }
    except StandardNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "STANDARD_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except EquipmentValidationError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "VALIDATION_ERROR", "message": e.message, "field": e.field, "success": False, "status_code": 400},
        )
    except DuplicateSerialNumberError as e:
        return JSONResponse(
            status_code=409,
            content={"error": "DUPLICATE_SERIAL_NUMBER", "message": str(e), "success": False, "status_code": 409},
        )


@router.patch("/test-standards/{standard_id}/status")
def change_test_standard_status_endpoint(standard_id: str = Path(...), payload: Dict[str, Any] = Body(...)):
    """Updates operational status of a test standard."""
    new_status = payload.get("status")
    if not new_status:
        return JSONResponse(
            status_code=400,
            content={"error": "MISSING_STATUS", "message": "Field 'status' is required.", "success": False, "status_code": 400},
        )
    try:
        updated = EQUIPMENT_SERVICE.change_test_standard_status(standard_id, new_status)
        return {
            "success": True,
            "status_code": 200,
            "message": f"Test standard '{standard_id}' status changed to {updated.status.value}.",
            "data": updated.to_dict(),
        }
    except StandardNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "STANDARD_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "INVALID_STATUS", "message": str(e), "success": False, "status_code": 400},
        )


# =============================================================================
# Job Association Endpoints
# =============================================================================

@router.post("/jobs/{job_id}/equipment")
@router.post("/test-jobs/{job_id}/equipment")
def associate_job_equipment_endpoint(job_id: str = Path(...), payload: Dict[str, Any] = Body(...)):
    """
    Associates an equipment item with a job, enforcing calibration validity.
    """
    equipment_id = payload.get("equipment_id") or payload.get("id")
    if not equipment_id:
        return JSONResponse(
            status_code=400,
            content={"error": "MISSING_EQUIPMENT_ID", "message": "Field 'equipment_id' is required.", "success": False, "status_code": 400},
        )
    try:
        job = EQUIPMENT_SERVICE.associate_equipment_with_job(job_id=job_id, equipment_id=equipment_id)
        associated_items = EQUIPMENT_SERVICE.get_job_equipment(job_id)
        return {
            "success": True,
            "status_code": 200,
            "message": f"Equipment '{equipment_id}' associated with job '{job_id}'.",
            "job_id": job.job_id,
            "equipment_ids": list(job.equipment_ids),
            "equipment": [item.to_dict() for item in associated_items],
        }
    except JobNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "JOB_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except EquipmentNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "EQUIPMENT_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except CalibrationExpiredError as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": e.error_code,
                "message": e.message,
                "item_id": e.item_id,
                "serial_number": e.serial_number,
                "success": False,
                "status_code": 400,
            },
        )


@router.get("/jobs/{job_id}/equipment")
@router.get("/test-jobs/{job_id}/equipment")
def get_job_equipment_endpoint(job_id: str = Path(...)):
    """Retrieves all equipment items associated with a job."""
    try:
        items = EQUIPMENT_SERVICE.get_job_equipment(job_id)
        return {
            "success": True,
            "status_code": 200,
            "job_id": job_id,
            "count": len(items),
            "data": [item.to_dict() for item in items],
        }
    except JobNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "JOB_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )


@router.post("/jobs/{job_id}/test-standards")
@router.post("/test-jobs/{job_id}/test-standards")
def associate_job_test_standard_endpoint(job_id: str = Path(...), payload: Dict[str, Any] = Body(...)):
    """
    Associates a test standard / reference weight with a job, enforcing calibration validity.
    """
    standard_id = payload.get("test_standard_id") or payload.get("standard_id") or payload.get("id")
    if not standard_id:
        return JSONResponse(
            status_code=400,
            content={"error": "MISSING_STANDARD_ID", "message": "Field 'test_standard_id' is required.", "success": False, "status_code": 400},
        )
    try:
        job = EQUIPMENT_SERVICE.associate_test_standard_with_job(job_id=job_id, standard_id=standard_id)
        associated_standards = EQUIPMENT_SERVICE.get_job_test_standards(job_id)
        return {
            "success": True,
            "status_code": 200,
            "message": f"Test standard '{standard_id}' associated with job '{job_id}'.",
            "job_id": job.job_id,
            "test_standard_ids": list(job.test_standard_ids),
            "test_standards": [item.to_dict() for item in associated_standards],
        }
    except JobNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "JOB_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except StandardNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "STANDARD_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
    except CalibrationExpiredError as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": e.error_code,
                "message": e.message,
                "item_id": e.item_id,
                "serial_number": e.serial_number,
                "success": False,
                "status_code": 400,
            },
        )


@router.get("/jobs/{job_id}/test-standards")
@router.get("/test-jobs/{job_id}/test-standards")
def get_job_test_standards_endpoint(job_id: str = Path(...)):
    """Retrieves all test standards associated with a job."""
    try:
        items = EQUIPMENT_SERVICE.get_job_test_standards(job_id)
        return {
            "success": True,
            "status_code": 200,
            "job_id": job_id,
            "count": len(items),
            "data": [item.to_dict() for item in items],
        }
    except JobNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"error": "JOB_NOT_FOUND", "message": str(e), "success": False, "status_code": 404},
        )
