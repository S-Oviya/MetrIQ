"""
MetrIQ P5 Environment Condition Repository
==========================================
Person 5: Workflow + Evidence Engineer

Thread-safe in-memory repository for storing, retrieving, and indexing
environment condition records associated with Test Jobs.
"""

from datetime import datetime
import threading
from typing import Any, Dict, List, Optional
from .models import EnvironmentCondition


class EnvironmentRepository:
    """Thread-safe storage and chronological indexing for EnvironmentCondition entities."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: Dict[str, EnvironmentCondition] = {}
        self._job_index: Dict[str, List[str]] = {}

    def save(self, record: EnvironmentCondition) -> EnvironmentCondition:
        """Stores or updates an environment condition record, updating job index."""
        with self._lock:
            self._records[record.id] = record
            if record.job_id:
                if record.job_id not in self._job_index:
                    self._job_index[record.job_id] = []
                if record.id not in self._job_index[record.job_id]:
                    self._job_index[record.job_id].append(record.id)
            return record

    def get(self, record_id: str) -> Optional[EnvironmentCondition]:
        """Retrieves an environment record by its unique identifier."""
        with self._lock:
            return self._records.get(record_id)

    def get_by_job(self, job_id: str) -> List[EnvironmentCondition]:
        """
        Retrieves all environment records for a job, sorted chronologically
        by recorded_at (and created_at as fallback).
        """
        with self._lock:
            record_ids = self._job_index.get(job_id, [])
            records = [self._records[rid] for rid in record_ids if rid in self._records]
            return sorted(records, key=lambda r: (r.recorded_at or "", r.created_at or ""))

    def get_latest_by_job(self, job_id: str) -> Optional[EnvironmentCondition]:
        """Retrieves the most recently recorded environment condition for a job."""
        records = self.get_by_job(job_id)
        if records:
            return records[-1]
        return None

    def delete(self, record_id: str) -> bool:
        """Deletes an environment record by ID."""
        with self._lock:
            record = self._records.pop(record_id, None)
            if record and record.job_id in self._job_index:
                try:
                    self._job_index[record.job_id].remove(record_id)
                except ValueError:
                    pass
                return True
            return False

    def list_all(self) -> List[EnvironmentCondition]:
        """Returns all stored environment records."""
        with self._lock:
            return list(self._records.values())

    def clear(self) -> None:
        """Clears all records and indices (used for testing isolation)."""
        with self._lock:
            self._records.clear()
            self._job_index.clear()


# Global singleton instance
ENVIRONMENT_REPOSITORY = EnvironmentRepository()
