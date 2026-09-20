"""
MetrIQ P5 Evidence & Attachment Models
======================================
Person 5: Workflow + Evidence Engineer

Defines domain entities, enums, and metadata structures for statutory evidence
attachments (photos of calibration seals, weight verification, test charts, certificates).
"""

from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import uuid


class EvidenceType(str, Enum):
    """
    Statutory evidence categories under Indian Legal Metrology framework:
    - PHOTO: Visual record of verification scales, load receptor, leveling, or test weights
    - VIDEO: Dynamic recording of test execution (e.g. rolling load, zero drift, tilt)
    - CALIBRATION_CERTIFICATE: Working standard or equipment verification certificate
    - INSTRUMENT_DOCUMENT: User manual, circuit diagram, or model approval gazette copy
    - TEST_OBSERVATION: Raw observation sheet, datalogger export, or printout
    - SIGNED_DOCUMENT: Verification stamping endorsement or inspector verification declaration
    - OTHER: Miscellaneous statutory metrological evidence
    """
    PHOTO = "PHOTO"
    VIDEO = "VIDEO"
    CALIBRATION_CERTIFICATE = "CALIBRATION_CERTIFICATE"
    INSTRUMENT_DOCUMENT = "INSTRUMENT_DOCUMENT"
    TEST_OBSERVATION = "TEST_OBSERVATION"
    SIGNED_DOCUMENT = "SIGNED_DOCUMENT"
    OTHER = "OTHER"

    @classmethod
    def from_value(cls, val: Any) -> "EvidenceType":
        if isinstance(val, cls):
            return val
        if hasattr(val, "value"):
            val = val.value
        clean = str(val or "OTHER").strip().upper().replace("-", "_").replace(" ", "_")
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        # Common aliases
        if clean in ("PICTURE", "IMAGE", "SNAPSHOT"):
            return cls.PHOTO
        if clean in ("CLIP", "RECORDING", "FOOTAGE"):
            return cls.VIDEO
        if clean in ("CERTIFICATE", "CAL_CERT", "WEIGHT_CERT"):
            return cls.CALIBRATION_CERTIFICATE
        if clean in ("MANUAL", "DOC", "DOCUMENT", "APPROVAL_DOC"):
            return cls.INSTRUMENT_DOCUMENT
        if clean in ("OBSERVATION", "DATA_SHEET", "PRINTOUT", "CHART"):
            return cls.TEST_OBSERVATION
        if clean in ("DECLARATION", "ENDORSEMENT", "SIGNATURE"):
            return cls.SIGNED_DOCUMENT
        raise ValueError(
            f"Invalid evidence type '{val}'. Permitted types: {[m.value for m in cls]}"
        )


class EvidenceStatus(str, Enum):
    """Retention status for audit and evidence lifecycle."""
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"

    @classmethod
    def from_value(cls, val: Any) -> "EvidenceStatus":
        if isinstance(val, cls):
            return val
        if hasattr(val, "value"):
            val = val.value
        clean = str(val or "ACTIVE").strip().upper()
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        return cls.ACTIVE


@dataclass
class Evidence:
    """
    Central Evidence entity tracking a statutory attachment.
    Traceable to a Job, optional Test, and optional Attempt.
    """
    __test__ = False  # Avoid pytest collection warning

    id: str
    job_id: str
    type: EvidenceType
    file_name: str
    storage_reference: str
    mime_type: str
    file_size: int
    checksum: str
    uploaded_by: str
    test_id: Optional[str] = None
    attempt_id: Optional[str] = None
    description: str = ""
    status: EvidenceStatus = EvidenceStatus.ACTIVE
    uploaded_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = dc_field(default_factory=dict)

    @property
    def evidence_id(self) -> str:
        """Alias for id conforming to existing report adapter expectations."""
        return self.id

    @property
    def evidence_type(self) -> str:
        """Convenience accessor for string type."""
        return self.type.value if isinstance(self.type, Enum) else str(self.type)

    @property
    def file_path(self) -> str:
        """Alias for storage_reference."""
        return self.storage_reference

    @property
    def hash(self) -> str:
        """Alias for checksum."""
        return self.checksum

    def to_dict(self) -> Dict[str, Any]:
        """Converts Evidence entity to dictionary representation."""
        return {
            "id": self.id,
            "evidence_id": self.id,
            "job_id": self.job_id,
            "test_id": self.test_id,
            "attempt_id": self.attempt_id,
            "type": self.type.value if isinstance(self.type, Enum) else str(self.type),
            "evidence_type": self.evidence_type,
            "file_name": self.file_name,
            "storage_reference": self.storage_reference,
            "file_path": self.storage_reference,
            "mime_type": self.mime_type,
            "file_size": self.file_size,
            "checksum": self.checksum,
            "hash": self.checksum,
            "uploaded_by": self.uploaded_by,
            "uploaded_at": self.uploaded_at,
            "description": self.description,
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Evidence":
        """Reconstructs Evidence entity from dictionary."""
        ev_type_raw = data.get("type") or data.get("evidence_type") or "OTHER"
        return cls(
            id=str(data.get("id") or data.get("evidence_id") or f"EVD-{uuid.uuid4().hex[:8].upper()}"),
            job_id=str(data.get("job_id", "")),
            test_id=data.get("test_id"),
            attempt_id=data.get("attempt_id"),
            type=EvidenceType.from_value(ev_type_raw),
            file_name=str(data.get("file_name", "unnamed_file")),
            storage_reference=str(data.get("storage_reference") or data.get("file_path") or ""),
            mime_type=str(data.get("mime_type", "application/octet-stream")),
            file_size=int(data.get("file_size", 0)),
            checksum=str(data.get("checksum") or data.get("hash") or ""),
            uploaded_by=str(data.get("uploaded_by") or data.get("operator") or "SYSTEM"),
            description=str(data.get("description", "")),
            status=EvidenceStatus.from_value(data.get("status", "ACTIVE")),
            uploaded_at=str(data.get("uploaded_at") or datetime.now(timezone.utc).isoformat()),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            updated_at=str(data.get("updated_at") or datetime.now(timezone.utc).isoformat()),
            metadata=dict(data.get("metadata", {})),
        )
