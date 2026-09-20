"""
MetrIQ P5 Equipment & Test Standards Service
============================================
Person 5: Workflow + Evidence Engineer

Provides business logic for equipment management, test standard tracking,
calibration validity checks, and job associations.
"""

from datetime import date, datetime, timezone
import threading
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from app.jobs.models import TestJob
from app.jobs.repository import TEST_JOB_REPOSITORY, TestJobRepository
from app.workflow.service import JobNotFoundError
from .models import Equipment, EquipmentStatus, TestStandard, _parse_date
from .repository import (
    DuplicateSerialNumberError,
    EQUIPMENT_REPOSITORY,
    EquipmentRepository,
)


class EquipmentNotFoundError(KeyError):
    """Raised when an equipment item cannot be located."""
    pass


class StandardNotFoundError(KeyError):
    """Raised when a test standard cannot be located."""
    pass


class CalibrationExpiredError(ValueError):
    """Raised when an expired or out-of-service item is associated with a job."""

    def __init__(
        self,
        message: str,
        error_code: str = "CALIBRATION_EXPIRED",
        item_id: Optional[str] = None,
        serial_number: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.item_id = item_id
        self.serial_number = serial_number


class EquipmentValidationError(ValueError):
    """Raised when input validation for equipment or test standards fails."""

    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.field = field


class EquipmentService:
    """
    Central domain service for managing equipment, test standards,
    and their verified attachment to statutory test jobs.
    """

    def __init__(
        self,
        equipment_repository: Optional[EquipmentRepository] = None,
        job_repository: Optional[TestJobRepository] = None,
    ) -> None:
        self.repo = equipment_repository or EQUIPMENT_REPOSITORY
        self.jobs = job_repository or TEST_JOB_REPOSITORY
        self._lock = threading.RLock()

    # =========================================================================
    # Equipment Management
    # =========================================================================

    def create_equipment(self, data: Dict[str, Any]) -> Equipment:
        """Validates and registers a new equipment item."""
        with self._lock:
            # 1. Required field validations
            required = [
                "name",
                "type",
                "serial_number",
                "manufacturer",
                "model",
                "calibration_certificate",
                "calibration_date",
                "calibration_due_date",
            ]
            for field in required:
                val = data.get(field)
                if val is None or not str(val).strip():
                    raise EquipmentValidationError(f"Field '{field}' is required.", field=field)

            # 2. Date parsing validations
            cal_date = _parse_date(data.get("calibration_date"))
            if not cal_date:
                raise EquipmentValidationError("Invalid calibration_date format. Expected YYYY-MM-DD.", field="calibration_date")

            due_date = _parse_date(data.get("calibration_due_date"))
            if not due_date:
                raise EquipmentValidationError("Invalid calibration_due_date format. Expected YYYY-MM-DD.", field="calibration_due_date")

            if due_date < cal_date:
                raise EquipmentValidationError("calibration_due_date cannot be earlier than calibration_date.", field="calibration_due_date")

            # 3. Status validation
            stat = EquipmentStatus.from_value(data.get("status", "ACTIVE"))

            eq_id = str(data.get("id") or f"EQ-{uuid.uuid4().hex[:8].upper()}")

            equipment = Equipment(
                id=eq_id,
                name=str(data["name"]).strip(),
                type=str(data["type"]).strip(),
                serial_number=str(data["serial_number"]).strip(),
                manufacturer=str(data["manufacturer"]).strip(),
                model=str(data["model"]).strip(),
                calibration_certificate=str(data["calibration_certificate"]).strip(),
                calibration_date=cal_date.isoformat(),
                calibration_due_date=due_date.isoformat(),
                status=stat,
                notes=str(data.get("notes", "")),
            )
            saved_eq = self.repo.save_equipment(equipment)

            # Emit statutory audit log
            try:
                from app.audit.service import AUDIT_SERVICE
                from app.audit.models import AuditAction, EntityType
                AUDIT_SERVICE.record_audit(
                    actor="SYSTEM",
                    action=AuditAction.EQUIPMENT_CREATED,
                    entity_type=EntityType.EQUIPMENT,
                    entity_id=saved_eq.id,
                    new_value={"name": saved_eq.name, "serial_number": saved_eq.serial_number, "status": saved_eq.status.value},
                )
            except Exception:
                pass

            return saved_eq

    def get_equipment(self, equipment_id: str) -> Optional[Equipment]:
        """Retrieves equipment by ID."""
        return self.repo.get_equipment(equipment_id)

    def list_equipment(
        self,
        status: Optional[Union[str, EquipmentStatus]] = None,
        equipment_type: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Equipment]:
        """Lists equipment matching filters."""
        return self.repo.list_equipment(status=status, equipment_type=equipment_type, search=search)

    def update_equipment(self, equipment_id: str, updates: Dict[str, Any]) -> Equipment:
        """Updates fields of an existing equipment item."""
        with self._lock:
            eq = self.repo.get_equipment(equipment_id)
            if not eq:
                raise EquipmentNotFoundError(f"Equipment '{equipment_id}' not found.")

            if "name" in updates and updates["name"]:
                eq.name = str(updates["name"]).strip()
            if "type" in updates and updates["type"]:
                eq.type = str(updates["type"]).strip()
            if "serial_number" in updates and updates["serial_number"]:
                eq.serial_number = str(updates["serial_number"]).strip()
            if "manufacturer" in updates and updates["manufacturer"]:
                eq.manufacturer = str(updates["manufacturer"]).strip()
            if "model" in updates and updates["model"]:
                eq.model = str(updates["model"]).strip()
            if "calibration_certificate" in updates and updates["calibration_certificate"]:
                eq.calibration_certificate = str(updates["calibration_certificate"]).strip()
            if "notes" in updates:
                eq.notes = str(updates["notes"])

            if "calibration_date" in updates:
                cd = _parse_date(updates["calibration_date"])
                if not cd:
                    raise EquipmentValidationError("Invalid calibration_date format.", field="calibration_date")
                eq.calibration_date = cd.isoformat()

            if "calibration_due_date" in updates:
                cdd = _parse_date(updates["calibration_due_date"])
                if not cdd:
                    raise EquipmentValidationError("Invalid calibration_due_date format.", field="calibration_due_date")
                eq.calibration_due_date = cdd.isoformat()

            if "status" in updates and updates["status"]:
                eq.status = EquipmentStatus.from_value(updates["status"])

            return self.repo.save_equipment(eq)

    def change_equipment_status(self, equipment_id: str, new_status: Union[str, EquipmentStatus], reason: Optional[str] = None) -> Equipment:
        """Explicitly changes equipment status."""
        stat = EquipmentStatus.from_value(new_status)
        return self.update_equipment(equipment_id, {"status": stat.value, "notes": reason} if reason else {"status": stat.value})

    # =========================================================================
    # Test Standards Management
    # =========================================================================

    def create_test_standard(self, data: Dict[str, Any]) -> TestStandard:
        """Validates and registers a new test standard / reference weight."""
        with self._lock:
            # 1. Required field validations
            required = [
                "nominal_value",
                "unit",
                "accuracy_class",
                "serial_number",
                "certificate_number",
                "calibration_date",
                "expiry_date",
            ]
            for field in required:
                val = data.get(field)
                if val is None or (isinstance(val, str) and not val.strip()):
                    raise EquipmentValidationError(f"Field '{field}' is required.", field=field)

            # 2. Numeric nominal value validation
            try:
                nominal_val = float(data["nominal_value"])
                if nominal_val <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                raise EquipmentValidationError("Field 'nominal_value' must be a positive number.", field="nominal_value")

            # 3. Unit validation
            raw_unit = str(data["unit"]).strip().lower()
            valid_units = {"kg", "g", "mg", "t", "ct"}
            if raw_unit not in valid_units:
                raise EquipmentValidationError(f"Invalid unit '{raw_unit}'. Allowed units: {sorted(valid_units)}", field="unit")

            # 4. Date parsing validations
            cal_date = _parse_date(data.get("calibration_date"))
            if not cal_date:
                raise EquipmentValidationError("Invalid calibration_date format. Expected YYYY-MM-DD.", field="calibration_date")

            exp_date = _parse_date(data.get("expiry_date"))
            if not exp_date:
                raise EquipmentValidationError("Invalid expiry_date format. Expected YYYY-MM-DD.", field="expiry_date")

            if exp_date < cal_date:
                raise EquipmentValidationError("expiry_date cannot be earlier than calibration_date.", field="expiry_date")

            # 5. Status validation
            stat = EquipmentStatus.from_value(data.get("status", "ACTIVE"))

            std_id = str(data.get("id") or f"STD-{uuid.uuid4().hex[:8].upper()}")

            standard = TestStandard(
                id=std_id,
                nominal_value=nominal_val,
                unit=raw_unit,
                accuracy_class=str(data["accuracy_class"]).strip().upper(),
                serial_number=str(data["serial_number"]).strip(),
                certificate_number=str(data["certificate_number"]).strip(),
                calibration_date=cal_date.isoformat(),
                expiry_date=exp_date.isoformat(),
                status=stat,
            )
            saved_std = self.repo.save_standard(standard)

            # Emit statutory audit log
            try:
                from app.audit.service import AUDIT_SERVICE
                from app.audit.models import AuditAction, EntityType
                AUDIT_SERVICE.record_audit(
                    actor="SYSTEM",
                    action=AuditAction.TEST_STANDARD_CREATED,
                    entity_type=EntityType.TEST_STANDARD,
                    entity_id=saved_std.id,
                    new_value={"nominal_value": saved_std.nominal_value, "unit": saved_std.unit, "serial_number": saved_std.serial_number},
                )
            except Exception:
                pass

            return saved_std

    def get_test_standard(self, standard_id: str) -> Optional[TestStandard]:
        """Retrieves test standard by ID."""
        return self.repo.get_standard(standard_id)

    def list_test_standards(
        self,
        status: Optional[Union[str, EquipmentStatus]] = None,
        accuracy_class: Optional[str] = None,
        unit: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[TestStandard]:
        """Lists test standards matching filters."""
        return self.repo.list_standards(status=status, accuracy_class=accuracy_class, unit=unit, search=search)

    def update_test_standard(self, standard_id: str, updates: Dict[str, Any]) -> TestStandard:
        """Updates fields of an existing test standard."""
        with self._lock:
            std = self.repo.get_standard(standard_id)
            if not std:
                raise StandardNotFoundError(f"Test standard '{standard_id}' not found.")

            if "nominal_value" in updates and updates["nominal_value"] is not None:
                try:
                    nv = float(updates["nominal_value"])
                    if nv <= 0:
                        raise ValueError
                    std.nominal_value = nv
                except (ValueError, TypeError):
                    raise EquipmentValidationError("Field 'nominal_value' must be a positive number.", field="nominal_value")

            if "unit" in updates and updates["unit"]:
                u = str(updates["unit"]).strip().lower()
                if u not in {"kg", "g", "mg", "t", "ct"}:
                    raise EquipmentValidationError(f"Invalid unit '{u}'.", field="unit")
                std.unit = u

            if "accuracy_class" in updates and updates["accuracy_class"]:
                std.accuracy_class = str(updates["accuracy_class"]).strip().upper()

            if "serial_number" in updates and updates["serial_number"]:
                std.serial_number = str(updates["serial_number"]).strip()

            if "certificate_number" in updates and updates["certificate_number"]:
                std.certificate_number = str(updates["certificate_number"]).strip()

            if "calibration_date" in updates:
                cd = _parse_date(updates["calibration_date"])
                if not cd:
                    raise EquipmentValidationError("Invalid calibration_date format.", field="calibration_date")
                std.calibration_date = cd.isoformat()

            if "expiry_date" in updates:
                ed = _parse_date(updates["expiry_date"])
                if not ed:
                    raise EquipmentValidationError("Invalid expiry_date format.", field="expiry_date")
                std.expiry_date = ed.isoformat()

            if "status" in updates and updates["status"]:
                std.status = EquipmentStatus.from_value(updates["status"])

            return self.repo.save_standard(std)

    def change_test_standard_status(self, standard_id: str, new_status: Union[str, EquipmentStatus]) -> TestStandard:
        """Explicitly changes test standard status."""
        stat = EquipmentStatus.from_value(new_status)
        return self.update_test_standard(standard_id, {"status": stat.value})

    # =========================================================================
    # Job Association & Calibration Validity
    # =========================================================================

    def associate_equipment_with_job(self, job_id: str, equipment_id: str) -> TestJob:
        """
        Associates an inspection equipment item with a TestJob after verifying calibration validity.
        Rejects association if equipment is EXPIRED, OUT_OF_SERVICE, or has past due date.
        """
        with self._lock:
            # 1. Load job
            job = self.jobs.get(str(job_id).strip())
            if not job:
                raise JobNotFoundError(f"Test job '{job_id}' not found.", job_id=job_id)

            # 2. Load equipment
            eq = self.repo.get_equipment(str(equipment_id).strip())
            if not eq:
                raise EquipmentNotFoundError(f"Equipment '{equipment_id}' not found.")

            # 3. Calibration validity gate
            usable, err_code, reason = eq.is_usable()
            if not usable:
                raise CalibrationExpiredError(
                    message=reason or f"Equipment '{eq.name}' (S/N: {eq.serial_number}) cannot be used.",
                    error_code=err_code or "CALIBRATION_EXPIRED",
                    item_id=eq.id,
                    serial_number=eq.serial_number,
                )

            # 4. Associate
            if eq.id not in job.equipment_ids:
                job.equipment_ids.append(eq.id)
                job.updated_at = datetime.now(timezone.utc).isoformat()
                self.jobs.save(job)

                # Emit statutory audit log
                try:
                    from app.audit.service import AUDIT_SERVICE
                    from app.audit.models import AuditAction, EntityType
                    AUDIT_SERVICE.record_audit(
                        actor="SYSTEM",
                        action=AuditAction.JOB_EQUIPMENT_ASSOCIATED,
                        entity_type=EntityType.EQUIPMENT,
                        entity_id=eq.id,
                        metadata={"job_id": job.job_id, "equipment_name": eq.name, "serial_number": eq.serial_number},
                        job_id=job.job_id,
                    )
                except Exception:
                    pass

            return job

    def associate_test_standard_with_job(self, job_id: str, standard_id: str) -> TestJob:
        """
        Associates a test standard / weight with a TestJob after verifying calibration validity.
        Rejects association if standard is EXPIRED, OUT_OF_SERVICE, or has past expiry date.
        """
        with self._lock:
            # 1. Load job
            job = self.jobs.get(str(job_id).strip())
            if not job:
                raise JobNotFoundError(f"Test job '{job_id}' not found.", job_id=job_id)

            # 2. Load standard
            std = self.repo.get_standard(str(standard_id).strip())
            if not std:
                raise StandardNotFoundError(f"Test standard '{standard_id}' not found.")

            # 3. Calibration validity gate
            usable, err_code, reason = std.is_usable()
            if not usable:
                raise CalibrationExpiredError(
                    message=reason or f"Test standard '{std.nominal_value} {std.unit}' (S/N: {std.serial_number}) cannot be used.",
                    error_code=err_code or "CALIBRATION_EXPIRED",
                    item_id=std.id,
                    serial_number=std.serial_number,
                )

            # 4. Associate
            if std.id not in job.test_standard_ids:
                job.test_standard_ids.append(std.id)
                job.updated_at = datetime.now(timezone.utc).isoformat()
                self.jobs.save(job)

                # Emit statutory audit log
                try:
                    from app.audit.service import AUDIT_SERVICE
                    from app.audit.models import AuditAction, EntityType
                    AUDIT_SERVICE.record_audit(
                        actor="SYSTEM",
                        action=AuditAction.JOB_STANDARD_ASSOCIATED,
                        entity_type=EntityType.TEST_STANDARD,
                        entity_id=std.id,
                        metadata={"job_id": job.job_id, "nominal_value": std.nominal_value, "unit": std.unit, "serial_number": std.serial_number},
                        job_id=job.job_id,
                    )
                except Exception:
                    pass

            return job

    def get_job_equipment(self, job_id: str) -> List[Equipment]:
        """Returns all Equipment items associated with a job."""
        job = self.jobs.get(str(job_id).strip())
        if not job:
            raise JobNotFoundError(f"Test job '{job_id}' not found.", job_id=job_id)
        return [self.repo.get_equipment(eid) for eid in job.equipment_ids if self.repo.get_equipment(eid)]

    def get_job_test_standards(self, job_id: str) -> List[TestStandard]:
        """Returns all TestStandard items associated with a job."""
        job = self.jobs.get(str(job_id).strip())
        if not job:
            raise JobNotFoundError(f"Test job '{job_id}' not found.", job_id=job_id)
        return [self.repo.get_standard(sid) for sid in job.test_standard_ids if self.repo.get_standard(sid)]


# Global singleton service
EQUIPMENT_SERVICE = EquipmentService()
