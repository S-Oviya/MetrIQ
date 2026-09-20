"""Mounted FastAPI coverage for the existing P6 report routes."""

from __future__ import annotations

from datetime import date
import unittest

from fastapi.testclient import TestClient

from app.main import app
import app.reports.router as reports_router
import app.reports.service as reports_service
from app.reports.repository import ReportRepository
from app.reports.service import ReportService


class _Jobs:
    """Focused upstream fixture for the existing report-service seam."""

    def get_job(self, job_id: str):
        if job_id != "JOB-API-1":
            return None
        return {
            "job_id": job_id,
            "job_number": "JOB/2026/API-1",
            "instrument_id": "INST-API-1",
            "status": "CLOSED",
            "job_type": "RE_VERIFICATION",
            "model_approval_id": "APR-API-1",
            "applicable_tests": ["Upstream test"],
            "test_plan": {"mpe_reference": "Upstream MPE reference"},
            "state_history": [],
        }

    def list_jobs(self):
        return [self.get_job("JOB-API-1")]


class _Instruments:
    """Focused instrument fixture used only to exercise report generation."""

    def get_instrument(self, instrument_id: str):
        if instrument_id != "INST-API-1":
            return None
        return {
            "instrument_id": instrument_id,
            "serial_number": "SER-API-1",
            "model_approval_number": "APR-API-1",
            "model_name": "API Test Scale",
            "manufacturer": "MetrIQ Test Manufacturer",
            "accuracy_class": "CLASS_III",
            "max_capacity": 15,
            "min_capacity": 0.1,
            "e": 0.005,
            "d": 0.005,
        }

    def list_instruments(self):
        return [{"next_re_verification_due": date.today().isoformat()}]


class P6MountedApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_router_service = reports_router.REPORT_SERVICE
        self.original_jobs = reports_service.TEST_JOB_SERVICE
        self.original_instruments = reports_service.INSTRUMENT_SERVICE

        reports_service.TEST_JOB_SERVICE = _Jobs()
        reports_service.INSTRUMENT_SERVICE = _Instruments()
        reports_router.REPORT_SERVICE = ReportService(repository=ReportRepository())
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reports_router.REPORT_SERVICE = self.original_router_service
        reports_service.TEST_JOB_SERVICE = self.original_jobs
        reports_service.INSTRUMENT_SERVICE = self.original_instruments

    def test_application_and_required_routes_are_mounted(self) -> None:
        route_methods = {
            (route.path, method)
            for route in app.routes
            for method in getattr(route, "methods", set())
        }
        expected = {
            ("/reports", "GET"),
            ("/reports", "POST"),
            ("/reports/generate", "POST"),
            ("/reports/{report_id}", "GET"),
            ("/reports/{report_id}/html", "GET"),
            ("/reports/{report_id}/pdf", "GET"),
            ("/reports/{report_id}/download", "GET"),
            ("/reports/{report_id}/generate", "POST"),
            ("/reports/{report_id}/preview", "GET"),
            ("/dashboard/metrics", "GET"),
            ("/archive/search", "GET"),
            ("/jobs", "GET"),
            ("/instruments", "GET"),
        }
        self.assertTrue(expected.issubset(route_methods))
        self.assertEqual({"status": "ok"}, self.client.get("/health").json())

    def test_reports_dashboard_and_archive_are_reachable(self) -> None:
        self.assertEqual(200, self.client.get("/reports").status_code)
        self.assertEqual(200, self.client.get("/dashboard/metrics").status_code)
        self.assertEqual(200, self.client.get("/archive/search").status_code)

    def test_create_generate_retrieve_preview_and_printable_report(self) -> None:
        created = self.client.post(
            "/reports",
            json={"job_id": "JOB-API-1", "report_type": "GENERIC_VERIFICATION"},
        )
        self.assertEqual(200, created.status_code)
        self.assertEqual(201, created.json()["status_code"])
        report_id = created.json()["data"]["report_id"]

        retrieved = self.client.get(f"/reports/{report_id}")
        self.assertEqual(200, retrieved.status_code)
        self.assertEqual("DRAFT", retrieved.json()["data"]["report_status"])
        self.assertEqual(409, self.client.get(f"/reports/{report_id}/pdf").status_code)

        generated = self.client.post(f"/reports/{report_id}/generate")
        self.assertEqual(200, generated.status_code)
        self.assertEqual("GENERATED", generated.json()["data"]["generation_status"])
        self.assertTrue(generated.json()["data"]["has_pdf"])

        preview = self.client.get(f"/reports/{report_id}/preview")
        self.assertEqual(200, preview.status_code)
        self.assertEqual(report_id, preview.json()["data"]["report_id"])

        html = self.client.get(f"/reports/{report_id}/html")
        self.assertEqual(200, html.status_code)
        self.assertIn("text/html", html.headers["content-type"])
        self.assertIn("METRIQ", html.text)

        pdf_resp = self.client.get(f"/reports/{report_id}/pdf")
        self.assertEqual(200, pdf_resp.status_code)
        self.assertIn("application/pdf", pdf_resp.headers["content-type"])
        self.assertTrue(pdf_resp.content.startswith(b"%PDF-"))

        download_resp = self.client.get(f"/reports/{report_id}/download")
        self.assertEqual(200, download_resp.status_code)
        self.assertIn("application/pdf", download_resp.headers["content-type"])
        self.assertIn("attachment;", download_resp.headers.get("content-disposition", ""))
        self.assertTrue(download_resp.content.startswith(b"%PDF-"))

        archive = self.client.get("/archive/search", params={"job_id": "JOB-API-1", "report_type": "GENERIC_VERIFICATION", "report_status": "ISSUED"})
        self.assertEqual(200, archive.status_code)
        self.assertEqual(1, archive.json()["meta"]["count"])

    def test_create_and_generate_endpoint(self) -> None:
        response = self.client.post("/reports/generate", json={"job_id": "JOB-API-1", "report_type": "TECHNICAL_EVIDENCE_ANNEX"})
        self.assertEqual(200, response.status_code)
        self.assertEqual("GENERATED", response.json()["data"]["generation_status"])
        self.assertTrue(response.json()["data"]["has_pdf"])

    def test_invalid_report_input_returns_4xx(self) -> None:
        response = self.client.post(
            "/reports",
            json={"job_id": "JOB-API-1", "report_type": "NOT_A_REPORT_TYPE"},
        )
        self.assertEqual(422, response.status_code)

        self.assertEqual(404, self.client.post("/reports", json={"job_id": "MISSING", "report_type": "GENERIC_VERIFICATION"}).status_code)
        self.assertEqual(422, self.client.post("/reports", json={"job_id": "JOB-API-1"}).status_code)
        self.assertEqual(404, self.client.get("/reports/MISSING").status_code)
        self.assertEqual(404, self.client.get("/reports/MISSING/html").status_code)
        self.assertEqual(404, self.client.get("/reports/MISSING/pdf").status_code)
        self.assertEqual(404, self.client.get("/reports/MISSING/download").status_code)
        self.assertEqual(404, self.client.post("/reports/MISSING/generate").status_code)

    def test_rejection_document_requires_a_rejected_p3_job_outcome(self) -> None:
        response = self.client.post(
            "/reports",
            json={"job_id": "JOB-API-1", "report_type": "REJECTION_DOCUMENT"},
        )
        self.assertEqual(409, response.status_code)
        self.assertIn("requires a rejected P3 job outcome", response.json()["detail"]["message"])

        reports_service.TEST_JOB_SERVICE.get_job = lambda job_id: {
            **_Jobs().get_job(job_id), "status": "REJECTED",
        } if job_id == "JOB-API-1" else None
        created = self.client.post(
            "/reports",
            json={"job_id": "JOB-API-1", "report_type": "REJECTION_DOCUMENT"},
        )
        self.assertEqual(200, created.status_code)
        report_id = created.json()["data"]["report_id"]

        reports_service.TEST_JOB_SERVICE.get_job = lambda job_id: {
            **_Jobs().get_job(job_id), "status": "CLOSED",
        } if job_id == "JOB-API-1" else None
        blocked = self.client.post(f"/reports/{report_id}/generate")
        self.assertEqual(409, blocked.status_code)
        self.assertIn("requires a rejected P3 job outcome", blocked.json()["detail"]["message"])

        reports_service.TEST_JOB_SERVICE.get_job = lambda job_id: {
            **_Jobs().get_job(job_id), "status": "REJECTED",
        } if job_id == "JOB-API-1" else None
        generated = self.client.post(f"/reports/{report_id}/generate")
        self.assertEqual(200, generated.status_code)
        self.assertEqual("REJECTED", generated.json()["data"]["report_status"])


if __name__ == "__main__":
    unittest.main()
