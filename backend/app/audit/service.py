"""
MetrIQ P5 Central Audit Service
===============================
Person 5: Workflow + Evidence Engineer

Reusable, thread-safe audit service coordinating statutory event logging,
sensitive data redaction, entity change tracking, and read-only query APIs.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional, Union
import uuid

from .models import AuditAction, AuditLog, EntityType
from .repository import AUDIT_REPOSITORY, AuditImmutabilityError, AuditRepository

# Keys that must never be recorded in plain text in audit logs
SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "access_token",
    "api_key",
    "auth",
    "authorization",
    "private_key",
    "certificate_key",
    "pin",
}


def _sanitize_dict(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Recursively scrubs sensitive keys, passwords, tokens, and excessive payloads
    from audit dictionary entries.
    """
    if data is None:
        return None
    clean: Dict[str, Any] = {}
    for k, v in data.items():
        k_lower = str(k).lower()
        if any(sens in k_lower for sens in SENSITIVE_KEYS):
            clean[k] = "[REDACTED]"
        elif isinstance(v, dict):
            clean[k] = _sanitize_dict(v)
        elif isinstance(v, bytes):
            clean[k] = f"<binary data: {len(v)} bytes>"
        elif isinstance(v, str) and len(v) > 2048:
            clean[k] = v[:2048] + "...[TRUNCATED]"
        else:
            clean[k] = v
    return clean


class AuditService:
    """
    Central domain service for recording and querying statutory audit events.
    Thread-safe and fail-safe.
    """

    def __init__(self, repository: Optional[AuditRepository] = None) -> None:
        self.repo = repository or AUDIT_REPOSITORY
        self._lock = threading.RLock()

    def record_audit(
        self,
        actor: str,
        action: Union[str, AuditAction],
        entity_type: Union[str, EntityType],
        entity_id: str,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        job_id: Optional[str] = None,
    ) -> AuditLog:
        """
        Records an append-only statutory audit event.
        Sanitizes sensitive data and preserves before-and-after change diffs.
        """
        with self._lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            audit_id = f"AUD-{uuid.uuid4().hex[:8].upper()}"

            clean_action = AuditAction.from_value(action)
            clean_etype = EntityType.from_value(entity_type)
            clean_actor = str(actor or "SYSTEM").strip() or "SYSTEM"
            clean_entity_id = str(entity_id or "").strip()

            meta = dict(metadata or {})
            if job_id and "job_id" not in meta:
                meta["job_id"] = str(job_id).strip()

            sanitized_old = _sanitize_dict(old_value)
            sanitized_new = _sanitize_dict(new_value)
            sanitized_meta = _sanitize_dict(meta) or {}

            log = AuditLog(
                id=audit_id,
                timestamp=now_iso,
                user_id=clean_actor,
                action=clean_action,
                entity_type=clean_etype,
                entity_id=clean_entity_id,
                old_value=sanitized_old,
                new_value=sanitized_new,
                metadata=sanitized_meta,
                created_at=now_iso,
            )

            self.repo.record(log)
            return log

    def get_job_audit_trail(self, job_id: str) -> List[AuditLog]:
        """Retrieves complete chronological audit trail for a test job."""
        return self.repo.get_by_job(job_id)

    def get_entity_audit_trail(
        self,
        entity_type: Union[str, EntityType],
        entity_id: str,
    ) -> List[AuditLog]:
        """Retrieves complete chronological audit trail for a specific entity."""
        return self.repo.get_by_entity(entity_type, entity_id)

    def query_audit_logs(
        self,
        action: Optional[Union[str, AuditAction]] = None,
        actor: Optional[str] = None,
        entity_type: Optional[Union[str, EntityType]] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[AuditLog]:
        """Queries audit logs with multi-parameter filtering."""
        return self.repo.query(
            action=action,
            actor=actor,
            entity_type=entity_type,
            from_date=from_date,
            to_date=to_date,
        )

    def get_audit_entry(self, audit_id: str) -> Optional[AuditLog]:
        """Retrieves a single audit log entry by ID."""
        return self.repo.get(audit_id)


# Global singleton service
AUDIT_SERVICE = AuditService()


def record_audit(
    actor: str,
    action: Union[str, AuditAction],
    entity_type: Union[str, EntityType],
    entity_id: str,
    old_value: Optional[Dict[str, Any]] = None,
    new_value: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,
) -> AuditLog:
    """Convenience functional helper for recording audit events across modules."""
    return AUDIT_SERVICE.record_audit(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        metadata=metadata,
        job_id=job_id,
    )
