"""
MetrIQ P5 Test Attempt Repository
=================================
Person 5: Workflow + Evidence Engineer

Thread-safe repository for storing and indexing TestAttempt and RetestRequest entities.
Enforces unique sequential attempt numbers per test under concurrent access.
Backed by SQLite persistent storage.
"""

from datetime import datetime
import json
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

from app.database.connection import db_session, init_db
from .models import RetestRequest, TestAttempt


class DuplicateAttemptNumberError(ValueError):
    """Raised when an attempt number is already assigned for a given (job_id, test_id)."""
    pass


class AttemptRepository:
    """
    Thread-safe repository providing atomic attempt allocation,
    unique constraint checking, and chronological index lookups.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._attempts: Dict[str, TestAttempt] = {}
        # (job_id, test_id.upper()) -> list of attempt_ids in ascending attempt_number order
        self._test_index: Dict[Tuple[str, str], List[str]] = {}
        # job_id -> list of attempt_ids
        self._job_index: Dict[str, List[str]] = {}
        # (job_id, test_id.upper(), attempt_number) -> attempt_id
        self._unique_number_index: Dict[Tuple[str, str, int], str] = {}
        # Retest requests storage
        self._retest_requests: Dict[str, RetestRequest] = {}
        self._job_retest_index: Dict[str, List[str]] = {}
        self._attempt_retest_index: Dict[str, str] = {}
        init_db()
        self._load_from_db()

    def _load_from_db(self) -> None:
        try:
            with db_session() as conn:
                rows = conn.execute("SELECT data_json FROM test_attempts ORDER BY started_at ASC").fetchall()
                for r in rows:
                    try:
                        attempt = TestAttempt.from_dict(json.loads(r["data_json"]))
                        self._populate_attempt_indices(attempt)
                    except Exception:
                        pass

                rrows = conn.execute("SELECT data_json FROM retest_requests ORDER BY requested_at ASC").fetchall()
                for r in rrows:
                    try:
                        req = RetestRequest.from_dict(json.loads(r["data_json"]))
                        self._populate_retest_indices(req)
                    except Exception:
                        pass
        except Exception:
            pass

    def _populate_attempt_indices(self, attempt: TestAttempt) -> None:
        self._attempts[attempt.id] = attempt
        job_key = str(attempt.job_id).strip()
        test_key = str(attempt.test_id).strip().upper()
        num_key = (job_key, test_key, attempt.attempt_number)
        self._unique_number_index[num_key] = attempt.id

        pair_key = (job_key, test_key)
        if pair_key not in self._test_index:
            self._test_index[pair_key] = []
        if attempt.id not in self._test_index[pair_key]:
            self._test_index[pair_key].append(attempt.id)

        if job_key not in self._job_index:
            self._job_index[job_key] = []
        if attempt.id not in self._job_index[job_key]:
            self._job_index[job_key].append(attempt.id)

    def _populate_retest_indices(self, req: RetestRequest) -> None:
        self._retest_requests[req.retest_id] = req
        job_key = str(req.job_id).strip()
        if job_key not in self._job_retest_index:
            self._job_retest_index[job_key] = []
        if req.retest_id not in self._job_retest_index[job_key]:
            self._job_retest_index[job_key].append(req.retest_id)
        self._attempt_retest_index[req.attempt_id] = req.retest_id

    def get_next_attempt_number(self, job_id: str, test_id: str) -> int:
        """
        Atomically computes the next sequential attempt number for a test on a job.
        Starts at 1, increments by 1.
        """
        with self._lock:
            clean_job = str(job_id).strip()
            clean_test = str(test_id).strip().upper()
            db_next = 1
            with db_session() as conn:
                row = conn.execute(
                    "SELECT COALESCE(MAX(attempt_number), 0) + 1 AS next_num FROM test_attempts WHERE job_id = ? AND UPPER(test_id) = ?",
                    (clean_job, clean_test),
                ).fetchone()
                if row:
                    db_next = row["next_num"]

            # Also verify against in-memory state
            key = (clean_job, clean_test)
            attempt_ids = self._test_index.get(key, [])
            mem_max = 0
            for aid in attempt_ids:
                att = self._attempts.get(aid)
                if att and att.attempt_number > mem_max:
                    mem_max = att.attempt_number

            return max(db_next, mem_max + 1)

    def save_attempt(self, attempt: TestAttempt) -> TestAttempt:
        """
        Saves or updates a TestAttempt.
        Enforces uniqueness constraint on (job_id, test_id, attempt_number).
        """
        with self._lock:
            job_key = str(attempt.job_id).strip()
            test_key = str(attempt.test_id).strip().upper()
            num_key = (job_key, test_key, attempt.attempt_number)

            # Check memory index
            existing_id = self._unique_number_index.get(num_key)
            if existing_id and existing_id != attempt.id:
                raise DuplicateAttemptNumberError(
                    f"Attempt number {attempt.attempt_number} already exists for test '{attempt.test_id}' in job '{attempt.job_id}' (attempt_id: {existing_id})."
                )

            # Check SQLite uniqueness
            with db_session() as conn:
                row = conn.execute(
                    "SELECT id FROM test_attempts WHERE job_id = ? AND UPPER(test_id) = ? AND attempt_number = ?",
                    (job_key, test_key, attempt.attempt_number),
                ).fetchone()
                if row and row["id"] != attempt.id:
                    raise DuplicateAttemptNumberError(
                        f"Attempt number {attempt.attempt_number} already exists for test '{attempt.test_id}' in job '{attempt.job_id}' (attempt_id: {row['id']})."
                    )

                status_val = attempt.status.value if hasattr(attempt.status, "value") else str(attempt.status)
                result_val = attempt.result.value if hasattr(attempt.result, "value") else (str(attempt.result) if attempt.result else None)
                data_json = json.dumps(attempt.to_dict())

                conn.execute(
                    """
                    INSERT INTO test_attempts (
                        id, job_id, test_id, attempt_number, status, result, operator, started_at, completed_at, data_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        job_id=excluded.job_id,
                        test_id=excluded.test_id,
                        attempt_number=excluded.attempt_number,
                        status=excluded.status,
                        result=excluded.result,
                        operator=excluded.operator,
                        started_at=excluded.started_at,
                        completed_at=excluded.completed_at,
                        data_json=excluded.data_json
                    """,
                    (
                        attempt.id,
                        job_key,
                        attempt.test_id,
                        attempt.attempt_number,
                        status_val,
                        result_val,
                        attempt.operator,
                        attempt.started_at,
                        attempt.completed_at,
                        data_json,
                    ),
                )

            self._populate_attempt_indices(attempt)
            return attempt

    save = save_attempt

    def get_attempt(self, attempt_id: str) -> Optional[TestAttempt]:
        """Retrieves a test attempt by its ID."""
        with self._lock:
            if attempt_id in self._attempts:
                return self._attempts[attempt_id]
            with db_session() as conn:
                row = conn.execute(
                    "SELECT data_json FROM test_attempts WHERE id = ?",
                    (attempt_id,),
                ).fetchone()
                if row:
                    attempt = TestAttempt.from_dict(json.loads(row["data_json"]))
                    self._populate_attempt_indices(attempt)
                    return attempt
            return None

    def get_attempts_for_test(self, job_id: str, test_id: str) -> List[TestAttempt]:
        """
        Retrieves all attempts for a given test on a job,
        sorted in ascending attempt_number order.
        """
        with self._lock:
            clean_job = str(job_id).strip()
            clean_test = str(test_id).strip().upper()
            with db_session() as conn:
                rows = conn.execute(
                    "SELECT data_json FROM test_attempts WHERE job_id = ? AND UPPER(test_id) = ? ORDER BY attempt_number ASC",
                    (clean_job, clean_test),
                ).fetchall()
                for r in rows:
                    try:
                        att = TestAttempt.from_dict(json.loads(r["data_json"]))
                        self._populate_attempt_indices(att)
                    except Exception:
                        pass

            key = (clean_job, clean_test)
            attempt_ids = self._test_index.get(key, [])
            attempts = [self._attempts[aid] for aid in attempt_ids if aid in self._attempts]
            return sorted(attempts, key=lambda a: a.attempt_number)

    def get_latest_attempt_for_test(self, job_id: str, test_id: str) -> Optional[TestAttempt]:
        """Returns the attempt with the highest attempt_number for a test."""
        attempts = self.get_attempts_for_test(job_id, test_id)
        if attempts:
            return attempts[-1]
        return None

    def get_attempts_by_job(self, job_id: str) -> List[TestAttempt]:
        """Retrieves all attempts recorded for a job."""
        with self._lock:
            clean_job = str(job_id).strip()
            with db_session() as conn:
                rows = conn.execute(
                    "SELECT data_json FROM test_attempts WHERE job_id = ? ORDER BY test_id, attempt_number ASC",
                    (clean_job,),
                ).fetchall()
                for r in rows:
                    try:
                        att = TestAttempt.from_dict(json.loads(r["data_json"]))
                        self._populate_attempt_indices(att)
                    except Exception:
                        pass

            attempt_ids = self._job_index.get(clean_job, [])
            attempts = [self._attempts[aid] for aid in attempt_ids if aid in self._attempts]
            return sorted(attempts, key=lambda a: (a.test_id, a.attempt_number))

    # =========================================================================
    # Retest Requests
    # =========================================================================

    def save_retest_request(self, req: RetestRequest) -> RetestRequest:
        """Saves a retest request record."""
        with self._lock:
            with db_session() as conn:
                conn.execute(
                    """
                    INSERT INTO retest_requests (
                        retest_id, job_id, test_id, attempt_id, attempt_number, data_json, requested_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(retest_id) DO UPDATE SET
                        job_id=excluded.job_id,
                        test_id=excluded.test_id,
                        attempt_id=excluded.attempt_id,
                        attempt_number=excluded.attempt_number,
                        data_json=excluded.data_json
                    """,
                    (
                        req.retest_id,
                        req.job_id,
                        req.test_id,
                        req.attempt_id,
                        req.attempt_number,
                        json.dumps(req.to_dict()),
                        req.requested_at,
                    ),
                )

            self._populate_retest_indices(req)
            return req

    def get_retest_requests_by_job(self, job_id: str) -> List[RetestRequest]:
        """Retrieves all retest requests for a job."""
        with self._lock:
            clean_job = str(job_id).strip()
            with db_session() as conn:
                rows = conn.execute(
                    "SELECT data_json FROM retest_requests WHERE job_id = ? ORDER BY requested_at ASC",
                    (clean_job,),
                ).fetchall()
                for r in rows:
                    try:
                        req = RetestRequest.from_dict(json.loads(r["data_json"]))
                        self._populate_retest_indices(req)
                    except Exception:
                        pass

            req_ids = self._job_retest_index.get(clean_job, [])
            return [self._retest_requests[rid] for rid in req_ids if rid in self._retest_requests]

    def get_retest_request_by_attempt(self, attempt_id: str) -> Optional[RetestRequest]:
        """Retrieves the retest request associated with an attempt."""
        with self._lock:
            rid = self._attempt_retest_index.get(attempt_id)
            if rid and rid in self._retest_requests:
                return self._retest_requests[rid]
            with db_session() as conn:
                row = conn.execute(
                    "SELECT data_json FROM retest_requests WHERE attempt_id = ?",
                    (attempt_id,),
                ).fetchone()
                if row:
                    req = RetestRequest.from_dict(json.loads(row["data_json"]))
                    self._populate_retest_indices(req)
                    return req
            return None

    # =========================================================================
    # Maintenance / Testing
    # =========================================================================

    def clear(self) -> None:
        """Clears all records and indices for test isolation."""
        with self._lock:
            self._attempts.clear()
            self._test_index.clear()
            self._job_index.clear()
            self._unique_number_index.clear()
            self._retest_requests.clear()
            self._job_retest_index.clear()
            self._attempt_retest_index.clear()
            with db_session() as conn:
                conn.execute("DELETE FROM test_attempts")
                conn.execute("DELETE FROM retest_requests")


# Global singleton repository
ATTEMPT_REPOSITORY = AttemptRepository()
