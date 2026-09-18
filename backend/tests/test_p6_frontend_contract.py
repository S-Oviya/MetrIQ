"""Static P6 frontend/backend contract checks without a browser test framework."""

from pathlib import Path
import re
import unittest

from app.reports.models import ReportType


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "src"


class P6FrontendContractTests(unittest.TestCase):
    def test_report_types_are_exactly_the_backend_canonical_values(self) -> None:
        client = (FRONTEND / "services" / "api" / "client.ts").read_text(encoding="utf-8")
        declared = set(re.findall(r"'([A-Z0-9_]+)'", re.search(r"export type ReportType = (.*?);", client).group(1)))
        self.assertEqual({item.value for item in ReportType}, declared)

    def test_p6_routes_and_archive_filter_names_match_the_api(self) -> None:
        client = (FRONTEND / "services" / "api" / "client.ts").read_text(encoding="utf-8")
        dashboard = (FRONTEND / "modules" / "dashboard" / "DashboardPage.tsx").read_text(encoding="utf-8")
        preview = (FRONTEND / "modules" / "reports" / "ReportPreviewPage.tsx").read_text(encoding="utf-8")
        archive = (FRONTEND / "modules" / "archive" / "ArchivePage.tsx").read_text(encoding="utf-8")
        self.assertIn("'/dashboard/metrics'", client)
        self.assertIn("dashboardApi.metrics()", dashboard)
        self.assertIn("/reports/${encodeURIComponent(id)}/html", client)
        self.assertIn("reportsApi.html(reportId)", preview)
        for name in ("search", "serial_number", "instrument_id", "job_id", "report_number", "approval_number", "report_type", "report_status", "date_from", "date_to"):
            self.assertRegex(client, rf"{name}\??:")
            self.assertIn(name, archive)
        self.assertNotIn("page?: number", client)
        self.assertNotIn("page_size?: number", client)

    def test_no_legacy_report_types_or_live_dashboard_metric_literals_remain(self) -> None:
        active = "\n".join(path.read_text(encoding="utf-8") for path in FRONTEND.rglob("*.ts*"))
        self.assertNotIn("GATC_VERIFICATION_CERTIFICATE", active)
        self.assertNotIn("STATE_VERIFICATION_CERTIFICATE", active)
        dashboard = (FRONTEND / "modules" / "dashboard" / "DashboardPage.tsx").read_text(encoding="utf-8")
        self.assertNotRegex(dashboard, r"(?:active_jobs|pending_reviews|failed_tests|completed_jobs)\s*:\s*\d")


if __name__ == "__main__":
    unittest.main()
