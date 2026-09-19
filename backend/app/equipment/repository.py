"""
MetrIQ P5 Equipment & Test Standards Repository
===============================================
Person 5: Workflow + Evidence Engineer

Thread-safe in-memory repository for inspection equipment and reference test standards.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional, Union

from .models import Equipment, EquipmentStatus, TestStandard


class DuplicateSerialNumberError(ValueError):
    """Raised when an item is registered with an existing serial number."""
    pass


class EquipmentRepository:
    """
    Thread-safe storage repository for equipment and test standards.
    Maintains primary keys and serial number uniqueness indexes.
    """

    def __init__(self) -> None:
        self._equipment: Dict[str, Equipment] = {}
        self._eq_serial_index: Dict[str, str] = {}  # serial_number.upper() -> equipment_id

        self._standards: Dict[str, TestStandard] = {}
        self._std_serial_index: Dict[str, str] = {}  # serial_number.upper() -> standard_id

        self._lock = threading.RLock()

    # =========================================================================
    # Equipment Operations
    # =========================================================================

    def save_equipment(self, item: Equipment) -> Equipment:
        """Saves or updates an Equipment entity."""
        with self._lock:
            sn_key = item.serial_number.strip().upper()
            existing_id = self._eq_serial_index.get(sn_key)
            if existing_id and existing_id != item.id:
                raise DuplicateSerialNumberError(
                    f"Equipment with serial number '{item.serial_number}' already exists (ID: {existing_id})."
                )

            item.updated_at = datetime.now(timezone.utc).isoformat()
            self._equipment[item.id] = item
            self._eq_serial_index[sn_key] = item.id
            return item

    def get_equipment(self, equipment_id: str) -> Optional[Equipment]:
        """Retrieves an equipment item by its unique ID."""
        with self._lock:
            return self._equipment.get(str(equipment_id).strip())

    def get_equipment_by_serial(self, serial_number: str) -> Optional[Equipment]:
        """Retrieves an equipment item by its serial number."""
        with self._lock:
            eq_id = self._eq_serial_index.get(str(serial_number).strip().upper())
            return self._equipment.get(eq_id) if eq_id else None

    def list_equipment(
        self,
        status: Optional[Union[str, EquipmentStatus]] = None,
        equipment_type: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Equipment]:
        """Queries equipment items with optional filtering."""
        with self._lock:
            results: List[Equipment] = []
            target_status = EquipmentStatus.from_value(status) if status else None
            search_clean = str(search or "").strip().lower()

            for item in self._equipment.values():
                if target_status and item.status != target_status:
                    continue
                if equipment_type and item.type.strip().lower() != equipment_type.strip().lower():
                    continue
                if search_clean:
                    haystack = f"{item.id} {item.name} {item.serial_number} {item.manufacturer} {item.model}".lower()
                    if search_clean not in haystack:
                        continue
                results.append(item)
            return results

    def delete_equipment(self, equipment_id: str) -> bool:
        """Deletes an equipment record."""
        with self._lock:
            eq_id = str(equipment_id).strip()
            item = self._equipment.pop(eq_id, None)
            if item:
                self._eq_serial_index.pop(item.serial_number.strip().upper(), None)
                return True
            return False

    # =========================================================================
    # Test Standards Operations
    # =========================================================================

    def save_standard(self, item: TestStandard) -> TestStandard:
        """Saves or updates a TestStandard entity."""
        with self._lock:
            sn_key = item.serial_number.strip().upper()
            existing_id = self._std_serial_index.get(sn_key)
            if existing_id and existing_id != item.id:
                raise DuplicateSerialNumberError(
                    f"Test standard with serial number '{item.serial_number}' already exists (ID: {existing_id})."
                )

            item.updated_at = datetime.now(timezone.utc).isoformat()
            self._standards[item.id] = item
            self._std_serial_index[sn_key] = item.id
            return item

    def get_standard(self, standard_id: str) -> Optional[TestStandard]:
        """Retrieves a test standard by its unique ID."""
        with self._lock:
            return self._standards.get(str(standard_id).strip())

    def get_standard_by_serial(self, serial_number: str) -> Optional[TestStandard]:
        """Retrieves a test standard by its serial number."""
        with self._lock:
            std_id = self._std_serial_index.get(str(serial_number).strip().upper())
            return self._standards.get(std_id) if std_id else None

    def list_standards(
        self,
        status: Optional[Union[str, EquipmentStatus]] = None,
        accuracy_class: Optional[str] = None,
        unit: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[TestStandard]:
        """Queries test standards with optional filtering."""
        with self._lock:
            results: List[TestStandard] = []
            target_status = EquipmentStatus.from_value(status) if status else None
            search_clean = str(search or "").strip().lower()

            for item in self._standards.values():
                if target_status and item.status != target_status:
                    continue
                if accuracy_class and item.accuracy_class.strip().upper() != accuracy_class.strip().upper():
                    continue
                if unit and item.unit.strip().lower() != unit.strip().lower():
                    continue
                if search_clean:
                    haystack = f"{item.id} {item.nominal_value} {item.unit} {item.serial_number} {item.certificate_number}".lower()
                    if search_clean not in haystack:
                        continue
                results.append(item)
            return results

    def delete_standard(self, standard_id: str) -> bool:
        """Deletes a test standard record."""
        with self._lock:
            std_id = str(standard_id).strip()
            item = self._standards.pop(std_id, None)
            if item:
                self._std_serial_index.pop(item.serial_number.strip().upper(), None)
                return True
            return False

    def clear(self) -> None:
        """Clears all records and indices for test isolation."""
        with self._lock:
            self._equipment.clear()
            self._eq_serial_index.clear()
            self._standards.clear()
            self._std_serial_index.clear()


# Global singleton repository
EQUIPMENT_REPOSITORY = EquipmentRepository()
