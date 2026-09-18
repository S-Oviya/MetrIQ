"""Isolated, explicitly labelled fallback data for absent P4/P5 integrations."""

from __future__ import annotations

from typing import Any, Dict, List


DEMO_SOURCE = "DEMO/MOCK — not a measured, reviewed, or issued record"


class MockReportDataAdapter:
    """Temporary adapter seam for report assembly when upstream data is absent.

    Every returned payload carries ``is_demo`` and ``data_source``. A future P4
    or P5 adapter can expose the same methods without changing report consumers.
    """

    @staticmethod
    def _payload(data: Dict[str, Any]) -> Dict[str, Any]:
        return {"is_demo": True, "data_source": DEMO_SOURCE, **data}

    def test_observations(self, job_id: str) -> List[Dict[str, Any]]:
        return [self._payload({"job_id": job_id, "observation_id": "DEMO-OBS-001", "description": "Synthetic placeholder observation", "result": "DEMO_ONLY"})]

    def environmental_readings(self, job_id: str) -> Dict[str, Any]:
        return self._payload({"job_id": job_id, "temperature": None, "humidity": None, "note": "No real environmental readings supplied."})

    def reviewer_information(self, job_id: str) -> Dict[str, Any]:
        return self._payload({"job_id": job_id, "reviewer_name": "DEMO REVIEWER", "review_status": "NOT_REVIEWED"})

    def test_weight_certificate(self, job_id: str) -> Dict[str, Any]:
        return self._payload({"job_id": job_id, "certificate_number": "DEMO-WEIGHT-CERT", "note": "Placeholder only; not a certificate reference."})

    def evidence_metadata(self, job_id: str) -> List[Dict[str, Any]]:
        return [self._payload({"job_id": job_id, "evidence_id": "DEMO-EVIDENCE-001", "file_name": "demo-placeholder.txt", "description": "Synthetic evidence metadata only"})]
