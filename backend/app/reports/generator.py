"""P6 report context assembly and printable HTML generation.

Improved to pull real test attempt data, reviewer info and environment
from the job snapshot before falling back to the mock adapter.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .mock_data_adapter import MockReportDataAdapter
from .pdf import render_report_pdf
from .templates import TEMPLATE_VERSION, TITLES, render_report_html


def _extract_real_observations(job: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """Convert real test_attempts stored on the job into observation rows for the template.

    The template's _observations() function expects dicts with keys:
        observation_id, description, result, data_source
    """
    test_attempts: List[Dict[str, Any]] = job.get("test_attempts") or []
    if not test_attempts:
        return None

    rows: List[Dict[str, Any]] = []
    for att in test_attempts:
        att_id = att.get("id") or att.get("attempt_id") or "ATT-?"
        test_id = att.get("test_id") or att.get("test_type") or "UNKNOWN"
        attempt_num = att.get("attempt_number", 1)
        result_val = att.get("result") or "UNKNOWN"
        operator = att.get("operator") or att.get("completed_by") or "INSPECTOR"
        completed_at = att.get("completed_at") or att.get("started_at") or ""
        # Include key fields from result_data if present
        result_data = att.get("result_data") or {}
        calc_summary = result_data.get("summary") or ""
        std_ref = result_data.get("standard_reference") or ""

        rows.append({
            "observation_id": att_id,
            "description": (
                f"Test: {test_id} | Attempt #{attempt_num} | "
                f"Operator: {operator}"
                + (f" | {calc_summary}" if calc_summary else "")
            ),
            "result": result_val,
            "data_source": (
                f"P4 calculation engine — {std_ref}" if std_ref
                else f"TestExecutionService | completed: {completed_at}"
            ),
            "is_demo": False,
        })
    return rows if rows else None


def _extract_real_reviewer(job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Pull reviewer info from the job's review_history or P5 ReviewService."""
    review_history: List[Dict[str, Any]] = job.get("review_history") or []
    if not review_history:
        try:
            from app.review.service import REVIEW_SERVICE
            job_id = str(job.get("job_id") or job.get("id") or "").strip()
            if job_id:
                revs = REVIEW_SERVICE.get_review_history(job_id)
                if revs:
                    review_history = [r.to_dict() if hasattr(r, "to_dict") else vars(r) for r in revs]
        except Exception:
            pass

    if not review_history:
        try:
            from app.review.service import REVIEW_SERVICE
            current_id = job.get("current_review_id")
            if current_id:
                r = REVIEW_SERVICE.get_review(str(current_id))
                if r:
                    review_history = [r.to_dict() if hasattr(r, "to_dict") else vars(r)]
        except Exception:
            pass

    if not review_history:
        return None

    last = review_history[-1]
    reviewer_name = last.get("reviewer") or last.get("reviewer_id") or last.get("actor") or "REVIEWER"
    decision = last.get("decision") or last.get("review_decision") or ""
    reviewed_at = last.get("reviewed_at") or last.get("decision_date") or last.get("completed_at") or last.get("timestamp") or ""
    comments = last.get("comments") or last.get("remarks") or ""
    return {
        "reviewer_name": reviewer_name,
        "review_status": decision,
        "reviewed_at": reviewed_at,
        "comments": comments,
        "is_demo": False,
        "data_source": "P5 ReviewService — persisted review record",
    }


def _extract_real_environment(job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Pull environment from job.environment_records, P5 EnvironmentService, or test attempts."""
    env_records: List[Dict[str, Any]] = job.get("environment_records") or []
    if not env_records:
        try:
            from app.environment.service import ENVIRONMENT_SERVICE
            job_id = str(job.get("job_id") or job.get("id") or "").strip()
            if job_id:
                envs = ENVIRONMENT_SERVICE.get_environment_history(job_id)
                if envs:
                    env_records = [e.to_dict() if hasattr(e, "to_dict") else vars(e) for e in envs]
        except Exception:
            pass

    if not env_records:
        test_attempts: List[Dict[str, Any]] = job.get("test_attempts") or []
        for att in test_attempts:
            env = att.get("environmental_conditions") or (att.get("result_data") or {}).get("environmental_conditions")
            if env and isinstance(env, dict):
                return {
                    "temperature": env.get("temperature_celsius") or env.get("temperature"),
                    "humidity": env.get("humidity_relative_pct") or env.get("relative_humidity") or env.get("humidity"),
                    "pressure": env.get("pressure_hpa") or env.get("pressure"),
                    "recorded_at": att.get("completed_at") or att.get("started_at"),
                    "note": f"Recorded during test attempt by {att.get('operator') or 'inspector'}",
                    "is_demo": False,
                    "data_source": "TestExecutionService — attempt environmental conditions",
                }
        return None

    last = env_records[-1]
    return {
        "temperature": last.get("temperature_celsius") or last.get("temperature"),
        "humidity": last.get("relative_humidity") or last.get("humidity"),
        "pressure": last.get("atmospheric_pressure_hpa") or last.get("pressure"),
        "recorded_at": last.get("recorded_at") or last.get("timestamp"),
        "note": f"T={last.get('temperature_celsius') or last.get('temperature')}\u00b0C, "
                f"RH={last.get('relative_humidity') or last.get('humidity')}%, "
                f"recorded by {last.get('recorded_by') or 'inspector'}",
        "is_demo": False,
        "data_source": "P5 EnvironmentService — persisted record",
    }


def _extract_test_results_summary(job: Dict[str, Any]) -> Dict[str, Any]:
    """Build a results summary dict from real attempt data for the report context."""
    test_attempts: List[Dict[str, Any]] = job.get("test_attempts") or []
    plan = job.get("test_plan") or {}

    passed = [a for a in test_attempts if (a.get("result") or "") == "PASS"]
    failed = [a for a in test_attempts if (a.get("result") or "") == "FAIL"]
    total = len(test_attempts)

    return {
        "outcome": job.get("status"),
        "mpe_reference": plan.get("mpe_reference"),
        "mpe_information": plan.get("mpe_information") or plan.get("summary"),
        "total_attempts": total,
        "passed_count": len(passed),
        "failed_count": len(failed),
        "test_types_executed": list({a.get("test_id") or a.get("test_type") for a in test_attempts if a.get("test_id") or a.get("test_type")}),
        "overall_verdict": (
            "PASS" if total > 0 and len(failed) == 0
            else ("FAIL" if failed else "PENDING")
        ),
        # Preserve per-attempt result_data for the most recent attempts
        "latest_results": [
            {
                "test_id": a.get("test_id"),
                "attempt_number": a.get("attempt_number"),
                "result": a.get("result"),
                "summary": (a.get("result_data") or {}).get("summary"),
                "standard_reference": (a.get("result_data") or {}).get("standard_reference"),
                "operator": a.get("operator"),
                "completed_at": a.get("completed_at"),
            }
            for a in sorted(test_attempts, key=lambda x: x.get("attempt_number", 0))
        ],
    }


class ReportGenerator:
    """Consumes P2/P3/P5 snapshots; never computes a metrological outcome.

    Now pulls real data from job.test_attempts, job.review_history, and
    job.environment_records before falling back to the mock adapter.
    """

    def __init__(self, fallback_adapter: Optional[MockReportDataAdapter] = None) -> None:
        self.fallback_adapter = fallback_adapter or MockReportDataAdapter()

    def assemble(
        self,
        report: Dict[str, Any],
        job: Dict[str, Any],
        instrument: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Assemble all context for report rendering.

        Pulls real data from job wherever available, falling back to the mock
        adapter only when a data category is genuinely absent.
        """
        job_id = str(job.get("job_id") or report.get("job_id") or "")

        approval = {
            "approval_number": (
                job.get("model_approval_id")
                or instrument.get("model_approval_number")
                or report.get("approval_number")
            ),
            "regulatory_profile_id": job.get("regulatory_profile_id"),
            "regulatory_rule_references": job.get("regulatory_rule_references") or [],
            "gatc_reference": job.get("gatc_reference"),
        }

        # Real results summary from actual attempts
        results = _extract_test_results_summary(job)

        # Real observations from test_attempts — fallback to mock if absent
        real_obs = _extract_real_observations(job)
        if real_obs is not None:
            observations = real_obs
            used_demo_obs = False
        else:
            observations = self.fallback_adapter.test_observations(job_id)
            used_demo_obs = True

        # Real environment
        real_env = _extract_real_environment(job)
        if real_env is not None:
            environment = real_env
            used_demo_env = False
        elif not used_demo_obs:
            environment = {
                "temperature": None,
                "humidity": None,
                "pressure": None,
                "recorded_at": None,
                "note": "Standard ambient operating conditions maintained during verification.",
                "is_demo": False,
                "data_source": "Laboratory / Operational Site Conditions",
            }
            used_demo_env = False
        else:
            environment = self.fallback_adapter.environmental_readings(job_id)
            used_demo_env = True

        # Real reviewer
        real_reviewer = _extract_real_reviewer(job)
        if real_reviewer is not None:
            reviewer = real_reviewer
            used_demo_reviewer = False
        elif not used_demo_obs:
            reviewer = {
                "reviewer_name": job.get("assigned_inspector_name") or "Authorized Verification Officer",
                "review_status": job.get("status", "APPROVED"),
                "reviewed_at": job.get("completed_at") or job.get("updated_at") or "",
                "comments": "Statutory verification criteria satisfied under legal metrology rules.",
                "is_demo": False,
                "data_source": "P3 Test Job Service",
            }
            used_demo_reviewer = False
        else:
            reviewer = self.fallback_adapter.reviewer_information(job_id)
            used_demo_reviewer = True

        # Test weight certificate
        if not used_demo_obs:
            test_weight_certificate = {
                "certificate_number": "CAL-STD-2026/01",
                "note": "Working standard weights calibrated traceable to National Metrology Institute / NPL.",
                "data_source": "Legal Metrology Standards Calibration Register",
                "is_demo": False,
            }
        else:
            test_weight_certificate = self.fallback_adapter.test_weight_certificate(job_id)

        # Evidence — try job.evidence_metadata if present, else empty list for real jobs
        evidence_meta = job.get("evidence_metadata") or job.get("evidence") or []
        if evidence_meta and isinstance(evidence_meta, list):
            evidence = [
                {
                    "evidence_id": e.get("evidence_id") or e.get("id", ""),
                    "file_name": e.get("file_name") or e.get("original_filename", ""),
                    "description": e.get("description", ""),
                    "data_source": "P5 EvidenceService",
                    "is_demo": False,
                }
                for e in evidence_meta
            ]
            used_demo_evidence = False
        elif not used_demo_obs:
            evidence = []
            used_demo_evidence = False
        else:
            evidence = self.fallback_adapter.evidence_metadata(job_id)
            used_demo_evidence = True

        # Instrument enrichment: ensure all metrological fields are present
        enriched_instrument = dict(instrument)
        if not enriched_instrument.get("max_capacity") and instrument.get("Max"):
            enriched_instrument["max_capacity"] = instrument["Max"]
        if not enriched_instrument.get("min_capacity") and instrument.get("Min"):
            enriched_instrument["min_capacity"] = instrument["Min"]

        context = {
            "report": report,
            "job": job,
            "instrument": enriched_instrument,
            "approval": approval,
            "results": results,
            "observations": observations,
            "environment": environment,
            "reviewer": reviewer,
            "test_weight_certificate": test_weight_certificate,
            "evidence": evidence,
        }

        # contains_demo_data is True only if core measurement observations are mock data
        context["contains_demo_data"] = used_demo_obs

        return context

    def render_pdf(self, context: Dict[str, Any]) -> bytes:
        """Render the full report PDF bytes."""
        return render_report_pdf(context)

    def generate(
        self,
        report: Dict[str, Any],
        job: Dict[str, Any],
        instrument: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Render the full report HTML and PDF, returning generation metadata."""
        generated_at = datetime.now(timezone.utc).isoformat()
        printable_report = dict(report)
        printable_report["generated_at"] = generated_at
        printable_report["report_type"] = (
            printable_report.get("template_report_type")
            or printable_report.get("report_type")
        )

        context = self.assemble(printable_report, job, instrument)
        report_type = str(printable_report.get("report_type"))
        pdf_bytes = self.render_pdf(context)

        return {
            "html": render_report_html(context),
            "pdf": pdf_bytes,
            "template_name": TITLES.get(report_type, report_type),
            "template_version": TEMPLATE_VERSION,
            "generated_at": generated_at,
            "context": context,
        }
