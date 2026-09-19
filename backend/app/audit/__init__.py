"""
MetrIQ P5 Audit Trail & Traceability Package
============================================
Person 5: Workflow + Evidence Engineer

Exports AuditLog, AuditAction, EntityType,
AuditRepository, AUDIT_REPOSITORY, AuditImmutabilityError,
AuditService, AUDIT_SERVICE, record_audit, and REST API router.
"""

from .models import (
    AuditAction,
    AuditLog,
    EntityType,
)
from .repository import (
    AUDIT_REPOSITORY,
    AuditImmutabilityError,
    AuditRepository,
)
from .service import (
    AUDIT_SERVICE,
    AuditService,
    record_audit,
)
from .router import router

__all__ = [
    "AuditLog",
    "AuditAction",
    "EntityType",
    "AuditRepository",
    "AUDIT_REPOSITORY",
    "AuditImmutabilityError",
    "AuditService",
    "AUDIT_SERVICE",
    "record_audit",
    "router",
]
