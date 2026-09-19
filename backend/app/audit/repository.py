"""
MetrIQ P5 Audit Repository
==========================
Person 5: Workflow + Evidence Engineer

Thread-safe, append-only in-memory storage and multi-dimensional indexing
for statutory AuditLog entities. Enforces immutability by strictly rejecting
updates or deletions.
"""

from datetime import datetime
import threading
from typing import Any, Dict, List, Optional, Tuple, Union
from .models import AuditAction, AuditLog, EntityType


class AuditImmutabilityError(PermissionError):
    """Raised when an illegal mutation or deletion of an audit entry is attempted."""
    pass


class AuditRepository:
    """
    Append-only repository for storing and querying immutable statutory audit logs.
    Maintains chronological ordering and indexes by Job, Entity, Actor, and Action.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: Dict[str, AuditLog] = {}
        self._chronological: List[str] = []
        # job_id -> list of audit_ids
        self._job_index: Dict[str, List[str]] = {}
        # (entity_type.upper(), entity_id.upper()) -> list of audit_ids
        self._entity_index: Dict[Tuple[str, str], List[str]] = {}
        # actor.upper() -> list of audit_ids
        self._actor_index: Dict[str, List[str]] = {}

    def record(self, log: AuditLog) -> AuditLog:
        """
        Appends an immutable audit log entry.
        Maintains all dimensional indices atomically.
        """
        with self._lock:
            if log.id in self._records:
                raise AuditImmutabilityError(
                    f"Audit entry '{log.id}' already exists. Audit records are strictly append-only and cannot be overwritten."
                )

            self._records[log.id] = log
            self._chronological.append(log.id)

            # 1. Entity Index
            etype = log.entity_type.value if hasattr(log.entity_type, "value") else str(log.entity_type)
            ekey = (etype.strip().upper(), str(log.entity_id).strip().upper())
            if ekey not in self._entity_index:
                self._entity_index[ekey] = []
            self._entity_index[ekey].append(log.id)

            # 2. Job Index
            jid = log.job_id
            if jid:
                clean_jid = str(jid).strip()
                if clean_jid not in self._job_index:
                    self._job_index[clean_jid] = []
                self._job_index[clean_jid].append(log.id)

            # 3. Actor Index
            clean_actor = str(log.actor or "").strip().upper()
            if clean_actor:
                if clean_actor not in self._actor_index:
                    self._actor_index[clean_actor] = []
                self._actor_index[clean_actor].append(log.id)

            return log

    def get(self, audit_id: str) -> Optional[AuditLog]:
        """Retrieves a single audit log entry by ID."""
        with self._lock:
            return self._records.get(audit_id)

    def get_by_job(self, job_id: str) -> List[AuditLog]:
        """Retrieves complete chronological audit trail for a job."""
        with self._lock:
            clean_jid = str(job_id).strip()
            log_ids = self._job_index.get(clean_jid, [])
            return [self._records[lid] for lid in log_ids if lid in self._records]

    def get_by_entity(self, entity_type: Union[str, EntityType], entity_id: str) -> List[AuditLog]:
        """Retrieves chronological audit trail for a specific domain entity."""
        with self._lock:
            etype = entity_type.value if hasattr(entity_type, "value") else str(entity_type)
            ekey = (etype.strip().upper(), str(entity_id).strip().upper())
            log_ids = self._entity_index.get(ekey, [])
            return [self._records[lid] for lid in log_ids if lid in self._records]

    def query(
        self,
        action: Optional[Union[str, AuditAction]] = None,
        actor: Optional[str] = None,
        entity_type: Optional[Union[str, EntityType]] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[AuditLog]:
        """
        Queries audit logs with multi-parameter filtering, returning results in chronological order.
        """
        with self._lock:
            results: List[AuditLog] = []

            filter_action = AuditAction.from_value(action) if action else None
            filter_etype = EntityType.from_value(entity_type) if entity_type else None
            filter_actor = str(actor).strip().upper() if actor else None

            for lid in self._chronological:
                log = self._records.get(lid)
                if not log:
                    continue

                if filter_action and log.action != filter_action:
                    continue
                if filter_etype and log.entity_type != filter_etype:
                    continue
                if filter_actor and str(log.actor).strip().upper() != filter_actor:
                    continue
                if from_date and log.timestamp < from_date:
                    continue
                if to_date and log.timestamp > to_date:
                    continue

                results.append(log)

            return results

    def update(self, *args, **kwargs) -> None:
        """Explicitly prohibited to preserve statutory non-repudiation."""
        raise AuditImmutabilityError("Statutory audit logs are immutable and cannot be updated.")

    def delete(self, *args, **kwargs) -> None:
        """Explicitly prohibited to preserve statutory non-repudiation."""
        raise AuditImmutabilityError("Statutory audit logs are immutable and cannot be deleted.")

    def clear(self) -> None:
        """Clears all records and indices for test isolation."""
        with self._lock:
            self._records.clear()
            self._chronological.clear()
            self._job_index.clear()
            self._entity_index.clear()
            self._actor_index.clear()


# Global singleton instance
AUDIT_REPOSITORY = AuditRepository()
