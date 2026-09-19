"""
MetrIQ P5 Test Attempt Repository
=================================
Person 5: Workflow + Evidence Engineer

Thread-safe in-memory repository for storing and indexing TestAttempt and RetestRequest entities.
Enforces unique sequential attempt numbers per test under concurrent access.
"""

from datetime import datetime
import threading
from typing import Any, Dict, List, Optional, Set, Tuple
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

    def get_next_attempt_number(self, job_id: str, test_id: str) -> int:
        """
        Atomically computes the next sequential attempt number for a test on a job.
        Starts at 1, increments by 1.
        """
        with self._lock:
            key = (str(job_id).strip(), str(test_id).strip().upper())
            attempt_ids = self._test_index.get(key, [])
            if not attempt_ids:
                return 1
            highest = 0
            for aid in attempt_ids:
                att = self._attempts.get(aid)
                if att and att.attempt_number > highest:
                    highest = att.attempt_number
            return highest + 1

    def save_attempt(self, attempt: TestAttempt) -> TestAttempt:
        """
        Saves or updates a TestAttempt.
        Enforces uniqueness constraint on (job_id, test_id, attempt_number).
        """
        with self._lock:
            job_key = str(attempt.job_id).strip()
            test_key = str(attempt.test_id).strip().upper()
            num_key = (job_key, test_key, attempt.attempt_number)

            # Unique constraint check
            existing_id = self._unique_number_index.get(num_key)
            if existing_id and existing_id != attempt.id:
                raise DuplicateAttemptNumberError(
                    f"Attempt number {attempt.attempt_number} already exists for test '{attempt.test_id}' in job '{attempt.job_id}' (attempt_id: {existing_id})."
                )

            # Update unique index
            self._unique_number_index[num_key] = attempt.id
            self._attempts[attempt.id] = attempt

            # Maintain compound test index
            pair_key = (job_key, test_key)
            if pair_key not in self._test_index:
                self._test_index[pair_key] = []
            if attempt.id not in self._test_index[pair_key]:
                self._test_index[pair_key].append(attempt.id)

            # Maintain job index
            if job_key not in self._job_index:
                self._job_index[job_key] = []
            if attempt.id not in self._job_index[job_key]:
                self._job_index[job_key].append(attempt.id)

            return attempt

    save = save_attempt

    def get_attempt(self, attempt_id: str) -> Optional[TestAttempt]:
        """Retrieves a test attempt by its ID."""
        with self._lock:
            return self._attempts.get(attempt_id)

    def get_attempts_for_test(self, job_id: str, test_id: str) -> List[TestAttempt]:
        """
        Retrieves all attempts for a given test on a job,
        sorted in ascending attempt_number order.
        """
        with self._lock:
            key = (str(job_id).strip(), str(test_id).strip().upper())
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
            attempt_ids = self._job_index.get(str(job_id).strip(), [])
            attempts = [self._attempts[aid] for aid in attempt_ids if aid in self._attempts]
            return sorted(attempts, key=lambda a: (a.test_id, a.attempt_number))

    # =========================================================================
    # Retest Requests
    # =========================================================================

    def save_retest_request(self, req: RetestRequest) -> RetestRequest:
        """Saves a retest request record."""
        with self._lock:
            self._retest_requests[req.retest_id] = req
            job_key = str(req.job_id).strip()
            if job_key not in self._job_retest_index:
                self._job_retest_index[job_key] = []
            if req.retest_id not in self._job_retest_index[job_key]:
                self._job_retest_index[job_key].append(req.retest_id)
            self._attempt_retest_index[req.attempt_id] = req.retest_id
            return req

    def get_retest_requests_by_job(self, job_id: str) -> List[RetestRequest]:
        """Retrieves all retest requests for a job."""
        with self._lock:
            req_ids = self._job_retest_index.get(str(job_id).strip(), [])
            return [self._retest_requests[rid] for rid in req_ids if rid in self._retest_requests]

    def get_retest_request_by_attempt(self, attempt_id: str) -> Optional[RetestRequest]:
        """Retrieves the retest request associated with an attempt."""
        with self._lock:
            rid = self._attempt_retest_index.get(attempt_id)
            if rid:
                return self._retest_requests.get(rid)
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


# Global singleton repository
ATTEMPT_REPOSITORY = AttemptRepository()
