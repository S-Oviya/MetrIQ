"""
MetrIQ P5 Review Repository
===========================
Person 5: Workflow + Evidence Engineer

Thread-safe in-memory repository for storing, indexing, and querying
Review records across multiple review cycles for each Test Job.
"""

from datetime import datetime
import threading
from typing import Any, Dict, List, Optional
from .models import Review, ReviewStatus


class ReviewRepository:
    """
    Thread-safe storage and chronological indexing for statutory Review records.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: Dict[str, Review] = {}
        # job_id -> list of review_ids in chronological creation order
        self._job_index: Dict[str, List[str]] = {}

    def save(self, review: Review) -> Review:
        """Stores or updates a Review record, maintaining chronological job index."""
        with self._lock:
            self._records[review.id] = review
            job_key = str(review.job_id).strip()

            if job_key not in self._job_index:
                self._job_index[job_key] = []
            if review.id not in self._job_index[job_key]:
                self._job_index[job_key].append(review.id)

            return review

    def get(self, review_id: str) -> Optional[Review]:
        """Retrieves a single review record by ID."""
        with self._lock:
            return self._records.get(review_id)

    def get_by_job(self, job_id: str) -> List[Review]:
        """Retrieves all reviews for a job in chronological order."""
        with self._lock:
            job_key = str(job_id).strip()
            review_ids = self._job_index.get(job_key, [])
            return [self._records[rid] for rid in review_ids if rid in self._records]

    def get_current_for_job(self, job_id: str) -> Optional[Review]:
        """
        Retrieves the active/current review for a job.
        Prefers a PENDING review if one exists; otherwise returns the latest completed review.
        """
        with self._lock:
            reviews = self.get_by_job(job_id)
            if not reviews:
                return None
            # Check for active pending review
            for r in reversed(reviews):
                if r.status == ReviewStatus.PENDING:
                    return r
            # Otherwise return most recent review
            return reviews[-1]

    def get_latest_for_job(self, job_id: str) -> Optional[Review]:
        """Returns the most recently created review for a job, or None."""
        with self._lock:
            reviews = self.get_by_job(job_id)
            return reviews[-1] if reviews else None

    def clear(self) -> None:
        """Clears all records and indexes (used for test isolation)."""
        with self._lock:
            self._records.clear()
            self._job_index.clear()


# Global singleton instance
REVIEW_REPOSITORY = ReviewRepository()
