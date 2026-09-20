"""
MetrIQ Test Job Repository — Person 3 (Job / Instrument Engineer)
================================================================
Thread-safe persistence repository for Test Jobs with multi-index lookups
by instrument, assigned inspector, status, and job type.
Backed by SQLite persistent storage.
"""

from datetime import datetime, timezone
import json
import threading
from typing import Any, Dict, List, Optional, Union

from app.database.connection import db_session, init_db
from app.regulatory.models import JobType
from .models import JobPriority, JobStatus, TestJob


class TestJobRepository:
    """
    Thread-safe repository for test jobs with SQLite persistence and instrument history indexing.
    """
    __test__ = False

    def __init__(self, persistent: bool = False) -> None:
        self._jobs: Dict[str, TestJob] = {}
        self._instrument_index: Dict[str, List[str]] = {}  # instrument_id -> [job_ids]
        self._lock = threading.RLock()
        self._persistent = persistent
        if self._persistent:
            init_db()
            self._load_from_db()

    def _load_from_db(self) -> None:
        try:
            with db_session() as conn:
                rows = conn.execute("SELECT data_json FROM jobs ORDER BY created_at ASC").fetchall()
                for r in rows:
                    try:
                        data = json.loads(r["data_json"])
                        job = TestJob.from_dict(data)
                        self._jobs[job.job_id] = job
                        inst_id = job.instrument_id
                        if inst_id:
                            if inst_id not in self._instrument_index:
                                self._instrument_index[inst_id] = []
                            if job.job_id not in self._instrument_index[inst_id]:
                                self._instrument_index[inst_id].append(job.job_id)
                    except Exception:
                        pass
        except Exception:
            pass

    def save(self, job: TestJob) -> TestJob:
        """Saves or updates a TestJob in the repository and persists to SQLite."""
        with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            job.updated_at = now
            if not getattr(job, "created_at", None):
                job.created_at = now

            if self._persistent:
                data_json = json.dumps(job.to_dict())
                with db_session() as conn:
                    conn.execute(
                        """
                        INSERT INTO jobs (
                            job_id, job_number, instrument_id, job_type, status,
                            assigned_inspector_id, testing_centre_id, data_json, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(job_id) DO UPDATE SET
                            job_number=excluded.job_number,
                            instrument_id=excluded.instrument_id,
                            job_type=excluded.job_type,
                            status=excluded.status,
                            assigned_inspector_id=excluded.assigned_inspector_id,
                            testing_centre_id=excluded.testing_centre_id,
                            data_json=excluded.data_json,
                            updated_at=excluded.updated_at
                        """,
                        (
                            job.job_id,
                            job.job_number,
                            job.instrument_id,
                            job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type),
                            job.status.value if hasattr(job.status, "value") else str(job.status),
                            job.assigned_inspector_id,
                            job.testing_centre_id,
                            data_json,
                            job.created_at,
                            job.updated_at,
                        ),
                    )

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
            clean_id = job_id.strip()
            if clean_id in self._jobs:
                return self._jobs[clean_id]
            if self._persistent:
                with db_session() as conn:
                    row = conn.execute(
                        "SELECT data_json FROM jobs WHERE job_id = ?",
                        (clean_id,),
                    ).fetchone()
                    if row:
                        job = TestJob.from_dict(json.loads(row["data_json"]))
                        self._jobs[job.job_id] = job
                        inst_id = job.instrument_id
                        if inst_id:
                            if inst_id not in self._instrument_index:
                                self._instrument_index[inst_id] = []
                            if job.job_id not in self._instrument_index[inst_id]:
                                self._instrument_index[inst_id].append(job.job_id)
                        return job
            return None

    def get_by_instrument(self, instrument_id: str) -> List[TestJob]:
        """Retrieves all jobs created for a given instrument."""
        with self._lock:
            clean_inst_id = instrument_id.strip()
            if self._persistent:
                with db_session() as conn:
                    rows = conn.execute(
                        "SELECT data_json FROM jobs WHERE instrument_id = ? ORDER BY created_at DESC",
                        (clean_inst_id,),
                    ).fetchall()
                    for r in rows:
                        try:
                            job = TestJob.from_dict(json.loads(r["data_json"]))
                            self._jobs[job.job_id] = job
                            if clean_inst_id not in self._instrument_index:
                                self._instrument_index[clean_inst_id] = []
                            if job.job_id not in self._instrument_index[clean_inst_id]:
                                self._instrument_index[clean_inst_id].append(job.job_id)
                        except Exception:
                            pass
            job_ids = self._instrument_index.get(clean_inst_id, [])
            return [self._jobs[jid] for jid in job_ids if jid in self._jobs]

    def exists(self, job_id: str) -> bool:
        """Checks if a job exists."""
        with self._lock:
            clean_id = job_id.strip()
            if clean_id in self._jobs:
                return True
            if self._persistent:
                with db_session() as conn:
                    row = conn.execute("SELECT 1 FROM jobs WHERE job_id = ?", (clean_id,)).fetchone()
                    return row is not None
            return False

    def delete(self, job_id: str) -> bool:
        """Deletes a job from repository."""
        with self._lock:
            clean_id = job_id.strip()
            deleted = False
            if self._persistent:
                with db_session() as conn:
                    cur = conn.execute("DELETE FROM jobs WHERE job_id = ?", (clean_id,))
                    if cur.rowcount > 0:
                        deleted = True
            job = self._jobs.pop(clean_id, None)
            if job:
                inst_id = job.instrument_id
                if inst_id in self._instrument_index:
                    self._instrument_index[inst_id] = [
                        jid for jid in self._instrument_index[inst_id] if jid != job.job_id
                    ]
                return True
            return deleted

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
            if self._persistent:
                with db_session() as conn:
                    rows = conn.execute("SELECT data_json FROM jobs").fetchall()
                    for r in rows:
                        try:
                            data = json.loads(r["data_json"])
                            jid = data.get("job_id")
                            if jid and jid not in self._jobs:
                                job = TestJob.from_dict(data)
                                self._jobs[job.job_id] = job
                                inst_id = job.instrument_id
                                if inst_id:
                                    if inst_id not in self._instrument_index:
                                        self._instrument_index[inst_id] = []
                                    if job.job_id not in self._instrument_index[inst_id]:
                                        self._instrument_index[inst_id].append(job.job_id)
                        except Exception:
                            pass

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
            if self._persistent:
                with db_session() as conn:
                    row = conn.execute("SELECT COUNT(*) AS cnt FROM jobs").fetchone()
                    db_cnt = row["cnt"] if row else 0
                return max(len(self._jobs), db_cnt)
            return len(self._jobs)

    def clear(self) -> None:
        """Clears all jobs and indices (used for testing isolation)."""
        with self._lock:
            self._jobs.clear()
            self._instrument_index.clear()
            if self._persistent:
                with db_session() as conn:
                    conn.execute("DELETE FROM jobs")


# Global singleton instance for application runtime
TEST_JOB_REPOSITORY = TestJobRepository(persistent=True)
