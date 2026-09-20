"""
MetrIQ P5 Evidence & Attachment Service
=======================================
Person 5: Workflow + Evidence Engineer

Coordinates evidence validation, secure local storage, cryptographic checksumming,
job/test/attempt relationship enforcement, and workflow lifecycle access controls.
"""

from datetime import datetime, timezone
import mimetypes
import os
import threading
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from app.attempts.repository import ATTEMPT_REPOSITORY, AttemptRepository
from app.attempts.service import AttemptNotFoundError
from app.calculations.models import TestType
from app.jobs.models import JobStatus, TestJob
from app.jobs.repository import TEST_JOB_REPOSITORY, TestJobRepository
from app.workflow.service import JobNotFoundError
from .models import Evidence, EvidenceStatus, EvidenceType
from .repository import EVIDENCE_REPOSITORY, EvidenceRepository
from .storage import FILE_STORAGE_SERVICE, FileStorageService, StorageSecurityError


class EvidenceNotFoundError(KeyError):
    """Raised when an evidence record cannot be located."""
    pass


class EvidenceValidationError(ValueError):
    """Raised when evidence metadata, file format, or size fails validation."""

    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.field = field


class EvidenceSecurityError(ValueError):
    """Raised on unauthorized cross-job access or path traversal attempts."""

    def __init__(self, message: str, error_code: str = "EVIDENCE_ACCESS_DENIED"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class EvidenceWorkflowStateError(ValueError):
    """Raised when evidence operations violate the current job workflow stage."""

    def __init__(self, message: str, error_code: str = "INVALID_WORKFLOW_STAGE"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


# Lifecycle states where evidence uploading is prohibited (terminal states)
TERMINAL_JOB_STATES = {
    JobStatus.REPORT_GENERATED,
    JobStatus.CLOSED,
    JobStatus.CERTIFIED,
    JobStatus.CANCELLED,
}

# Lifecycle states where evidence deletion is prohibited (audited/approved states)
LOCKED_EVIDENCE_STATES = {
    JobStatus.APPROVED,
    JobStatus.REPORT_GENERATED,
    JobStatus.CLOSED,
    JobStatus.CERTIFIED,
}

# Permitted file extensions for statutory metrological attachments
ALLOWED_EXTENSIONS = {
    # Images
    ".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".bmp", ".gif",
    # Videos
    ".mp4", ".webm", ".mov", ".avi", ".mkv",
    # Documents
    ".pdf", ".txt", ".csv", ".json", ".docx", ".xlsx", ".zip", ".xml", ".log",
}

DEFAULT_MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 Megabytes


class EvidenceService:
    """
    Domain service governing evidence and attachment operations.
    Enforces file integrity, relationship traceability, and statutory retention.
    """

    def __init__(
        self,
        repository: Optional[EvidenceRepository] = None,
        storage_service: Optional[FileStorageService] = None,
        job_repository: Optional[TestJobRepository] = None,
        attempt_repository: Optional[AttemptRepository] = None,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
    ) -> None:
        self.repo = repository or EVIDENCE_REPOSITORY
        self.storage = storage_service or FILE_STORAGE_SERVICE
        self.jobs = job_repository or TEST_JOB_REPOSITORY
        self.attempts = attempt_repository or ATTEMPT_REPOSITORY
        self.max_file_size = max_file_size
        self._lock = threading.RLock()

    # =========================================================================
    # Validation Helpers
    # =========================================================================

    def _validate_file_type_and_mime(self, filename: str, content: bytes, mime_type: Optional[str]) -> str:
        """Validates filename extension and infers/checks MIME type."""
        _, ext = os.path.splitext(filename.lower())
        if not ext or ext not in ALLOWED_EXTENSIONS:
            raise EvidenceValidationError(
                f"File extension '{ext}' is not supported. Permitted extensions: {sorted(list(ALLOWED_EXTENSIONS))}",
                field="file_name",
            )

        # Infer MIME if missing or generic or HTTP JSON wrapper
        detected_mime = mime_type
        if not detected_mime or detected_mime in ("application/octet-stream", "binary/octet-stream", "application/json"):
            guessed, _ = mimetypes.guess_type(filename)
            detected_mime = guessed or "application/octet-stream"

        return detected_mime

    def _validate_relationships(
        self,
        job: TestJob,
        test_id: Optional[str],
        attempt_id: Optional[str],
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Enforces strict hierarchical relationship:
        Job -> Test -> Attempt -> Evidence
        """
        resolved_test_id = str(test_id).strip() if test_id else None
        resolved_attempt_id = str(attempt_id).strip() if attempt_id else None

        if resolved_attempt_id:
            attempt = self.attempts.get_attempt(resolved_attempt_id)
            if not attempt:
                raise AttemptNotFoundError(f"Test attempt '{resolved_attempt_id}' not found.")

            # Validate attempt belongs to this job
            if attempt.job_id != job.job_id:
                raise EvidenceValidationError(
                    f"Attempt '{resolved_attempt_id}' belongs to job '{attempt.job_id}', not '{job.job_id}'.",
                    field="attempt_id",
                )

            # Validate attempt matches test_id if supplied
            if resolved_test_id:
                if attempt.test_id.upper() != resolved_test_id.upper():
                    raise EvidenceValidationError(
                        f"Attempt '{resolved_attempt_id}' belongs to test '{attempt.test_id}', not '{resolved_test_id}'.",
                        field="test_id",
                    )
            else:
                resolved_test_id = attempt.test_id

        if resolved_test_id and job.applicable_tests:
            clean_test_upper = resolved_test_id.upper()
            applicable_uppers = [t.upper() for t in job.applicable_tests]
            if clean_test_upper not in applicable_uppers:
                # Check test plan
                in_plan = False
                if job.test_plan and isinstance(job.test_plan, dict):
                    for t in job.test_plan.get("tests", []):
                        if (
                            str(t.get("test_id", "")).upper() == clean_test_upper
                            or str(t.get("test_type", "")).upper() == clean_test_upper
                        ):
                            in_plan = True
                            break
                if not in_plan:
                    try:
                        TestType.from_value(resolved_test_id)
                    except ValueError:
                        raise EvidenceValidationError(
                            f"Test '{resolved_test_id}' is not an applicable test for job '{job.job_id}'.",
                            field="test_id",
                        )

        return resolved_test_id, resolved_attempt_id

    # =========================================================================
    # Upload Operations
    # =========================================================================

    def upload_evidence(
        self,
        job_id: str,
        file_name: str,
        content: bytes,
        evidence_type: Optional[Union[str, EvidenceType]] = None,
        type: Optional[Union[str, EvidenceType]] = None,
        test_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
        description: str = "",
        uploaded_by: str = "SYSTEM",
        mime_type: Optional[str] = None,
    ) -> Evidence:
        """
        Uploads and links a new evidence attachment:
        1. Validates job existence and lifecycle stage.
        2. Validates test/attempt relationship integrity.
        3. Validates file size, extension, and content.
        4. Calculates cryptographic SHA-256 checksum and saves to safe local storage.
        5. Records and indexes Evidence entity.
        """
        with self._lock:
            # 1. Verify job exists
            job = self.jobs.get(job_id)
            if not job:
                raise JobNotFoundError(f"Test job '{job_id}' not found.")

            # 2. Check workflow stage (prohibit upload in terminal states)
            if job.status in TERMINAL_JOB_STATES or getattr(job.status, "is_terminal", False):
                raise EvidenceWorkflowStateError(
                    f"Cannot upload evidence: job '{job_id}' is in terminal state '{job.status.value}'.",
                    error_code="JOB_TERMINAL_STATE",
                )

            # 3. Validate evidence type
            raw_type = evidence_type or type or EvidenceType.OTHER
            try:
                ev_type = EvidenceType.from_value(raw_type)
            except ValueError as e:
                raise EvidenceValidationError(str(e), field="type")

            # 4. Validate file content and size
            if not content or len(content) == 0:
                raise EvidenceValidationError("File content cannot be empty.", field="file")
            if len(content) > self.max_file_size:
                raise EvidenceValidationError(
                    f"File size ({len(content)} bytes) exceeds maximum permitted limit of {self.max_file_size} bytes.",
                    field="file_size",
                )

            # 5. Validate filename and MIME
            clean_filename = self.storage.sanitize_filename(file_name)
            validated_mime = self._validate_file_type_and_mime(clean_filename, content, mime_type)

            # 6. Validate test / attempt relationship
            val_test_id, val_attempt_id = self._validate_relationships(job, test_id, attempt_id)

            # 7. Generate safe evidence ID and store file
            evidence_id = f"EVD-{uuid.uuid4().hex[:8].upper()}"
            storage_ref, file_size, checksum = self.storage.save_file(
                job_id=job.job_id,
                evidence_id=evidence_id,
                filename=clean_filename,
                content=content,
            )

            # 8. Create Evidence entity
            now_iso = datetime.now(timezone.utc).isoformat()
            clean_uploader = str(uploaded_by or "SYSTEM").strip()

            evidence = Evidence(
                id=evidence_id,
                job_id=job.job_id,
                test_id=val_test_id,
                attempt_id=val_attempt_id,
                type=ev_type,
                file_name=clean_filename,
                storage_reference=storage_ref,
                mime_type=validated_mime,
                file_size=file_size,
                checksum=checksum,
                uploaded_by=clean_uploader,
                uploaded_at=now_iso,
                description=str(description or "").strip(),
                status=EvidenceStatus.ACTIVE,
                created_at=now_iso,
                updated_at=now_iso,
            )

            # 9. Persist in repository
            self.repo.save(evidence)

            # 10. Synchronize with Job entity
            if hasattr(job, "evidence_ids"):
                if evidence.id not in job.evidence_ids:
                    job.evidence_ids.append(evidence.id)
            job.updated_at = now_iso
            self.jobs.save(job)

            # Emit statutory audit log
            try:
                from app.audit.service import AUDIT_SERVICE
                from app.audit.models import AuditAction, EntityType
                AUDIT_SERVICE.record_audit(
                    actor=clean_uploader,
                    action=AuditAction.EVIDENCE_UPLOADED,
                    entity_type=EntityType.EVIDENCE,
                    entity_id=evidence.id,
                    new_value={"type": evidence.type.value, "file_name": evidence.file_name, "file_size": evidence.file_size},
                    metadata={
                        "job_id": job.job_id,
                        "test_id": evidence.test_id,
                        "attempt_id": evidence.attempt_id,
                        "checksum": evidence.checksum,
                    },
                    job_id=job.job_id,
                )
            except Exception:
                pass

            return evidence

    # =========================================================================
    # Retrieval Operations
    # =========================================================================

    def get_evidence(self, evidence_id: str) -> Optional[Evidence]:
        """Retrieves an evidence record by ID."""
        with self._lock:
            return self.repo.get(evidence_id)

    def list_job_evidence(
        self,
        job_id: str,
        test_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
        evidence_type: Optional[Union[str, EvidenceType]] = None,
        include_archived: bool = False,
    ) -> List[Evidence]:
        """Retrieves evidence records associated with a Job with optional filters."""
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                raise JobNotFoundError(f"Test job '{job_id}' not found.")

            items = self.repo.get_by_job(job_id, include_archived=include_archived)

            if test_id:
                clean_test = str(test_id).strip().upper()
                items = [e for e in items if e.test_id and e.test_id.upper() == clean_test]

            if attempt_id:
                clean_att = str(attempt_id).strip()
                items = [e for e in items if e.attempt_id == clean_att]

            if evidence_type:
                target_type = EvidenceType.from_value(evidence_type)
                items = [e for e in items if e.type == target_type]

            return items

    def list_test_evidence(self, job_id: str, test_id: str, include_archived: bool = False) -> List[Evidence]:
        """Retrieves all evidence associated with a specific test on a job."""
        return self.list_job_evidence(job_id, test_id=test_id, include_archived=include_archived)

    def list_attempt_evidence(self, attempt_id: str, include_archived: bool = False) -> List[Evidence]:
        """Retrieves all evidence linked to a specific test attempt."""
        with self._lock:
            return self.repo.get_by_attempt(attempt_id, include_archived=include_archived)

    def download_evidence(
        self,
        evidence_id: str,
        requesting_job_id: Optional[str] = None,
    ) -> Tuple[bytes, str, str]:
        """
        Retrieves file content for download.
        Returns: (file_bytes, filename, mime_type)
        Enforces cross-job security verification.
        """
        with self._lock:
            evidence = self.repo.get(evidence_id)
            if not evidence:
                raise EvidenceNotFoundError(f"Evidence record '{evidence_id}' not found.")

            # Cross-job security check
            if requesting_job_id and evidence.job_id != requesting_job_id:
                raise EvidenceSecurityError(
                    f"Access denied: evidence '{evidence_id}' belongs to job '{evidence.job_id}', not '{requesting_job_id}'."
                )

            try:
                content = self.storage.read_file(evidence.storage_reference)
                return content, evidence.file_name, evidence.mime_type
            except StorageSecurityError as e:
                raise EvidenceSecurityError(str(e))
            except FileNotFoundError:
                raise EvidenceNotFoundError(f"Underlying storage file for evidence '{evidence_id}' is missing on disk.")

    # =========================================================================
    # Delete Operations (Soft-delete / Archive)
    # =========================================================================

    def delete_evidence(
        self,
        evidence_id: str,
        user_id: str = "SYSTEM",
        reason: str = "",
    ) -> Evidence:
        """
        Soft-deletes / archives an evidence record.
        Strictly prohibits deletion once job enters APPROVED or terminal state.
        """
        with self._lock:
            evidence = self.repo.get(evidence_id)
            if not evidence:
                raise EvidenceNotFoundError(f"Evidence record '{evidence_id}' not found.")

            job = self.jobs.get(evidence.job_id)
            if job and job.status in LOCKED_EVIDENCE_STATES:
                raise EvidenceWorkflowStateError(
                    f"Cannot delete evidence: associated job '{job.job_id}' is in '{job.status.value}' state. "
                    "Evidence is permanently locked for audit and certification integrity.",
                    error_code="EVIDENCE_LOCKED_AUDIT",
                )

            now_iso = datetime.now(timezone.utc).isoformat()
            evidence.status = EvidenceStatus.ARCHIVED
            evidence.updated_at = now_iso
            evidence.metadata["archived_by"] = user_id
            evidence.metadata["archive_reason"] = str(reason or "").strip()

            self.repo.save(evidence)

            # Emit statutory audit log
            try:
                from app.audit.service import AUDIT_SERVICE
                from app.audit.models import AuditAction, EntityType
                AUDIT_SERVICE.record_audit(
                    actor=str(user_id or "SYSTEM"),
                    action=AuditAction.EVIDENCE_DELETED_OR_ARCHIVED,
                    entity_type=EntityType.EVIDENCE,
                    entity_id=evidence.id,
                    old_value={"status": EvidenceStatus.ACTIVE.value},
                    new_value={"status": EvidenceStatus.ARCHIVED.value},
                    metadata={
                        "job_id": evidence.job_id,
                        "file_name": evidence.file_name,
                        "archive_reason": str(reason or ""),
                    },
                    job_id=evidence.job_id,
                )
            except Exception:
                pass

            return evidence


# Global singleton service
EVIDENCE_SERVICE = EvidenceService()
