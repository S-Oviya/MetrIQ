"""P6 orchestration over P2/P3 source data and P6 report persistence."""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from app.database.connection import get_reports_dir
from app.instruments.service import INSTRUMENT_SERVICE
from app.jobs.service import TEST_JOB_SERVICE
from .generator import ReportGenerator
from .models import ReportStatus, ReportType
from .repository import REPORT_REPOSITORY, ReportRepository

GENERATABLE_JOB_STATUSES = {"APPROVED", "REJECTED", "CLOSED", "CERTIFIED", "REPORT_GENERATED"}

def _now() -> str: return datetime.now(timezone.utc).isoformat()
def _type(value: str) -> Optional[str]:
    candidate = str(value or "").strip().upper()
    return candidate if candidate in {item.value for item in ReportType} else None

class ReportService:
    """Creates report snapshots from P2/P3 data without altering those sources."""
    def __init__(self, repository: ReportRepository = REPORT_REPOSITORY, generator: Optional[ReportGenerator] = None) -> None:
        self.repository, self.generator = repository, generator or ReportGenerator()
        self._pdf_cache: Dict[str, bytes] = {}

    def create(self, job_id: str, report_type: str, created_by: str = "SYSTEM") -> Dict[str, Any]:
        job = TEST_JOB_SERVICE.get_job(job_id)
        if not job: return {"success":False,"status_code":404,"message":f"Test job '{job_id}' was not found."}
        canonical_type = _type(report_type)
        if not canonical_type: return {"success":False,"status_code":422,"message":"A supported report type is required.","details":{"allowed_report_types":[item.value for item in ReportType]}}
        if canonical_type == ReportType.REJECTION_DOCUMENT.value and str(job.get("status", "")).upper() != "REJECTED":
            return {"success":False,"status_code":409,"message":"A rejection document requires a rejected P3 job outcome.","details":{"job_status":job.get("status")}}
        existing = next((item for item in self.repository.list() if item.get("job_id") == job_id and _type(str(item.get("template_report_type") or item.get("report_type"))) == canonical_type), None)
        if existing: return {"success":True,"status_code":200,"data":existing,"message":"Existing report record returned."}
        instrument = INSTRUMENT_SERVICE.get_instrument(str(job.get("instrument_id") or "")) or {}
        record_id = f"RPT-{uuid4().hex[:10].upper()}"; year = datetime.now(timezone.utc).year
        report = {"report_id":record_id,"report_number":f"METRIQ/{year}/{record_id.split('-')[-1]}","report_type":canonical_type,"template_report_type":canonical_type,"job_id":job_id,"job_number":job.get("job_number"),"instrument_id":job.get("instrument_id"),"serial_number":instrument.get("serial_number"),"approval_number":job.get("model_approval_id") or instrument.get("model_approval_number"),"status":ReportStatus.DRAFT.value,"report_status":ReportStatus.DRAFT.value,"generation_status":"NOT_GENERATED","created_at":_now(),"updated_at":_now(),"created_by":created_by,"generated_at":None,"generated_by":None,"html":None,"job_snapshot":None,"instrument_snapshot":None,"approval_snapshot":None,"audit_snapshot":[],"job_status_at_creation":str(job.get("status","")).upper()}
        return {"success":True,"status_code":201,"data":self.repository.save(report)}

    def generate(self, report_id: str, generated_by: str = "SYSTEM") -> Dict[str, Any]:
        report = self.repository.get(report_id)
        if not report: return {"success":False,"status_code":404,"message":f"Report '{report_id}' was not found."}
        is_rejection_document = _type(str(report.get("template_report_type") or report.get("report_type"))) == ReportType.REJECTION_DOCUMENT.value
        if report.get("generation_status") == "GENERATED" and not is_rejection_document: return {"success":True,"status_code":200,"data":report,"message":"Report has already been generated."}
        job = TEST_JOB_SERVICE.get_job(str(report.get("job_id") or ""))
        if not job: return {"success":False,"status_code":409,"message":"The linked test job is no longer available."}
        if is_rejection_document and str(job.get("status", "")).upper() not in ("REJECTED", "CLOSED"):
            return {"success":False,"status_code":409,"message":"A rejection document requires a rejected P3 job outcome.","details":{"job_status":job.get("status")}}
        if is_rejection_document and str(job.get("status", "")).upper() == "CLOSED" and str(report.get("job_status_at_creation","")).upper() != "CLOSED":
            return {"success":False,"status_code":409,"message":"A rejection document requires a rejected P3 job outcome.","details":{"job_status":job.get("status")}}
        if report.get("generation_status") == "GENERATED": return {"success":True,"status_code":200,"data":report,"message":"Report has already been generated."}
        if str(job.get("status", "")).upper() not in GENERATABLE_JOB_STATUSES: return {"success":False,"status_code":409,"message":"Report generation is available only after the linked job has been approved, rejected, or closed.","details":{"job_status":job.get("status"),"allowed_statuses":sorted(GENERATABLE_JOB_STATUSES)}}
        instrument = INSTRUMENT_SERVICE.get_instrument(str(job.get("instrument_id") or ""))
        if not instrument: return {"success":False,"status_code":409,"message":"The linked instrument is no longer available."}
        try:
            report["generation_status"] = "GENERATING"; self.repository.save(report)
            output = self.generator.generate(report, job, instrument); rejected = str(job.get("status")).upper() == "REJECTED" or report.get("template_report_type") == ReportType.REJECTION_DOCUMENT.value
            pdf_bytes = output.get("pdf")
            pdf_path_str = None
            if pdf_bytes:
                self._pdf_cache[report_id] = pdf_bytes
                try:
                    disk_pdf = get_reports_dir() / f"{report_id}.pdf"
                    disk_pdf.write_bytes(pdf_bytes)
                    pdf_path_str = str(disk_pdf)
                except Exception:
                    pass
            report_num = str(report.get("report_number") or report_id).replace("/", "_").replace("\\", "_")
            report.update({"status":ReportStatus.REJECTED.value if rejected else ReportStatus.ISSUED.value,"report_status":ReportStatus.REJECTED.value if rejected else ReportStatus.ISSUED.value,"generation_status":"GENERATED","generated_at":output["generated_at"],"generated_by":generated_by,"template_name":output["template_name"],"template_version":output["template_version"],"html":output["html"],"has_pdf":bool(pdf_bytes),"pdf_filename":f"{report_num}.pdf","pdf_path":pdf_path_str,"job_snapshot":job,"instrument_snapshot":instrument,"approval_snapshot":output["context"]["approval"],"audit_snapshot":list(job.get("state_history") or []),"evidence_metadata":output["context"]["evidence"],"contains_demo_data":output["context"]["contains_demo_data"]})
            saved = self.repository.save(report)
            # Emit audit event for report generation
            try:
                from app.audit.service import AUDIT_SERVICE
                from app.audit.models import AuditAction, EntityType
                AUDIT_SERVICE.record_audit(
                    actor=str(generated_by or "SYSTEM"),
                    action=AuditAction.REPORT_GENERATED,
                    entity_type=EntityType.JOB,
                    entity_id=str(report.get("job_id") or ""),
                    new_value={
                        "report_id": report.get("report_id"),
                        "report_number": report.get("report_number"),
                        "report_type": report.get("template_report_type") or report.get("report_type"),
                        "generation_status": "GENERATED",
                        "contains_demo_data": output["context"]["contains_demo_data"],
                    },
                    metadata={
                        "job_id": str(report.get("job_id") or ""),
                        "report_id": report.get("report_id"),
                        "generated_by": str(generated_by or "SYSTEM"),
                    },
                    job_id=str(report.get("job_id") or ""),
                )
            except Exception:
                pass
            return {"success":True,"status_code":200,"data":saved}
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Report generation failed for %s: %s", report_id, exc)
            report.update({"generation_status":"FAILED","generation_error":f"The report snapshot could not be assembled: {exc}"}); self.repository.save(report)
            return {"success":False,"status_code":500,"message":report["generation_error"]}

    def get(self, report_id: str) -> Optional[Dict[str, Any]]: return self.repository.get(report_id)
    def get_html(self, report_id: str) -> Optional[str]:
        report = self.get(report_id); return str(report.get("html")) if report and report.get("html") else None
    def get_pdf(self, report_id: str) -> Optional[bytes]:
        report = self.get(report_id)
        if not report:
            return None
        if report_id in self._pdf_cache:
            return self._pdf_cache[report_id]
        disk_pdf = get_reports_dir() / f"{report_id}.pdf"
        if disk_pdf.is_file():
            try:
                pdf_bytes = disk_pdf.read_bytes()
                self._pdf_cache[report_id] = pdf_bytes
                return pdf_bytes
            except Exception:
                pass
        if report.get("generation_status") == "GENERATED":
            job = report.get("job_snapshot") or TEST_JOB_SERVICE.get_job(str(report.get("job_id") or ""))
            inst_id = str((job or {}).get("instrument_id") or report.get("instrument_id") or "")
            instrument = report.get("instrument_snapshot") or INSTRUMENT_SERVICE.get_instrument(inst_id)
            if job and instrument:
                context = self.generator.assemble(report, job, instrument)
                pdf_bytes = self.generator.render_pdf(context)
                self._pdf_cache[report_id] = pdf_bytes
                try:
                    disk_pdf.write_bytes(pdf_bytes)
                except Exception:
                    pass
                return pdf_bytes
        return None
    def list(self, search: Optional[str] = None, report_status: Optional[str] = None, generation_status: Optional[str] = None, sort_by: str = "created_at", sort_direction: str = "desc") -> List[Dict[str, Any]]:
        rows = self.repository.list(); term = str(search or "").lower().strip()
        if term: rows = [row for row in rows if term in " ".join(str(row.get(key, "")) for key in ("report_id","report_number","job_id","job_number","instrument_id","serial_number","approval_number","report_type")).lower()]
        if report_status: rows = [row for row in rows if row.get("report_status") == report_status or row.get("status") == report_status]
        if generation_status: rows = [row for row in rows if row.get("generation_status") == generation_status]
        key = sort_by if sort_by in {"created_at","generated_at","report_number","report_status","generation_status"} else "created_at"; rows.sort(key=lambda row:str(row.get(key) or ""),reverse=sort_direction.lower() != "asc")
        return [self.summary(row) for row in rows]
    def archive_search(self, **filters: Optional[str]) -> List[Dict[str, Any]]:
        requested_type = filters.get("report_type")
        rows = self.repository.search(serial_number=filters.get("serial_number"),instrument_id=filters.get("instrument_id"),job_id=filters.get("job_id"),report_number=filters.get("report_number"),approval_number=filters.get("approval_number"),status=filters.get("report_status") or filters.get("status"),date_from=filters.get("date_from"),date_to=filters.get("date_to"))
        if requested_type:
            canonical_type = _type(str(requested_type))
            rows = [row for row in rows if _type(str(row.get("template_report_type") or row.get("report_type"))) == canonical_type]
        term = str(filters.get("search") or "").lower().strip()
        if term: rows = [row for row in rows if term in " ".join(str(row.get(k, "")) for k in ("serial_number","instrument_id","job_id","report_number","approval_number")).lower()]
        return [self.summary(row) for row in rows]
    def update_status(self, report_id: str, status: str) -> Optional[Dict[str, Any]]: return self.repository.update_status(report_id, status)
    @staticmethod
    def summary(report: Dict[str, Any]) -> Dict[str, Any]:
        instrument, job = report.get("instrument_snapshot") or {}, report.get("job_snapshot") or {}
        report_num = str(report.get("report_number") or report.get("report_id") or "").replace("/", "_").replace("\\", "_")
        return {key:report.get(key) for key in ("report_id","report_number","report_type","job_id","job_number","instrument_id","serial_number","approval_number","created_at","generated_at","generation_status")} | {"instrument":instrument.get("model_name") or instrument.get("model_number"),"customer_name":(instrument.get("location") or instrument.get("customer_info") or {}).get("customer_name"),"test_date":job.get("completed_at") or job.get("scheduled_date"),"report_status":report.get("report_status") or report.get("status"),"contains_demo_data":bool(report.get("contains_demo_data")),"has_pdf":bool(report.get("has_pdf") or report.get("generation_status") == "GENERATED"),"pdf_filename":report.get("pdf_filename") or f"{report_num}.pdf"}
    def dashboard_metrics(self) -> Dict[str, int]:
        jobs = TEST_JOB_SERVICE.list_jobs(); states = [str(job.get("status", "")).upper() for job in jobs]
        due = 0; cutoff = date.today() + timedelta(days=30)
        for instrument in INSTRUMENT_SERVICE.list_instruments():
            try: due += date.fromisoformat(str(instrument.get("next_re_verification_due"))[:10]) <= cutoff
            except (TypeError, ValueError): pass
        reports = self.repository.list()
        return {"active_jobs":sum(state in {"CREATED","VALIDATED","TEST_PLAN_GENERATED","READY_FOR_TEST","IN_TESTING","IN_PROGRESS","ASSIGNED"} for state in states),"pending_reviews":sum(state in {"UNDER_REVIEW","TEST_COMPLETED","REVIEW"} for state in states),"failed_tests":sum(state == "REJECTED" for state in states),"retests":sum(str(job.get("job_type", "")).upper() == "RETEST" for job in jobs),"completed_jobs":sum(state in {"APPROVED","CLOSED","CERTIFIED","REPORT_GENERATED"} for state in states),"verification_due":due,"reports_generated":sum(row.get("generation_status") == "GENERATED" for row in reports),"reports_pending_generation":sum(row.get("generation_status") != "GENERATED" for row in reports)}

REPORT_SERVICE = ReportService()
