"""
MetrIQ P5 Evidence & Attachment Package
=======================================
Person 5: Workflow + Evidence Engineer

Exports Evidence, EvidenceType, EvidenceStatus,
FileStorageService, FILE_STORAGE_SERVICE, StorageSecurityError,
EvidenceRepository, EVIDENCE_REPOSITORY,
EvidenceService, EVIDENCE_SERVICE,
custom exceptions, and the REST API router.
"""

from .models import (
    Evidence,
    EvidenceStatus,
    EvidenceType,
)
from .storage import (
    FILE_STORAGE_SERVICE,
    FileStorageService,
    StorageSecurityError,
)
from .repository import (
    EVIDENCE_REPOSITORY,
    EvidenceRepository,
)
from .service import (
    EVIDENCE_SERVICE,
    EvidenceNotFoundError,
    EvidenceSecurityError,
    EvidenceService,
    EvidenceValidationError,
    EvidenceWorkflowStateError,
)
from .router import router

__all__ = [
    "Evidence",
    "EvidenceType",
    "EvidenceStatus",
    "FileStorageService",
    "FILE_STORAGE_SERVICE",
    "StorageSecurityError",
    "EvidenceRepository",
    "EVIDENCE_REPOSITORY",
    "EvidenceService",
    "EVIDENCE_SERVICE",
    "EvidenceNotFoundError",
    "EvidenceValidationError",
    "EvidenceSecurityError",
    "EvidenceWorkflowStateError",
    "router",
]
