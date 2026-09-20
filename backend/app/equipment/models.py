"""
MetrIQ P5 Equipment & Test Standards Models
===========================================
Person 5: Workflow + Evidence Engineer

Defines domain entities, enums, and calibration-validity logic for:
1. Inspection Equipment (Thermometers, Barometers, Hygrometers, Standards)
2. Test Standards / Reference Weights (OIML R 111 class weights)
"""

from dataclasses import dataclass, field as dc_field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from app.regulatory.models import MassUnit


class EquipmentStatus(str, Enum):
    """Operational and calibration validity status for equipment and test weights."""
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"

    @classmethod
    def from_value(cls, val: Any) -> "EquipmentStatus":
        if isinstance(val, cls):
            return val
        if hasattr(val, "value"):
            val = val.value
        clean = str(val or "ACTIVE").strip().upper().replace(" ", "_").replace("-", "_")
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        # Common aliases
        if clean in ("INACTIVE", "DISABLED", "MAINTENANCE", "DECOMMISSIONED"):
            return cls.OUT_OF_SERVICE
        if clean in ("CALIBRATION_EXPIRED", "DUE"):
            return cls.EXPIRED
        raise ValueError(f"Invalid equipment status '{val}'. Permitted: {[m.value for m in cls]}")


def _parse_date(val: Any) -> Optional[date]:
    """Helper to reliably parse ISO strings or date objects."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if "T" in s:
        s = s.split("T")[0]
    return date.fromisoformat(s)


@dataclass
class Equipment:
    """
    Inspection and verification equipment entity.
    Tracks calibration certificates and statutory due dates.
    """
    id: str
    name: str
    type: str
    serial_number: str
    manufacturer: str
    model: str
    calibration_certificate: str
    calibration_date: str          # YYYY-MM-DD
    calibration_due_date: str      # YYYY-MM-DD
    status: EquipmentStatus = EquipmentStatus.ACTIVE
    notes: str = ""
    created_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def is_usable(self, reference_date: Optional[date] = None) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Determines whether the equipment item is legally and metrologically usable.
        Returns: (is_usable: bool, error_code: Optional[str], reason: Optional[str])
        """
        ref = reference_date or datetime.now(timezone.utc).date()

        # Status check
        if self.status == EquipmentStatus.OUT_OF_SERVICE:
            return (
                False,
                "EQUIPMENT_OUT_OF_SERVICE",
                f"Equipment '{self.name}' (S/N: {self.serial_number}) is marked OUT_OF_SERVICE.",
            )
        if self.status == EquipmentStatus.EXPIRED:
            return (
                False,
                "CALIBRATION_EXPIRED",
                f"Equipment '{self.name}' (S/N: {self.serial_number}) calibration status is EXPIRED.",
            )
        if self.status != EquipmentStatus.ACTIVE:
            return (
                False,
                f"EQUIPMENT_{self.status.value}",
                f"Equipment '{self.name}' is in non-active status '{self.status.value}'.",
            )

        # Due date check
        due = _parse_date(self.calibration_due_date)
        if due and due < ref:
            return (
                False,
                "CALIBRATION_EXPIRED",
                f"Equipment '{self.name}' (S/N: {self.serial_number}) calibration expired on {due.isoformat()}.",
            )

        return True, None, None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "serial_number": self.serial_number,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "calibration_certificate": self.calibration_certificate,
            "calibration_date": self.calibration_date,
            "calibration_due_date": self.calibration_due_date,
            "status": self.status.value,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Equipment":
        eq_id = str(data.get("id") or f"EQ-{uuid.uuid4().hex[:8].upper()}")
        stat = EquipmentStatus.from_value(data.get("status", "ACTIVE"))
        return cls(
            id=eq_id,
            name=str(data.get("name", "")),
            type=str(data.get("type", "")),
            serial_number=str(data.get("serial_number", "")),
            manufacturer=str(data.get("manufacturer", "")),
            model=str(data.get("model", "")),
            calibration_certificate=str(data.get("calibration_certificate", "")),
            calibration_date=str(data.get("calibration_date", "")),
            calibration_due_date=str(data.get("calibration_due_date", "")),
            status=stat,
            notes=str(data.get("notes", "")),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            updated_at=str(data.get("updated_at") or datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class TestStandard:
    """
    Test standard / reference weight entity.
    Tracks nominal mass, unit, accuracy class (E1..M3), and calibration expiry.
    """
    __test__ = False
    id: str
    nominal_value: float
    unit: str                      # e.g., kg, g, mg, t
    accuracy_class: str            # e.g., E1, E2, F1, F2, M1, M2, M3
    serial_number: str
    certificate_number: str
    calibration_date: str          # YYYY-MM-DD
    expiry_date: str               # YYYY-MM-DD
    status: EquipmentStatus = EquipmentStatus.ACTIVE
    created_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def is_usable(self, reference_date: Optional[date] = None) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Determines whether the test standard is legally and metrologically usable.
        Returns: (is_usable: bool, error_code: Optional[str], reason: Optional[str])
        """
        ref = reference_date or datetime.now(timezone.utc).date()

        # Status check
        if self.status == EquipmentStatus.OUT_OF_SERVICE:
            return (
                False,
                "STANDARD_OUT_OF_SERVICE",
                f"Test standard '{self.nominal_value} {self.unit}' (S/N: {self.serial_number}) is marked OUT_OF_SERVICE.",
            )
        if self.status == EquipmentStatus.EXPIRED:
            return (
                False,
                "CALIBRATION_EXPIRED",
                f"Test standard '{self.nominal_value} {self.unit}' (S/N: {self.serial_number}) calibration status is EXPIRED.",
            )
        if self.status != EquipmentStatus.ACTIVE:
            return (
                False,
                f"STANDARD_{self.status.value}",
                f"Test standard '{self.nominal_value} {self.unit}' is in non-active status '{self.status.value}'.",
            )

        # Expiry date check
        exp = _parse_date(self.expiry_date)
        if exp and exp < ref:
            return (
                False,
                "CALIBRATION_EXPIRED",
                f"Test standard '{self.nominal_value} {self.unit}' (S/N: {self.serial_number}) calibration expired on {exp.isoformat()}.",
            )

        return True, None, None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "nominal_value": self.nominal_value,
            "unit": self.unit,
            "accuracy_class": self.accuracy_class,
            "serial_number": self.serial_number,
            "certificate_number": self.certificate_number,
            "calibration_date": self.calibration_date,
            "expiry_date": self.expiry_date,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestStandard":
        std_id = str(data.get("id") or f"STD-{uuid.uuid4().hex[:8].upper()}")
        stat = EquipmentStatus.from_value(data.get("status", "ACTIVE"))
        return cls(
            id=std_id,
            nominal_value=float(data.get("nominal_value", 0.0)),
            unit=str(data.get("unit", "kg")),
            accuracy_class=str(data.get("accuracy_class", "M1")),
            serial_number=str(data.get("serial_number", "")),
            certificate_number=str(data.get("certificate_number", "")),
            calibration_date=str(data.get("calibration_date", "")),
            expiry_date=str(data.get("expiry_date", "")),
            status=stat,
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            updated_at=str(data.get("updated_at") or datetime.now(timezone.utc).isoformat()),
        )
