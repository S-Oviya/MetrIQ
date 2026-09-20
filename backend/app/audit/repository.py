"""
MetrIQ P5 Audit Repository
==========================
Person 5: Workflow + Evidence Engineer

Thread-safe, append-only persistence and multi-dimensional indexing
for statutory AuditLog entities. Enforces immutability by strictly rejecting
updates or deletions. Backed by SQLite persistent storage.
"""

from datetime import datetime
import json
import threading
from typing import Any, Dict, List, Optional, Tuple, Union

from app.database.connection import db_session, init_db
from .models import AuditAction, AuditLog, EntityType


class AuditImmutabilityError(PermissionError):
    """Raised when an illegal mutation or deletion of an audit entry is attempted."""
    pass


class AuditRepository:
    """
    Append-only repository for storing and querying immutable statutory audit logs.
    Maintains chronological ordering and indexes by Job, Entity, Actor, and Action.
    Backed by SQLite persistent storage.
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
        init_db()
        self._load_from_db()

    def _load_from_db(self) -> None:
        try:
            with db_session() as conn:
                rows = conn.execute("SELECT data_json FROM audit_logs ORDER BY timestamp ASC, rowid ASC").fetchall()
                for r in rows:
                    try:
                        log = AuditLog.from_dict(json.loads(r["data_json"]))
                        self._populate_indices(log)
                    except Exception:
                        pass
        except Exception:
            pass

    def _populate_indices(self, log: AuditLog) -> None:
        if log.id in self._records:
            return
        self._records[log.id] = log
        self._chronological.append(log.id)

        # 1. Entity Index
        etype = log.entity_type.value if hasattr(log.entity_type, "value") else str(log.entity_type)
        ekey = (etype.strip().upper(), str(log.entity_id).strip().upper())
        if ekey not in self._entity_index:
            self._entity_index[ekey] = []
        if log.id not in self._entity_index[ekey]:
            self._entity_index[ekey].append(log.id)

        # 2. Job Index
        jid = log.job_id
        if jid:
            clean_jid = str(jid).strip()
            if clean_jid not in self._job_index:
                self._job_index[clean_jid] = []
            if log.id not in self._job_index[clean_jid]:
                self._job_index[clean_jid].append(log.id)

        # 3. Actor Index
        clean_actor = str(log.actor or "").strip().upper()
        if clean_actor:
            if clean_actor not in self._actor_index:
                self._actor_index[clean_actor] = []
            if log.id not in self._actor_index[clean_actor]:
                self._actor_index[clean_actor].append(log.id)

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

            with db_session() as conn:
                row = conn.execute("SELECT 1 FROM audit_logs WHERE id = ?", (log.id,)).fetchone()
                if row:
                    raise AuditImmutabilityError(
                        f"Audit entry '{log.id}' already exists. Audit records are strictly append-only and cannot be overwritten."
                    )

                etype = log.entity_type.value if hasattr(log.entity_type, "value") else str(log.entity_type)
                action_val = log.action.value if hasattr(log.action, "value") else str(log.action)
                data_json = json.dumps(log.to_dict())

                conn.execute(
                    """
                    INSERT INTO audit_logs (id, job_id, entity_type, entity_id, action, actor, timestamp, created_at, data_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        log.id,
                        log.job_id,
                        etype,
                        log.entity_id,
                        action_val,
                        log.user_id,
                        log.timestamp,
                        log.created_at,
                        data_json,
                    ),
                )

            self._populate_indices(log)
            return log

    def get(self, audit_id: str) -> Optional[AuditLog]:
        """Retrieves a single audit log entry by ID."""
        with self._lock:
            clean_id = audit_id.strip()
            if clean_id in self._records:
                return self._records[clean_id]
            with db_session() as conn:
                row = conn.execute("SELECT data_json FROM audit_logs WHERE id = ?", (clean_id,)).fetchone()
                if row:
                    log = AuditLog.from_dict(json.loads(row["data_json"]))
                    self._populate_indices(log)
                    return log
            return None

    def get_by_job(self, job_id: str) -> List[AuditLog]:
        """Retrieves complete chronological audit trail for a job."""
        with self._lock:
            clean_jid = str(job_id).strip()
            with db_session() as conn:
                rows = conn.execute(
                    "SELECT data_json FROM audit_logs WHERE job_id = ? ORDER BY timestamp ASC, rowid ASC",
                    (clean_jid,),
                ).fetchall()
                for r in rows:
                    try:
                        log = AuditLog.from_dict(json.loads(r["data_json"]))
                        self._populate_indices(log)
                    except Exception:
                        pass

            log_ids = self._job_index.get(clean_jid, [])
            return [self._records[lid] for lid in log_ids if lid in self._records]

    def get_by_entity(self, entity_type: Union[str, EntityType], entity_id: str) -> List[AuditLog]:
        """Retrieves chronological audit trail for a specific domain entity."""
        with self._lock:
            etype = entity_type.value if hasattr(entity_type, "value") else str(entity_type)
            clean_etype = etype.strip().upper()
            clean_eid = str(entity_id).strip().upper()

            with db_session() as conn:
                rows = conn.execute(
                    "SELECT data_json FROM audit_logs WHERE UPPER(entity_type) = ? AND UPPER(entity_id) = ? ORDER BY timestamp ASC, rowid ASC",
                    (clean_etype, clean_eid),
                ).fetchall()
                for r in rows:
                    try:
                        log = AuditLog.from_dict(json.loads(r["data_json"]))
                        self._populate_indices(log)
                    except Exception:
                        pass

            ekey = (clean_etype, clean_eid)
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
            # Sync all logs from SQLite
            with db_session() as conn:
                rows = conn.execute("SELECT data_json FROM audit_logs ORDER BY timestamp ASC, rowid ASC").fetchall()
                for r in rows:
                    try:
                        log = AuditLog.from_dict(json.loads(r["data_json"]))
                        self._populate_indices(log)
                    except Exception:
                        pass

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
            with db_session() as conn:
                conn.execute("DELETE FROM audit_logs")


# Global singleton instance
AUDIT_REPOSITORY = AuditRepository()
