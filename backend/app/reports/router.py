"""FastAPI surface for P6 reports, dashboard metrics, and archive retrieval."""
from typing import Any, Optional
try:
    from fastapi import APIRouter, Body, HTTPException
    from fastapi.responses import HTMLResponse
    router = APIRouter(tags=["Reports & Archive"])
except ImportError:  # Keeps pure-Python service/test environments importable.
    router = None
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: Any): self.status_code, self.detail = status_code, detail
    def Body(default=None, **kwargs: Any): return default
    def _route(*args: Any, **kwargs: Any):
        def decorate(function: Any): return function
        return decorate
    class _NoFastApiRouter:
        get = staticmethod(_route)
        post = staticmethod(_route)
    router = _NoFastApiRouter()
    class HTMLResponse(str): pass
from app.api.schemas import success_envelope
from .service import REPORT_SERVICE

def _result(result: dict):
    if not result.get("success"): raise HTTPException(status_code=result.get("status_code",400), detail={"message":result.get("message","Report operation failed."),"details":result.get("details")})
    return success_envelope(result.get("data"), status_code=result.get("status_code",200), message=result.get("message"))

@router.get("/reports")
def list_reports(search: Optional[str]=None, report_status: Optional[str]=None, generation_status: Optional[str]=None, sort_by: str="created_at", sort_direction: str="desc"):
    rows=REPORT_SERVICE.list(search,report_status,generation_status,sort_by,sort_direction); return success_envelope(rows,meta={"count":len(rows)})
@router.post("/reports")
def create_report(payload: dict=Body(...)): return _result(REPORT_SERVICE.create(str(payload.get("job_id") or ""),str(payload.get("report_type") or ""),str(payload.get("created_by") or "SYSTEM")))
@router.post("/reports/generate")
def create_and_generate(payload: dict=Body(...)):
    created=REPORT_SERVICE.create(str(payload.get("job_id") or ""),str(payload.get("report_type") or ""),str(payload.get("created_by") or "SYSTEM"))
    if not created.get("success"): return _result(created)
    return _result(REPORT_SERVICE.generate(created["data"]["report_id"],str(payload.get("generated_by") or "SYSTEM")))
@router.get("/reports/{report_id}/html", response_class=HTMLResponse)
def report_html(report_id: str):
    html=REPORT_SERVICE.get_html(report_id)
    if not html: raise HTTPException(status_code=404,detail={"message":"Generated report HTML was not found."})
    return HTMLResponse(html)
@router.get("/reports/{report_id}")
def get_report(report_id: str):
    report=REPORT_SERVICE.get(report_id)
    if not report: raise HTTPException(status_code=404,detail={"message":f"Report '{report_id}' was not found."})
    return success_envelope(report)
@router.post("/reports/{report_id}/generate")
def generate_report(report_id: str,payload: Optional[dict]=Body(None)): return _result(REPORT_SERVICE.generate(report_id,str((payload or {}).get("generated_by") or "SYSTEM")))
@router.get("/reports/{report_id}/preview")
def preview_report(report_id: str):
    report=REPORT_SERVICE.get(report_id)
    if not report: raise HTTPException(status_code=404,detail={"message":f"Report '{report_id}' was not found."})
    if report.get("generation_status") != "GENERATED": raise HTTPException(status_code=409,detail={"message":"Generate the report before opening its preview."})
    return success_envelope(report)
@router.get("/dashboard/metrics")
def dashboard_metrics(): return success_envelope(REPORT_SERVICE.dashboard_metrics())
@router.get("/archive/search")
def archive_search(search: Optional[str]=None,serial_number: Optional[str]=None,instrument_id: Optional[str]=None,job_id: Optional[str]=None,report_number: Optional[str]=None,approval_number: Optional[str]=None,report_type: Optional[str]=None,status: Optional[str]=None,report_status: Optional[str]=None,date_from: Optional[str]=None,date_to: Optional[str]=None):
    rows=REPORT_SERVICE.archive_search(search=search,serial_number=serial_number,instrument_id=instrument_id,job_id=job_id,report_number=report_number,approval_number=approval_number,report_type=report_type,status=report_status or status,date_from=date_from,date_to=date_to); return success_envelope(rows,meta={"count":len(rows)})
