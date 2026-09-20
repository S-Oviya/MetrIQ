"""
MetrIQ P5 Evidence Repository
=============================
Person 5: Workflow + Evidence Engineer

Thread-safe in-memory repository for storing, querying, and indexing Evidence entities.
Supports indexing by Job, Test, and Attempt.
"""

from datetime import datetime
import threading
from typing import Any, Dict, List, Optional, Tuple
from .models import Evidence, EvidenceStatus


class EvidenceRepository:
    """
    Thread-safe storage and multi-level index for Evidence records.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: Dict[str, Evidence] = {}
        # job_id -> list of evidence_ids
        self._job_index: Dict[str, List[str]] = {}
        # (job_id, test_id.upper()) -> list of evidence_ids
        self._test_index: Dict[Tuple[str, str], List[str]] = {}
        # attempt_id -> list of evidence_ids
        self._attempt_index: Dict[str, List[str]] = {}

    def save(self, evidence: Evidence) -> Evidence:
        """Stores or updates an Evidence record, maintaining all indexes."""
        with self._lock:
            self._records[evidence.id] = evidence
            job_key = str(evidence.job_id).strip()

            # 1. Job Index
            if job_key not in self._job_index:
                self._job_index[job_key] = []
            if evidence.id not in self._job_index[job_key]:
                self._job_index[job_key].append(evidence.id)

            # 2. Test Index
            if evidence.test_id:
                test_key = (job_key, str(evidence.test_id).strip().upper())
                if test_key not in self._test_index:
                    self._test_index[test_key] = []
                if evidence.id not in self._test_index[test_key]:
                    self._test_index[test_key].append(evidence.id)

            # 3. Attempt Index
            if evidence.attempt_id:
                att_key = str(evidence.attempt_id).strip()
                if att_key not in self._attempt_index:
                    self._attempt_index[att_key] = []
                if evidence.id not in self._attempt_index[att_key]:
                    self._attempt_index[att_key].append(evidence.id)

            return evidence

    def get(self, evidence_id: str) -> Optional[Evidence]:
        """Retrieves single evidence record by ID."""
        with self._lock:
            return self._records.get(evidence_id)

    def get_by_job(self, job_id: str, include_archived: bool = False) -> List[Evidence]:
        """Retrieves all evidence associated with a Job."""
        with self._lock:
            job_key = str(job_id).strip()
            ev_ids = self._job_index.get(job_key, [])
            results = []
            for eid in ev_ids:
                e = self._records.get(eid)
                if e:
                    if not include_archived and e.status in (EvidenceStatus.ARCHIVED, EvidenceStatus.DELETED):
                        continue
                    results.append(e)
            return sorted(results, key=lambda r: (r.uploaded_at or "", r.created_at or ""))

    def get_by_test(self, job_id: str, test_id: str, include_archived: bool = False) -> List[Evidence]:
        """Retrieves all evidence associated with a Test on a Job."""
        with self._lock:
            pair_key = (str(job_id).strip(), str(test_id).strip().upper())
            ev_ids = self._test_index.get(pair_key, [])
            results = []
            for eid in ev_ids:
                e = self._records.get(eid)
                if e:
                    if not include_archived and e.status in (EvidenceStatus.ARCHIVED, EvidenceStatus.DELETED):
                        continue
                    results.append(e)
            return sorted(results, key=lambda r: (r.uploaded_at or "", r.created_at or ""))

    def get_by_attempt(self, attempt_id: str, include_archived: bool = False) -> List[Evidence]:
        """Retrieves all evidence attached to a specific Attempt."""
        with self._lock:
            att_key = str(attempt_id).strip()
            ev_ids = self._attempt_index.get(att_key, [])
            results = []
            for eid in ev_ids:
                e = self._records.get(eid)
                if e:
                    if not include_archived and e.status in (EvidenceStatus.ARCHIVED, EvidenceStatus.DELETED):
                        continue
                    results.append(e)
            return sorted(results, key=lambda r: (r.uploaded_at or "", r.created_at or ""))

    def list_all(self, include_archived: bool = False) -> List[Evidence]:
        """Lists all evidence in the repository."""
        with self._lock:
            if include_archived:
                return list(self._records.values())
            return [
                e for e in self._records.values()
                if e.status not in (EvidenceStatus.ARCHIVED, EvidenceStatus.DELETED)
            ]

    def delete(self, evidence_id: str) -> bool:
        """Removes an evidence record completely from repository."""
        with self._lock:
            e = self._records.pop(evidence_id, None)
            if not e:
                return False
            # Clean indexes
            job_key = str(e.job_id).strip()
            if job_key in self._job_index and evidence_id in self._job_index[job_key]:
                self._job_index[job_key].remove(evidence_id)
            if e.test_id:
                test_key = (job_key, str(e.test_id).strip().upper())
                if test_key in self._test_index and evidence_id in self._test_index[test_key]:
                    self._test_index[test_key].remove(evidence_id)
            if e.attempt_id:
                att_key = str(e.attempt_id).strip()
                if att_key in self._attempt_index and evidence_id in self._attempt_index[att_key]:
                    self._attempt_index[att_key].remove(evidence_id)
            return True

    def clear(self) -> None:
        """Clears all records and indices for test isolation."""
        with self._lock:
            self._records.clear()
            self._job_index.clear()
            self._test_index.clear()
            self._attempt_index.clear()


# Global singleton repository
EVIDENCE_REPOSITORY = EvidenceRepository()
