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
    # Default status sequence for the two loop tests that iterate all ReportTypes.
    # Each iteration calls get_job twice (once in create, once in generate).
    # REJECTION_DOCUMENT is the 4th enum member (index 3); its two calls must return
    # "REJECTED" so the strict domain rule (create requires REJECTED outcome) is met.
    # All other iterations use "CLOSED" so generate() produces report_status="ISSUED".
    # Tests that need a specific status (test_rejection_document_*, test_status_handling)
    # set self.status to a non-None string, which overrides the sequence entirely.
    _DEFAULT_SEQUENCE = (
        "CLOSED",   "CLOSED",    # OIML_R76_2_TYPE_EVALUATION        calls 1-2
        "CLOSED",   "CLOSED",    # GATC_THIRD_SCHEDULE_VERIFICATION   calls 3-4
        "CLOSED",   "CLOSED",    # GENERIC_VERIFICATION               calls 5-6
        "REJECTED", "REJECTED",  # REJECTION_DOCUMENT                 calls 7-8
        "CLOSED",   "CLOSED",    # TECHNICAL_EVIDENCE_ANNEX           calls 9-10
    )

    def __init__(self):
        self.status = None   # None → use _DEFAULT_SEQUENCE; any string → hard override
        self._call = 0

    def get_job(self, job_id):
        if job_id != "JOB-1":
            return None
        if self.status is not None:
            status = self.status
        else:
            status = self._DEFAULT_SEQUENCE[self._call] if self._call < len(self._DEFAULT_SEQUENCE) else "CLOSED"
            self._call += 1
        return {"job_id": job_id, "job_number": "JOB/2026/1", "instrument_id": "INST-1",
                "status": status, "job_type": "RE_VERIFICATION", "model_approval_id": "APR-1",
                "applicable_tests": ["Upstream test"], "test_plan": {"mpe_reference": "Upstream MPE reference"},
                "state_history": []}

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
            pdf_bytes = self.service.get_pdf(created["data"]["report_id"])
            self.assertIsNotNone(pdf_bytes)
            self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
            self.assertGreater(len(pdf_bytes), 1000)
            self.assertTrue(generated["data"]["has_pdf"])
            self.assertTrue(generated["data"]["pdf_filename"].endswith(".pdf"))
            self.assertEqual("ISSUED" if report_type != ReportType.REJECTION_DOCUMENT else "REJECTED", generated["data"]["report_status"])

    def test_pdf_generation_with_real_job_data_contains_actual_values(self):
        import pypdfium2
        real_job = {
            "job_id": "JOB-REAL-100",
            "job_number": "JOB/2026/REAL-100",
            "instrument_id": "INST-REAL-100",
            "status": "APPROVED",
            "job_type": "INITIAL_VERIFICATION",
            "model_approval_id": "APR-REAL-888",
            "applicable_tests": ["WEIGHING_PERFORMANCE", "REPEATABILITY"],
            "test_plan": {"mpe_reference": "MPE R76-1 Table 6"},
            "state_history": [{"state": "APPROVED", "by": "Chief Inspector"}],
            "test_attempts": [
                {
                    "id": "ATT-REAL-001",
                    "test_id": "WEIGHING_PERFORMANCE",
                    "attempt_number": 1,
                    "result": "PASS",
                    "operator": "Jane Inspector",
                    "completed_at": "2026-09-20T10:30:00Z",
                    "result_data": {
                        "summary": "Measured error zero at max load",
                        "standard_reference": "OIML R76-1 cl 3.5.1",
                    },
                }
            ],
            "review_history": [
                {
                    "reviewer": "Dr. Metrology Reviewer",
                    "decision": "APPROVED",
                    "reviewed_at": "2026-09-20T11:00:00Z",
                    "comments": "High precision verified compliant with statutory limits.",
                }
            ],
            "environment_records": [
                {
                    "temperature_celsius": 20.8,
                    "relative_humidity": 48.5,
                    "atmospheric_pressure_hpa": 1014.2,
                    "recorded_by": "Jane Inspector",
                    "recorded_at": "2026-09-20T09:00:00Z",
                }
            ],
            "evidence_metadata": [
                {
                    "evidence_id": "EV-REAL-001",
                    "file_name": "calibration_seal.png",
                    "description": "Tamper evident seal applied to adjustment port",
                }
            ],
        }
        real_instrument = {
            "instrument_id": "INST-REAL-100",
            "serial_number": "SER-REAL-9999",
            "model_approval_number": "APR-REAL-888",
            "model_name": "Precision Benchmark Balancer",
            "manufacturer": "MetrIQ Certified Metrology",
            "accuracy_class": "CLASS_II",
            "max_capacity": 5000,
            "min_capacity": 20,
            "e": 0.01,
            "d": 0.001,
        }

        self.module.TEST_JOB_SERVICE.get_job = lambda j_id: real_job if j_id == "JOB-REAL-100" else None
        self.module.INSTRUMENT_SERVICE.get_instrument = lambda i_id: real_instrument if i_id == "INST-REAL-100" else None

        created = self.service.create("JOB-REAL-100", "GENERIC_VERIFICATION")
        self.assertTrue(created["success"])
        report_id = created["data"]["report_id"]

        generated = self.service.generate(report_id, generated_by="Auditor Smith")
        self.assertTrue(generated["success"])
        self.assertFalse(generated["data"]["contains_demo_data"])
        self.assertTrue(generated["data"]["has_pdf"])

        pdf_bytes = self.service.get_pdf(report_id)
        self.assertIsNotNone(pdf_bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))

        # Extract text from the real generated PDF
        pdf = pypdfium2.PdfDocument(pdf_bytes)
        self.assertGreaterEqual(len(pdf), 1)
        text = "".join(page.get_textpage().get_text_range() for page in pdf)

        # Assert all real data fields are embedded in the PDF
        normalized_text = " ".join(text.split())
        self.assertIn("JOB-REAL-100", normalized_text)
        self.assertIn("SER-REAL-9999", normalized_text)
        self.assertIn("Precision Benchmark Balancer", normalized_text)
        self.assertIn("MetrIQ Certified Metrology", normalized_text)
        self.assertIn("ATT-REAL-001", normalized_text)
        self.assertIn("Jane Inspector", normalized_text)
        self.assertIn("Measured error zero at max load", normalized_text)
        self.assertIn("Dr. Metrology Reviewer", normalized_text)
        self.assertIn("T=20.8", normalized_text)
        self.assertIn("RH=48.5%", normalized_text)
        self.assertIn("EV-REAL-001", normalized_text)
        self.assertIn("calibration_seal.png", normalized_text)
        self.assertIn("BACKEND-RECORDED REPORT SNAPSHOT", normalized_text)
        self.assertNotIn("DEMO/MOCK DATA PRESENT", normalized_text)

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
