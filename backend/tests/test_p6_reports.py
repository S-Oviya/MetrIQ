"""P6 report service coverage without mutating P2/P3 source implementations."""
from datetime import date
import unittest
from app.reports.mock_data_adapter import MockReportDataAdapter
from app.reports.repository import ReportRepository
from app.reports.models import ReportStatus, ReportType
from app.reports.service import ReportService
from app.reports.templates import TITLES

REPORT_SECTION_MARKERS = {
    "OIML_R76_2_TYPE_EVALUATION": ("Type Evaluation Identification", "Test-Point / Evaluation Matrix", "Practice/demo type-evaluation template only"),
    "GATC_THIRD_SCHEDULE_VERIFICATION": ("GATC / Statutory Routing Reference", "Inspector / Testing-Centre Information", "not an official issued statutory certificate"),
    "GENERIC_VERIFICATION": ("Applicable State / Regulatory Profile", "Results and Tolerance Comparison", "Configurable record"),
    "REJECTION_DOCUMENT": ("REJECTION / NON-COMPLIANCE NOTICE", "Failed / Non-Compliant Criteria", "Required Corrective / Retest Action"),
    "TECHNICAL_EVIDENCE_ANNEX": ("Evidence Index", "Environmental Records", "Test-Weight / Calibration Certificate References"),
}

class _Jobs:
    def __init__(self): self.status = "CLOSED"
    def get_job(self, job_id):
        if job_id != "JOB-1": return None
        return {"job_id":job_id,"job_number":"JOB/2026/1","instrument_id":"INST-1","status":self.status,"job_type":"RE_VERIFICATION","model_approval_id":"APR-1","applicable_tests":["Upstream test"],"test_plan":{"mpe_reference":"Upstream MPE reference"},"state_history":[]}
    def list_jobs(self): return [self.get_job("JOB-1")]
class _Instruments:
    def get_instrument(self, instrument_id): return {"instrument_id":instrument_id,"serial_number":"SER-1","model_approval_number":"APR-1","model_name":"Demo Scale","manufacturer":"Demo Manufacturer","accuracy_class":"CLASS_III","max_capacity":15,"min_capacity":0.1,"e":0.005,"d":0.005}
    def list_instruments(self): return [{"next_re_verification_due":date.today().isoformat()}]

class ReportServiceTests(unittest.TestCase):
    def setUp(self):
        import app.reports.service as module
        self.module, self.old_jobs, self.old_instruments = module, module.TEST_JOB_SERVICE, module.INSTRUMENT_SERVICE
        module.TEST_JOB_SERVICE, module.INSTRUMENT_SERVICE = _Jobs(), _Instruments()
        self.service = ReportService(repository=ReportRepository())
    def tearDown(self): self.module.TEST_JOB_SERVICE, self.module.INSTRUMENT_SERVICE = self.old_jobs, self.old_instruments
    def test_all_canonical_report_types_create_generate_retrieve_and_render_metadata(self):
        for report_type in ReportType:
            created=self.service.create("JOB-1",report_type.value); self.assertTrue(created["success"]); self.assertTrue(created["data"]["report_id"]); self.assertTrue(created["data"]["report_number"])
            self.assertEqual(report_type.value, created["data"]["report_type"])
            generated=self.service.generate(created["data"]["report_id"]); self.assertTrue(generated["success"]); self.assertIn("METRIQ",generated["data"]["html"])
            self.assertIsNotNone(self.service.get(created["data"]["report_id"]))
            self.assertIn(created["data"]["report_number"], generated["data"]["html"])
            self.assertIn(TITLES[report_type.value], generated["data"]["html"])
            self.assertIn("JOB-1", generated["data"]["html"])
            self.assertIn("INST-1", generated["data"]["html"])
            self.assertIn("SER-1", generated["data"]["html"])
            self.assertIn("DEMO/MOCK", generated["data"]["html"])
            for marker in REPORT_SECTION_MARKERS[report_type.value]:
                self.assertIn(marker, generated["data"]["html"])
            self.assertNotIn("undefined", generated["data"]["html"].lower())
            self.assertNotIn(">null<", generated["data"]["html"].lower())
            self.assertNotIn("[object object]", generated["data"]["html"].lower())
            self.assertTrue(generated["data"]["contains_demo_data"])
            self.assertEqual("ISSUED" if report_type != ReportType.REJECTION_DOCUMENT else "REJECTED", generated["data"]["report_status"])

    def test_report_templates_keep_upstream_snapshot_and_demo_safety_boundaries(self):
        for report_type in ReportType:
            report = self.service.create("JOB-1", report_type.value)["data"]
            generated = self.service.generate(report["report_id"])["data"]
            html = generated["html"]
            self.assertIn("Upstream test", html)
            self.assertIn("Upstream MPE reference", html)
            self.assertIn("DEMO/MOCK — not a measured, reviewed, or issued record", html)

        oiml = self.service.generate(self.service.create("JOB-1", "OIML_R76_2_TYPE_EVALUATION")["data"]["report_id"])["data"]["html"]
        self.assertIn("not an official issued OIML certificate", oiml)
    def test_archive_filters(self):
        report=self.service.create("JOB-1","GENERIC_VERIFICATION")["data"]; self.service.generate(report["report_id"])
        self.assertEqual(1,len(self.service.archive_search(report_number=report["report_number"])))
        self.assertEqual(1,len(self.service.archive_search(job_id="JOB-1")))
        self.assertEqual(1,len(self.service.archive_search(instrument_id="INST-1")))
        self.assertEqual(1,len(self.service.archive_search(approval_number="APR-1")))
        self.assertEqual(1,len(self.service.archive_search(date_from=date.today().isoformat(),date_to=date.today().isoformat())))
    def test_dashboard_and_mock_markers(self):
        report=self.service.create("JOB-1","GENERIC_VERIFICATION")["data"]; self.service.generate(report["report_id"])
        metrics=self.service.dashboard_metrics(); self.assertTrue({"active_jobs","pending_reviews","failed_tests","retests","completed_jobs","verification_due","reports_generated","reports_pending_generation"}.issubset(metrics))
        self.assertEqual(metrics["reports_generated"], 1)
        self.assertTrue(MockReportDataAdapter().test_observations("JOB-1")[0]["is_demo"])
    def test_status_handling_and_invalid_requests_preserve_lifecycle_validation(self):
        report=self.service.create("JOB-1","GENERIC_VERIFICATION")["data"]
        self.assertEqual(ReportStatus.DRAFT.value, report["report_status"])
        self.module.TEST_JOB_SERVICE.status="UNDER_REVIEW"
        blocked=self.service.generate(report["report_id"])
        self.assertFalse(blocked["success"]); self.assertEqual(409, blocked["status_code"])
        self.module.TEST_JOB_SERVICE.status="REJECTED"
        generated=self.service.generate(report["report_id"])
        self.assertTrue(generated["success"]); self.assertEqual(ReportStatus.REJECTED.value, generated["data"]["report_status"])
        self.assertFalse(self.service.create("MISSING","GENERIC_VERIFICATION")["success"])
        self.assertEqual(404, self.service.create("MISSING","GENERIC_VERIFICATION")["status_code"])
        self.assertFalse(self.service.create("JOB-1","GATC_VERIFICATION_CERTIFICATE")["success"])
        self.assertEqual(422, self.service.create("JOB-1","GATC_VERIFICATION_CERTIFICATE")["status_code"])
        self.assertFalse(self.service.generate("MISSING")["success"])

    def test_rejection_document_requires_a_rejected_p3_job_outcome(self):
        self.module.TEST_JOB_SERVICE.status = "APPROVED"
        blocked_create = self.service.create("JOB-1", "REJECTION_DOCUMENT")
        self.assertFalse(blocked_create["success"])
        self.assertEqual(409, blocked_create["status_code"])
        self.assertIn("requires a rejected P3 job outcome", blocked_create["message"])

        self.module.TEST_JOB_SERVICE.status = "REJECTED"
        report = self.service.create("JOB-1", "REJECTION_DOCUMENT")["data"]
        self.module.TEST_JOB_SERVICE.status = "CLOSED"
        blocked_generation = self.service.generate(report["report_id"])
        self.assertFalse(blocked_generation["success"])
        self.assertEqual(409, blocked_generation["status_code"])
        self.assertIn("requires a rejected P3 job outcome", blocked_generation["message"])

        self.module.TEST_JOB_SERVICE.status = "REJECTED"
        generated = self.service.generate(report["report_id"])
        self.assertTrue(generated["success"])
        self.assertEqual(ReportStatus.REJECTED.value, generated["data"]["report_status"])

if __name__ == "__main__": unittest.main()
