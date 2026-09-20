"""Thread-safe persistence for P6 report records backed by SQLite."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from threading import RLock
from typing import Any, Dict, List, Mapping, Optional, Union

from app.database.connection import db_session, init_db
from .models import Report, ReportStatus, ReportType


ReportRecord = Union[Report, Mapping[str, Any]]


class ReportRepository:
    """Report store with traceability-oriented archive filters and SQLite persistence.

    ``save`` accepts mappings as a compatibility seam for the pre-existing P6
    service. New backend consumers should use ``create`` with a typed Report.
    """

    def __init__(self, persistent: bool = False) -> None:
        self._records: Dict[str, Dict[str, Any]] = {}
        self._report_number_index: Dict[str, str] = {}
        self._lock = RLock()
        self._persistent = persistent
        if self._persistent:
            init_db()
            self._load_from_db()

    def _load_from_db(self) -> None:
        try:
            with db_session() as conn:
                rows = conn.execute("SELECT data_json FROM reports ORDER BY created_at ASC").fetchall()
                for r in rows:
                    try:
                        data = json.loads(r["data_json"])
                        report_id = str(data["report_id"]).strip()
                        self._records[report_id] = data
                        if "report_number" in data:
                            self._report_number_index[str(data["report_number"]).strip().upper()] = report_id
                    except Exception:
                        pass
        except Exception:
            pass

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
            report_id = str(report.report_id).strip()
            number = report.metadata.report_number.strip().upper()
            if report_id in self._records:
                raise ValueError(f"Report '{report.report_id}' already exists.")
            if number in self._report_number_index:
                raise ValueError(f"Report number '{report.metadata.report_number}' already exists.")

            if self._persistent:
                with db_session() as conn:
                    r1 = conn.execute("SELECT 1 FROM reports WHERE report_id = ?", (report_id,)).fetchone()
                    if r1:
                        raise ValueError(f"Report '{report.report_id}' already exists.")
                    r2 = conn.execute("SELECT 1 FROM reports WHERE UPPER(report_number) = ?", (number,)).fetchone()
                    if r2:
                        raise ValueError(f"Report number '{report.metadata.report_number}' already exists.")

            self._store(self._normalise(report))
            return report

    def _store(self, data: Dict[str, Any]) -> Dict[str, Any]:
        report_id = str(data["report_id"]).strip()
        report_number = str(data["report_number"]).strip()
        job_id = str(data.get("job_id") or "")
        instrument_id = str(data.get("instrument_id") or "")
        report_type = str(data.get("report_type") or data.get("template_report_type") or "")
        status = str(data.get("status") or data.get("report_status") or "")
        pdf_path = str(data.get("pdf_path") or "")
        created_at = str(data.get("created_at") or datetime.now(timezone.utc).isoformat())
        updated_at = str(data.get("updated_at") or datetime.now(timezone.utc).isoformat())
        data_json = json.dumps(data)

        if self._persistent:
            with db_session() as conn:
                conn.execute(
                    """
                    INSERT INTO reports (
                        report_id, report_number, job_id, instrument_id, report_type,
                        status, pdf_path, data_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(report_id) DO UPDATE SET
                        report_number=excluded.report_number,
                        job_id=excluded.job_id,
                        instrument_id=excluded.instrument_id,
                        report_type=excluded.report_type,
                        status=excluded.status,
                        pdf_path=excluded.pdf_path,
                        data_json=excluded.data_json,
                        updated_at=excluded.updated_at
                    """,
                    (report_id, report_number, job_id, instrument_id, report_type, status, pdf_path, data_json, created_at, updated_at),
                )

        existing = self._records.get(report_id)
        if existing and existing.get("report_number") != data.get("report_number"):
            self._report_number_index.pop(str(existing["report_number"]).strip().upper(), None)
        self._records[report_id] = data
        self._report_number_index[report_number.upper()] = report_id
        return self._copy(data)

    def save(self, report: ReportRecord) -> Dict[str, Any]:
        """Create or update a record; retained for existing P6 service use."""
        with self._lock:
            return self._store(self._normalise(report))

    def get(self, report_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            clean_id = report_id.strip()
            if clean_id in self._records:
                return self._copy(self._records[clean_id])
            if self._persistent:
                with db_session() as conn:
                    row = conn.execute("SELECT data_json FROM reports WHERE report_id = ?", (clean_id,)).fetchone()
                    if row:
                        data = json.loads(row["data_json"])
                        self._records[clean_id] = data
                        if "report_number" in data:
                            self._report_number_index[str(data["report_number"]).strip().upper()] = clean_id
                        return self._copy(data)
            return None

    def get_by_report_number(self, report_number: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            clean_num = report_number.strip().upper()
            report_id = self._report_number_index.get(clean_num)
            if report_id:
                return self.get(report_id)
            if self._persistent:
                with db_session() as conn:
                    row = conn.execute("SELECT data_json FROM reports WHERE UPPER(report_number) = ?", (clean_num,)).fetchone()
                    if row:
                        data = json.loads(row["data_json"])
                        rid = str(data["report_id"]).strip()
                        self._records[rid] = data
                        self._report_number_index[clean_num] = rid
                        return self._copy(data)
            return None

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            if self._persistent:
                with db_session() as conn:
                    rows = conn.execute("SELECT data_json FROM reports").fetchall()
                    for r in rows:
                        try:
                            data = json.loads(r["data_json"])
                            rid = str(data["report_id"]).strip()
                            if rid not in self._records:
                                self._records[rid] = data
                                if "report_number" in data:
                                    self._report_number_index[str(data["report_number"]).strip().upper()] = rid
                        except Exception:
                            pass
            return [self._copy(record) for record in self._records.values()]

    def search(
        self,
        *,
        serial_number: Optional[str] = None,
        instrument_id: Optional[str] = None,
        job_id: Optional[str] = None,
        report_number: Optional[str] = None,
        approval_number: Optional[str] = None,
        report_type: Optional[Union[ReportType, str]] = None,
        status: Optional[Union[ReportStatus, str]] = None,
        date_from: Optional[Union[date, str]] = None,
        date_to: Optional[Union[date, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Return reports matching all supplied archive criteria."""
        def contains(value: Any, expected: Optional[str]) -> bool:
            return not expected or expected.strip().lower() in str(value or "").lower()

        def matches_day(val: Any) -> bool:
            if not from_day and not to_day:
                return True
            if not val:
                return False
            raw = str(val)[:10]
            local = raw
            try:
                dt = datetime.fromisoformat(str(val))
                local = dt.astimezone().date().isoformat()
            except Exception:
                pass
            utc_ok = (not from_day or raw >= from_day) and (not to_day or raw <= to_day)
            loc_ok = (not from_day or local >= from_day) and (not to_day or local <= to_day)
            return utc_ok or loc_ok

        wanted_type = report_type.value if isinstance(report_type, ReportType) else report_type
        wanted_status = status.value if isinstance(status, ReportStatus) else status
        from_day, to_day = str(date_from or "")[:10], str(date_to or "")[:10]

        with self._lock:
            # Sync from DB if persistent
            self.list()
            results = []
            for record in self._records.values():
                if not all((
                    contains(record.get("serial_number"), serial_number),
                    contains(record.get("instrument_id"), instrument_id),
                    contains(record.get("job_id"), job_id),
                    contains(record.get("report_number"), report_number),
                    contains(record.get("approval_number"), approval_number),
                    not wanted_type or record.get("report_type") == wanted_type,
                    not wanted_status or record.get("status", record.get("report_status")) == wanted_status,
                    matches_day(record.get("created_at")),
                )):
                    continue
                results.append(self._copy(record))
            return sorted(results, key=lambda item: str(item.get("created_at") or ""), reverse=True)

    def update_status(self, report_id: str, status: Union[ReportStatus, str]) -> Optional[Dict[str, Any]]:
        """Update only report status and the timestamp; return None if absent."""
        value = status.value if isinstance(status, ReportStatus) else str(status).strip().upper()
        with self._lock:
            clean_id = report_id.strip()
            record = self.get(clean_id)
            if not record:
                return None
            record["status"] = value
            if "report_status" in record:
                record["report_status"] = value
            record["updated_at"] = datetime.now(timezone.utc).isoformat()
            return self._store(record)

    def clear(self) -> None:
        """Clears all report records (used for test isolation)."""
        with self._lock:
            self._records.clear()
            self._report_number_index.clear()
            if self._persistent:
                with db_session() as conn:
                    conn.execute("DELETE FROM reports")


REPORT_REPOSITORY = ReportRepository(persistent=True)
