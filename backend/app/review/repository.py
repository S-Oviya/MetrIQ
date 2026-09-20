"""
MetrIQ P5 Review Repository
===========================
Person 5: Workflow + Evidence Engineer

Thread-safe repository for storing, indexing, and querying
Review records across multiple review cycles for each Test Job.
Backed by SQLite persistent storage.
"""

from datetime import datetime
import json
import threading
from typing import Any, Dict, List, Optional

from app.database.connection import db_session, init_db
from .models import Review, ReviewStatus


class ReviewRepository:
    """
    Thread-safe storage and chronological indexing for statutory Review records.
    Backed by SQLite persistent storage.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: Dict[str, Review] = {}
        # job_id -> list of review_ids in chronological creation order
        self._job_index: Dict[str, List[str]] = {}
        init_db()
        self._load_from_db()

    def _load_from_db(self) -> None:
        try:
            with db_session() as conn:
                rows = conn.execute("SELECT data_json FROM reviews ORDER BY created_at ASC").fetchall()
                for r in rows:
                    try:
                        review = Review.from_dict(json.loads(r["data_json"]))
                        self._populate_indices(review)
                    except Exception:
                        pass
        except Exception:
            pass

    def _populate_indices(self, review: Review) -> None:
        self._records[review.id] = review
        job_key = str(review.job_id).strip()
        if job_key not in self._job_index:
            self._job_index[job_key] = []
        if review.id not in self._job_index[job_key]:
            self._job_index[job_key].append(review.id)

    def save(self, review: Review) -> Review:
        """Stores or updates a Review record, maintaining chronological job index."""
        with self._lock:
            status_val = review.status.value if hasattr(review.status, "value") else str(review.status)
            decision_val = review.decision.value if (review.decision and hasattr(review.decision, "value")) else (str(review.decision) if review.decision else None)
            data_json = json.dumps(review.to_dict())

            with db_session() as conn:
                conn.execute(
                    """
                    INSERT INTO reviews (id, job_id, reviewer, status, decision, created_at, updated_at, data_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        job_id=excluded.job_id,
                        reviewer=excluded.reviewer,
                        status=excluded.status,
                        decision=excluded.decision,
                        data_json=excluded.data_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        review.id,
                        str(review.job_id).strip(),
                        review.reviewer,
                        status_val,
                        decision_val,
                        review.created_at,
                        review.updated_at,
                        data_json,
                    ),
                )

            self._populate_indices(review)
            return review

    def get(self, review_id: str) -> Optional[Review]:
        """Retrieves a single review record by ID."""
        with self._lock:
            clean_id = review_id.strip()
            if clean_id in self._records:
                return self._records[clean_id]
            with db_session() as conn:
                row = conn.execute(
                    "SELECT data_json FROM reviews WHERE id = ?",
                    (clean_id,),
                ).fetchone()
                if row:
                    review = Review.from_dict(json.loads(row["data_json"]))
                    self._populate_indices(review)
                    return review
            return None

    def get_by_job(self, job_id: str) -> List[Review]:
        """Retrieves all reviews for a job in chronological order."""
        with self._lock:
            job_key = str(job_id).strip()
            with db_session() as conn:
                rows = conn.execute(
                    "SELECT data_json FROM reviews WHERE job_id = ? ORDER BY created_at ASC",
                    (job_key,),
                ).fetchall()
                for r in rows:
                    try:
                        review = Review.from_dict(json.loads(r["data_json"]))
                        self._populate_indices(review)
                    except Exception:
                        pass

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
            with db_session() as conn:
                conn.execute("DELETE FROM reviews")


# Global singleton instance
REVIEW_REPOSITORY = ReviewRepository()
