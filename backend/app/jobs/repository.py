"""
MetrIQ Test Job Repository — Person 3 (Job / Instrument Engineer)
================================================================
Thread-safe persistence repository for Test Jobs with multi-index lookups
by instrument, assigned inspector, status, and job type.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional, Union

from app.regulatory.models import JobType
from .models import JobPriority, JobStatus, TestJob


class TestJobRepository:
    """
    Thread-safe in-memory repository for test jobs with instrument history indexing.
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, TestJob] = {}
        self._instrument_index: Dict[str, List[str]] = {} # instrument_id -> [job_ids]
        self._lock = threading.RLock()

    def save(self, job: TestJob) -> TestJob:
        """Saves or updates a TestJob in the repository."""
        with self._lock:
            job.updated_at = datetime.now(timezone.utc).isoformat()
            self._jobs[job.job_id] = job

            # Maintain instrument index
            inst_id = job.instrument_id
            if inst_id:
                if inst_id not in self._instrument_index:
                    self._instrument_index[inst_id] = []
                if job.job_id not in self._instrument_index[inst_id]:
                    self._instrument_index[inst_id].append(job.job_id)

            return job

    def get(self, job_id: str) -> Optional[TestJob]:
        """Retrieves a job by its unique ID."""
        with self._lock:
            return self._jobs.get(job_id.strip())

    def get_by_instrument(self, instrument_id: str) -> List[TestJob]:
        """Retrieves all jobs created for a given instrument."""
        with self._lock:
            job_ids = self._instrument_index.get(instrument_id.strip(), [])
            return [self._jobs[jid] for jid in job_ids if jid in self._jobs]

    def exists(self, job_id: str) -> bool:
        """Checks if a job exists."""
        with self._lock:
            return job_id.strip() in self._jobs

    def delete(self, job_id: str) -> bool:
        """Deletes a job from repository."""
        with self._lock:
            job = self._jobs.pop(job_id.strip(), None)
            if job:
                inst_id = job.instrument_id
                if inst_id in self._instrument_index:
                    self._instrument_index[inst_id] = [
                        jid for jid in self._instrument_index[inst_id] if jid != job.job_id
                    ]
                return True
            return False

    def list_all(
        self,
        status: Optional[Union[str, JobStatus]] = None,
        job_type: Optional[Union[str, JobType]] = None,
        instrument_id: Optional[str] = None,
        inspector_id: Optional[str] = None,
        testing_centre_id: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[TestJob]:
        """Queries and filters jobs with multiple criteria."""
        with self._lock:
            results: List[TestJob] = []
            target_status = JobStatus.from_value(status) if status is not None else None
            target_type = JobType(job_type) if isinstance(job_type, str) else job_type
            search_term = search.lower().strip() if search else None

            for job in self._jobs.values():
                if target_status and job.status != target_status:
                    continue
                if target_type and job.job_type != target_type:
                    continue
                if instrument_id and job.instrument_id.strip() != instrument_id.strip():
                    continue
                if inspector_id and (not job.assigned_inspector_id or inspector_id.lower() not in job.assigned_inspector_id.lower()):
                    continue
                if testing_centre_id and (not job.testing_centre_id or testing_centre_id.lower() not in job.testing_centre_id.lower()):
                    continue
                if search_term:
                    match = (
                        search_term in job.job_id.lower()
                        or search_term in job.instrument_id.lower()
                        or (job.assigned_inspector_name and search_term in job.assigned_inspector_name.lower())
                        or (job.testing_centre_name and search_term in job.testing_centre_name.lower())
                    )
                    if not match:
                        continue

                results.append(job)

            # Sort by created_at descending (latest jobs first)
            results.sort(key=lambda j: j.created_at, reverse=True)
            return results

    def count(self) -> int:
        """Returns total jobs count."""
        with self._lock:
            return len(self._jobs)

    def clear(self) -> None:
        """Clears all jobs and indices (used for testing isolation)."""
        with self._lock:
            self._jobs.clear()
            self._instrument_index.clear()


# Global singleton instance for application runtime
TEST_JOB_REPOSITORY = TestJobRepository()
