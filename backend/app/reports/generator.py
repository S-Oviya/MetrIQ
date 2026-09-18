"""P6 report context assembly and printable HTML generation."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from .mock_data_adapter import MockReportDataAdapter
from .templates import TEMPLATE_VERSION, TITLES, render_report_html

class ReportGenerator:
    """Consumes P2/P3 snapshots; it never computes a metrological outcome."""
    def __init__(self, fallback_adapter: Optional[MockReportDataAdapter] = None) -> None: self.fallback_adapter = fallback_adapter or MockReportDataAdapter()
    def assemble(self, report: Dict[str, Any], job: Dict[str, Any], instrument: Dict[str, Any]) -> Dict[str, Any]:
        job_id = str(job.get("job_id") or report.get("job_id") or "")
        approval = {"approval_number": job.get("model_approval_id") or instrument.get("model_approval_number"), "regulatory_profile_id": job.get("regulatory_profile_id"), "regulatory_rule_references": job.get("regulatory_rule_references") or [], "gatc_reference": job.get("gatc_reference")}
        plan = job.get("test_plan") or {}
        context = {"report":report,"job":job,"instrument":instrument,"approval":approval,"results":{"outcome":job.get("status"),"mpe_reference":plan.get("mpe_reference"),"mpe_information":plan.get("mpe_information") or plan.get("summary")},"observations":self.fallback_adapter.test_observations(job_id),"environment":self.fallback_adapter.environmental_readings(job_id),"reviewer":self.fallback_adapter.reviewer_information(job_id),"test_weight_certificate":self.fallback_adapter.test_weight_certificate(job_id),"evidence":self.fallback_adapter.evidence_metadata(job_id)}
        context["contains_demo_data"] = any(item.get("is_demo") for item in [context["environment"],context["reviewer"],context["test_weight_certificate"]]+context["observations"]+context["evidence"])
        return context
    def generate(self, report: Dict[str, Any], job: Dict[str, Any], instrument: Dict[str, Any]) -> Dict[str, Any]:
        generated_at = datetime.now(timezone.utc).isoformat()
        printable_report = dict(report)
        printable_report["generated_at"] = generated_at
        printable_report["report_type"] = printable_report.get("template_report_type") or printable_report.get("report_type")
        context = self.assemble(printable_report, job, instrument); report_type = str(printable_report.get("report_type"))
        return {"html":render_report_html(context),"template_name":TITLES.get(report_type,report_type),"template_version":TEMPLATE_VERSION,"generated_at":generated_at,"context":context}
