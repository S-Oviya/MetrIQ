"""
MetrIQ P5 Environment Condition Models
======================================
Person 5: Workflow + Evidence Engineer

Defines domain entities, measurement validation rules, and physical range checks
for statutory ambient condition monitoring during NAWI test executions.
Under OIML R 76-1:2006 Clause 3.9 and Legal Metrology (General) Rules, 2011,
ambient temperature, relative humidity, and atmospheric pressure must be recorded
and verified during verification inspections.
"""

from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
import uuid


@dataclass
class EnvironmentCondition:
    """
    Physical ambient and environmental condition observation record.
    Supports statutory NAWI testing compliance tracking over time.
    """
    id: str
    job_id: str
    temperature: float            # In degrees Celsius (°C)
    humidity: float               # Relative humidity percentage (% RH, 0 to 100)
    atmospheric_pressure: float   # In hPa / mbar (positive number)
    location: str                 # Operational site / test bay description
    operator: str                 # Legal Metrology Inspector / GATC operator ID or name
    recorded_at: str              # ISO 8601 timestamp of measurement
    notes: str = ""               # Additional remarks or HVAC/weather observations
    created_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Converts EnvironmentCondition entity to serializable dict."""
        return {
            "id": self.id,
            "job_id": self.job_id,
            "temperature": self.temperature,
            "humidity": self.humidity,
            "atmospheric_pressure": self.atmospheric_pressure,
            "location": self.location,
            "operator": self.operator,
            "recorded_at": self.recorded_at,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnvironmentCondition":
        """Constructs an EnvironmentCondition entity from dictionary."""
        return cls(
            id=str(data.get("id") or f"ENV-{uuid.uuid4().hex[:8].upper()}"),
            job_id=str(data.get("job_id", "")),
            temperature=float(data.get("temperature", 0.0)),
            humidity=float(data.get("humidity", 0.0)),
            atmospheric_pressure=float(data.get("atmospheric_pressure", 0.0)),
            location=str(data.get("location", "")),
            operator=str(data.get("operator", "")),
            recorded_at=str(data.get("recorded_at") or datetime.now(timezone.utc).isoformat()),
            notes=str(data.get("notes", "")),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            updated_at=str(data.get("updated_at") or datetime.now(timezone.utc).isoformat()),
        )
