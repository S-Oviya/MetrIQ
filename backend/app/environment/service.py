"""
MetrIQ P5 Environment Condition Service
=======================================
Person 5: Workflow + Evidence Engineer

Provides business logic for ambient condition recording, validation,
chronological history tracking, and workflow state enforcement during NAWI testing.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional, Union
import uuid

from app.jobs.models import JobStatus, TestJob
from app.jobs.repository import TEST_JOB_REPOSITORY, TestJobRepository
from app.workflow.service import JobNotFoundError
from .models import EnvironmentCondition
from .repository import ENVIRONMENT_REPOSITORY, EnvironmentRepository


class EnvironmentValidationError(ValueError):
    """Raised when validation of environment condition data fails."""

    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.field = field


class EnvironmentNotFoundError(KeyError):
    """Raised when an environment condition record cannot be located."""
    pass


class EnvironmentStageError(ValueError):
    """Raised when environment condition recording is attempted in an invalid job lifecycle stage."""

    def __init__(self, message: str, error_code: str = "INVALID_JOB_STAGE"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class EnvironmentUpdateRestrictedError(ValueError):
    """Raised when updating an environment record is prohibited due to job status (e.g. REVIEW or APPROVED)."""

    def __init__(self, message: str, error_code: str = "ENVIRONMENT_UPDATE_RESTRICTED"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


# Lifecycle states that permanently prohibit recording new environment conditions
TERMINAL_JOB_STATES = {
    JobStatus.REPORT_GENERATED,
    JobStatus.CLOSED,
    JobStatus.CERTIFIED,
    JobStatus.CANCELLED,
}

# Lifecycle states that restrict modifying previously recorded environment observations
RESTRICTED_UPDATE_JOB_STATES = {
    JobStatus.REVIEW,
    JobStatus.UNDER_REVIEW,
    JobStatus.SUBMITTED_FOR_REVIEW,
    JobStatus.APPROVED,
    JobStatus.REPORT_GENERATED,
    JobStatus.CLOSED,
    JobStatus.CERTIFIED,
    JobStatus.CANCELLED,
}


class EnvironmentService:
    """
    Domain service for managing environmental observations during NAWI test jobs.
    Enforces physical range checks, legal metrology auditability, and workflow progression gates.
    """

    def __init__(
        self,
        repository: Optional[EnvironmentRepository] = None,
        job_repository: Optional[TestJobRepository] = None,
    ) -> None:
        self.repo = repository or ENVIRONMENT_REPOSITORY
        self.jobs = job_repository or TEST_JOB_REPOSITORY
        self._lock = threading.RLock()

    # =========================================================================
    # Validation Helpers
    # =========================================================================

    @staticmethod
    def _validate_float(val: Any, field_name: str) -> float:
        """Validates that a value is a valid numeric float (and not a boolean)."""
        if val is None or isinstance(val, bool):
            raise EnvironmentValidationError(
                f"Field '{field_name}' must be a valid numeric value.",
                field=field_name,
            )
        try:
            return float(val)
        except (ValueError, TypeError):
            raise EnvironmentValidationError(
                f"Field '{field_name}' must be a valid numeric value, got '{val}'.",
                field=field_name,
            )

    def _validate_temperature(self, val: Any) -> float:
        """Enforces realistic physical range for ambient temperature (-50°C to +100°C)."""
        temp = self._validate_float(val, "temperature")
        if not (-50.0 <= temp <= 100.0):
            raise EnvironmentValidationError(
                f"Temperature '{temp}' is outside realistic physical range (-50°C to 100°C).",
                field="temperature",
            )
        return temp

    def _validate_humidity(self, val: Any) -> float:
        """Enforces relative humidity percentage range (0% to 100%)."""
        hum = self._validate_float(val, "humidity")
        if not (0.0 <= hum <= 100.0):
            raise EnvironmentValidationError(
                f"Relative humidity '{hum}' must be between 0% and 100%.",
                field="humidity",
            )
        return hum

    def _validate_pressure(self, val: Any) -> float:
        """Enforces positive atmospheric pressure."""
        press = self._validate_float(val, "atmospheric_pressure")
        if press <= 0.0:
            raise EnvironmentValidationError(
                f"Atmospheric pressure '{press}' must be a positive number.",
                field="atmospheric_pressure",
            )
        return press

    @staticmethod
    def _validate_string(val: Any, field_name: str) -> str:
        """Enforces non-empty string."""
        if val is None or not str(val).strip():
            raise EnvironmentValidationError(
                f"Field '{field_name}' is required and cannot be empty.",
                field=field_name,
            )
        return str(val).strip()

    @staticmethod
    def _validate_timestamp(val: Any) -> str:
        """Validates ISO 8601 timestamp string."""
        if not val:
            return datetime.now(timezone.utc).isoformat()
        if isinstance(val, datetime):
            return val.isoformat()
        s = str(val).strip()
        try:
            # Handle ISO string with or without Z
            datetime.fromisoformat(s.replace("Z", "+00:00"))
            return s
        except Exception:
            raise EnvironmentValidationError(
                f"Field 'recorded_at' with value '{val}' is not a valid ISO 8601 format.",
                field="recorded_at",
            )

    # =========================================================================
    # Core Operations
    # =========================================================================

    def record_environment(self, job_id: str, data: Dict[str, Any]) -> EnvironmentCondition:
        """
        Validates and records a new ambient condition observation for a test job.
        Maintains chronological history on the job.
        """
        with self._lock:
            # 1. Verify job exists
            job = self.jobs.get(job_id)
            if not job:
                raise JobNotFoundError(f"Test job '{job_id}' not found.")

            # 2. Check job workflow state (cannot record if in terminal state)
            if job.status in TERMINAL_JOB_STATES or getattr(job.status, "is_terminal", False):
                raise EnvironmentStageError(
                    f"Cannot record environment conditions: job '{job_id}' is in terminal state '{job.status.value}'.",
                    error_code="JOB_TERMINAL_STATE",
                )

            # 3. Validate measurements and attributes
            temp = self._validate_temperature(data.get("temperature"))
            hum = self._validate_humidity(data.get("humidity"))
            press = self._validate_pressure(data.get("atmospheric_pressure"))
            loc = self._validate_string(data.get("location"), "location")
            operator = self._validate_string(data.get("operator"), "operator")
            recorded_at = self._validate_timestamp(data.get("recorded_at"))
            notes = str(data.get("notes") or "").strip()

            record_id = str(data.get("id") or f"ENV-{uuid.uuid4().hex[:8].upper()}")
            now_iso = datetime.now(timezone.utc).isoformat()

            record = EnvironmentCondition(
                id=record_id,
                job_id=job.job_id,
                temperature=temp,
                humidity=hum,
                atmospheric_pressure=press,
                location=loc,
                operator=operator,
                recorded_at=recorded_at,
                notes=notes,
                created_at=now_iso,
                updated_at=now_iso,
            )

            # 4. Save in repository
            self.repo.save(record)

            # 5. Append to job's environment_records history
            job.environment_records.append(record.to_dict())
            job.updated_at = now_iso
            self.jobs.save(job)

            # Emit statutory audit log
            try:
                from app.audit.service import AUDIT_SERVICE
                from app.audit.models import AuditAction, EntityType
                AUDIT_SERVICE.record_audit(
                    actor=str(operator or "SYSTEM"),
                    action=AuditAction.ENVIRONMENT_RECORDED,
                    entity_type=EntityType.ENVIRONMENT,
                    entity_id=record.id,
                    new_value={
                        "temperature": record.temperature,
                        "humidity": record.humidity,
                        "atmospheric_pressure": record.atmospheric_pressure,
                    },
                    metadata={"job_id": job.job_id, "location": record.location},
                    job_id=job.job_id,
                )
            except Exception:
                pass

            return record

    def get_latest_environment(self, job_id: str) -> Optional[EnvironmentCondition]:
        """Retrieves the latest environment condition record for a test job."""
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                raise JobNotFoundError(f"Test job '{job_id}' not found.")
            return self.repo.get_latest_by_job(job_id)

    def get_environment_history(self, job_id: str) -> List[EnvironmentCondition]:
        """Retrieves the chronological environment history for a test job."""
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                raise JobNotFoundError(f"Test job '{job_id}' not found.")
            return self.repo.get_by_job(job_id)

    def get_environment_by_id(self, record_id: str) -> Optional[EnvironmentCondition]:
        """Retrieves an environment condition record by its unique ID."""
        with self._lock:
            return self.repo.get(record_id)

    def update_environment(
        self,
        job_id: str,
        record_id: str,
        data: Dict[str, Any],
    ) -> EnvironmentCondition:
        """
        Updates an existing environment record, subject to workflow restrictions.
        Updates are rejected once the job has entered REVIEW, APPROVED, or terminal states.
        """
        with self._lock:
            # 1. Verify job exists
            job = self.jobs.get(job_id)
            if not job:
                raise JobNotFoundError(f"Test job '{job_id}' not found.")

            # 2. Verify record exists
            record = self.repo.get(record_id)
            if not record:
                raise EnvironmentNotFoundError(f"Environment record '{record_id}' not found.")

            # 3. Verify record belongs to this job
            if record.job_id != job_id:
                raise EnvironmentValidationError(
                    f"Record '{record_id}' belongs to job '{record.job_id}', not '{job_id}'.",
                    field="job_id",
                )

            # 4. Restrict updates once job enters REVIEW, APPROVED, or terminal states
            if job.status in RESTRICTED_UPDATE_JOB_STATES:
                raise EnvironmentUpdateRestrictedError(
                    f"Cannot update environment record: job '{job_id}' is in '{job.status.value}' state. "
                    "Modifications are restricted once a job enters REVIEW or APPROVED.",
                    error_code="ENVIRONMENT_UPDATE_RESTRICTED",
                )

            # 5. Validate and apply updates
            if "temperature" in data:
                record.temperature = self._validate_temperature(data["temperature"])
            if "humidity" in data:
                record.humidity = self._validate_humidity(data["humidity"])
            if "atmospheric_pressure" in data:
                record.atmospheric_pressure = self._validate_pressure(data["atmospheric_pressure"])
            if "location" in data:
                record.location = self._validate_string(data["location"], "location")
            if "operator" in data:
                record.operator = self._validate_string(data["operator"], "operator")
            if "recorded_at" in data:
                record.recorded_at = self._validate_timestamp(data["recorded_at"])
            if "notes" in data:
                record.notes = str(data["notes"] or "").strip()

            record.updated_at = datetime.now(timezone.utc).isoformat()

            # 6. Save in repository
            self.repo.save(record)

            # 7. Update in job's environment_records
            for i, rec_dict in enumerate(job.environment_records):
                if rec_dict.get("id") == record_id:
                    job.environment_records[i] = record.to_dict()
                    break
            job.updated_at = record.updated_at
            self.jobs.save(job)

            # Emit statutory audit log
            try:
                from app.audit.service import AUDIT_SERVICE
                from app.audit.models import AuditAction, EntityType
                AUDIT_SERVICE.record_audit(
                    actor=str(record.operator or "SYSTEM"),
                    action=AuditAction.ENVIRONMENT_UPDATED,
                    entity_type=EntityType.ENVIRONMENT,
                    entity_id=record.id,
                    new_value={
                        "temperature": record.temperature,
                        "humidity": record.humidity,
                        "atmospheric_pressure": record.atmospheric_pressure,
                    },
                    metadata={"job_id": job.job_id, "updated_fields": list(data.keys())},
                    job_id=job.job_id,
                )
            except Exception:
                pass

            return record


# Global singleton instance
ENVIRONMENT_SERVICE = EnvironmentService()
