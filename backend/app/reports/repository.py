"""Thread-safe in-memory persistence for P6 report records."""

from __future__ import annotations

from datetime import date, datetime, timezone
from threading import RLock
from typing import Any, Dict, List, Mapping, Optional, Union

from .models import Report, ReportStatus, ReportType


ReportRecord = Union[Report, Mapping[str, Any]]


class ReportRepository:
    """In-memory report store with traceability-oriented archive filters.

    ``save`` accepts mappings as a compatibility seam for the pre-existing P6
    service. New backend consumers should use ``create`` with a typed Report.
    """

    def __init__(self) -> None:
        self._records: Dict[str, Dict[str, Any]] = {}
        self._report_number_index: Dict[str, str] = {}
        self._lock = RLock()

    @staticmethod
    def _copy(record: Dict[str, Any]) -> Dict[str, Any]:
        return dict(record)

    @staticmethod
    def _normalise(record: ReportRecord) -> Dict[str, Any]:
        data = record.to_dict() if isinstance(record, Report) else dict(record)
        if not data.get("report_id"):
            raise ValueError("report_id is required")
        if not data.get("report_number"):
            raise ValueError("report_number is required")
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        return data

    def create(self, report: Report) -> Report:
        """Create a typed report and reject duplicate identifiers/numbers."""
        with self._lock:
            if report.report_id in self._records:
                raise ValueError(f"Report '{report.report_id}' already exists.")
            number = report.metadata.report_number.strip().upper()
            if number in self._report_number_index:
                raise ValueError(f"Report number '{report.metadata.report_number}' already exists.")
            self._store(self._normalise(report))
            return report

    def _store(self, data: Dict[str, Any]) -> Dict[str, Any]:
        report_id = str(data["report_id"]).strip()
        existing = self._records.get(report_id)
        if existing and existing.get("report_number") != data.get("report_number"):
            self._report_number_index.pop(str(existing["report_number"]).strip().upper(), None)
        self._records[report_id] = data
        self._report_number_index[str(data["report_number"]).strip().upper()] = report_id
        return self._copy(data)

    def save(self, report: ReportRecord) -> Dict[str, Any]:
        """Create or update a record; retained for existing P6 service use."""
        with self._lock:
            return self._store(self._normalise(report))

    def get(self, report_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            record = self._records.get(report_id.strip())
            return self._copy(record) if record else None

    def get_by_report_number(self, report_number: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            report_id = self._report_number_index.get(report_number.strip().upper())
            return self.get(report_id) if report_id else None

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self._copy(record) for record in self._records.values()]

    def search(
        self, *, serial_number: Optional[str] = None, instrument_id: Optional[str] = None,
        job_id: Optional[str] = None, report_number: Optional[str] = None,
        approval_number: Optional[str] = None, report_type: Optional[Union[ReportType, str]] = None,
        status: Optional[Union[ReportStatus, str]] = None, date_from: Optional[Union[date, str]] = None,
        date_to: Optional[Union[date, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Return reports matching all supplied archive criteria."""
        def contains(value: Any, expected: Optional[str]) -> bool:
            return not expected or expected.strip().lower() in str(value or "").lower()
        def day(value: Any) -> str:
            return str(value or "")[:10]
        wanted_type = report_type.value if isinstance(report_type, ReportType) else report_type
        wanted_status = status.value if isinstance(status, ReportStatus) else status
        from_day, to_day = str(date_from or "")[:10], str(date_to or "")[:10]
        with self._lock:
            results = []
            for record in self._records.values():
                record_day = day(record.get("created_at"))
                if not all((contains(record.get("serial_number"), serial_number), contains(record.get("instrument_id"), instrument_id), contains(record.get("job_id"), job_id), contains(record.get("report_number"), report_number), contains(record.get("approval_number"), approval_number), not wanted_type or record.get("report_type") == wanted_type, not wanted_status or record.get("status", record.get("report_status")) == wanted_status, not from_day or record_day >= from_day, not to_day or record_day <= to_day)):
                    continue
                results.append(self._copy(record))
            return sorted(results, key=lambda item: str(item.get("created_at") or ""), reverse=True)

    def update_status(self, report_id: str, status: Union[ReportStatus, str]) -> Optional[Dict[str, Any]]:
        """Update only report status and the timestamp; return None if absent."""
        value = status.value if isinstance(status, ReportStatus) else str(status).strip().upper()
        with self._lock:
            record = self._records.get(report_id.strip())
            if not record:
                return None
            record["status"] = value
            # Existing service exposes report_status, so maintain both fields.
            if "report_status" in record:
                record["report_status"] = value
            record["updated_at"] = datetime.now(timezone.utc).isoformat()
            return self._copy(record)


REPORT_REPOSITORY = ReportRepository()
