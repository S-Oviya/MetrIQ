"""
MetrIQ P4 Test Engine & Calculations — Core Domain Models
=========================================================
Person 4: Rachitha (Test Engine + Calculations Lead)

Defines data structures and enumerations for test definitions,
raw observations, test runs, and test execution results covering
all statutory tests under OIML R 76-1:2006 and Indian Legal Metrology Rules, 2011.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


def _generate_id(prefix: str = "P4") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class Verdict(str, Enum):
    """Overall test outcome."""
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class TestType(str, Enum):
    """The ten statutory NAWI tests supported by MetrIQ P4."""
    __test__ = False
    WEIGHING_PERFORMANCE = "WEIGHING_PERFORMANCE"
    ECCENTRICITY = "ECCENTRICITY"
    REPEATABILITY = "REPEATABILITY"
    ZERO_RETURN = "ZERO_RETURN"
    CREEP = "CREEP"
    DISCRIMINATION = "DISCRIMINATION"
    TARE = "TARE"
    TEMPERATURE_EFFECT = "TEMPERATURE_EFFECT"
    CONSTRUCTION_EXAMINATION = "CONSTRUCTION_EXAMINATION"
    SOFTWARE_EXAMINATION = "SOFTWARE_EXAMINATION"

    @classmethod
    def from_value(cls, val: Any) -> "TestType":
        if isinstance(val, cls):
            return val
        clean = str(val).strip().upper().replace("-", "_").replace(" ", "_")
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        # Common aliases
        aliases = {
            "WEIGHING": cls.WEIGHING_PERFORMANCE,
            "ECCENTRIC": cls.ECCENTRICITY,
            "REPEAT": cls.REPEATABILITY,
            "ZERO": cls.ZERO_RETURN,
            "DIGITAL_DISCRIMINATION": cls.DISCRIMINATION,
            "TEMPERATURE": cls.TEMPERATURE_EFFECT,
            "CONSTRUCTION": cls.CONSTRUCTION_EXAMINATION,
            "SOFTWARE": cls.SOFTWARE_EXAMINATION,
        }
        if clean in aliases:
            return aliases[clean]
        raise ValueError(f"Unknown or unsupported TestType: {val}")


class ChecklistStatus(str, Enum):
    """Inspection result for non-numerical checklist examination items."""
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass
class ChecklistItem:
    """Individual inspection checklist item for Construction or Software tests."""
    item_id: str
    title: str
    clause: str
    status: ChecklistStatus = ChecklistStatus.COMPLIANT
    is_mandatory: bool = True
    comments: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "clause": self.clause,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "is_mandatory": self.is_mandatory,
            "comments": self.comments,
        }

    @classmethod
    def from_dict(cls, data: Union[Dict[str, Any], "ChecklistItem"]) -> "ChecklistItem":
        if isinstance(data, cls):
            return data
        raw_status = data.get("status", ChecklistStatus.COMPLIANT)
        status = ChecklistStatus(raw_status) if isinstance(raw_status, str) else raw_status
        return cls(
            item_id=str(data.get("item_id", "")),
            title=str(data.get("title", "")),
            clause=str(data.get("clause", "")),
            status=status,
            is_mandatory=bool(data.get("is_mandatory", True)),
            comments=data.get("comments"),
        )


@dataclass
class RawObservation:
    """
    A single captured measurement or observation in a test run.
    Supports numerical readings (load, indication, turning points, temperatures)
    and checklist items.
    """
    observation_id: str = field(default_factory=lambda: _generate_id("OBS"))
    step_number: int = 1
    applied_load: Optional[float] = None
    indicated_value: Optional[float] = None
    turning_point_delta_l: Optional[float] = None
    tare_load: Optional[float] = None
    position: Optional[str] = None           # e.g., "CENTER", "CORNER_1", "CORNER_2"
    temperature_c: Optional[float] = None
    time_seconds: Optional[float] = None      # e.g., 5, 300, 900, 1800 for creep
    extra_load: Optional[float] = None        # e.g., 1.4d for discrimination
    checklist_item: Optional[ChecklistItem] = None
    remarks: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "step_number": self.step_number,
            "applied_load": self.applied_load,
            "indicated_value": self.indicated_value,
            "turning_point_delta_l": self.turning_point_delta_l,
            "tare_load": self.tare_load,
            "position": self.position,
            "temperature_c": self.temperature_c,
            "time_seconds": self.time_seconds,
            "extra_load": self.extra_load,
            "checklist_item": self.checklist_item.to_dict() if self.checklist_item else None,
            "remarks": self.remarks,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RawObservation":
        chk = data.get("checklist_item")
        chk_item = ChecklistItem.from_dict(chk) if isinstance(chk, dict) else None
        return cls(
            observation_id=str(data.get("observation_id") or _generate_id("OBS")),
            step_number=int(data.get("step_number", 1)),
            applied_load=float(data["applied_load"]) if data.get("applied_load") is not None else None,
            indicated_value=float(data["indicated_value"]) if data.get("indicated_value") is not None else None,
            turning_point_delta_l=float(data["turning_point_delta_l"]) if data.get("turning_point_delta_l") is not None else None,
            tare_load=float(data["tare_load"]) if data.get("tare_load") is not None else None,
            position=data.get("position"),
            temperature_c=float(data["temperature_c"]) if data.get("temperature_c") is not None else None,
            time_seconds=float(data["time_seconds"]) if data.get("time_seconds") is not None else None,
            extra_load=float(data["extra_load"]) if data.get("extra_load") is not None else None,
            checklist_item=chk_item,
            remarks=data.get("remarks"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class TestDefinition:
    """Regulatory definition and specifications for a test."""
    __test__ = False
    test_type: TestType
    title: str
    standard_clause: str
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_type": self.test_type.value if isinstance(self.test_type, Enum) else self.test_type,
            "title": self.title,
            "standard_clause": self.standard_clause,
            "parameters": self.parameters,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestDefinition":
        return cls(
            test_type=TestType.from_value(data.get("test_type", TestType.WEIGHING_PERFORMANCE)),
            title=str(data.get("title", "")),
            standard_clause=str(data.get("standard_clause", "")),
            parameters=dict(data.get("parameters", {})),
        )


@dataclass
class TestRun:
    """
    A concrete execution event of a test on an instrument for a job,
    containing the raw observations recorded by the verification officer.
    """
    __test__ = False
    test_run_id: str = field(default_factory=lambda: _generate_id("RUN"))
    job_id: str = ""
    instrument_id: Optional[str] = None
    test_type: TestType = TestType.WEIGHING_PERFORMANCE
    test_definition: Optional[TestDefinition] = None
    observations: List[RawObservation] = field(default_factory=list)
    executed_at: str = field(default_factory=_current_timestamp)
    executed_by: Optional[str] = None
    environmental_conditions: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_run_id": self.test_run_id,
            "job_id": self.job_id,
            "instrument_id": self.instrument_id,
            "test_type": self.test_type.value if isinstance(self.test_type, Enum) else self.test_type,
            "test_definition": self.test_definition.to_dict() if self.test_definition else None,
            "observations": [o.to_dict() for o in self.observations],
            "executed_at": self.executed_at,
            "executed_by": self.executed_by,
            "environmental_conditions": self.environmental_conditions,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestRun":
        tdef = data.get("test_definition")
        test_definition = TestDefinition.from_dict(tdef) if isinstance(tdef, dict) else None
        raw_obs = data.get("observations", [])
        observations = [RawObservation.from_dict(o) if isinstance(o, dict) else o for o in raw_obs]
        return cls(
            test_run_id=str(data.get("test_run_id") or _generate_id("RUN")),
            job_id=str(data.get("job_id", "")),
            instrument_id=data.get("instrument_id"),
            test_type=TestType.from_value(data.get("test_type", TestType.WEIGHING_PERFORMANCE)),
            test_definition=test_definition,
            observations=observations,
            executed_at=data.get("executed_at") or _current_timestamp(),
            executed_by=data.get("executed_by"),
            environmental_conditions=dict(data.get("environmental_conditions", {})),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class TestExecutionResult:
    """
    Final calculated result of a test execution, containing PASS/FAIL verdict,
    evaluated limits, intermediate steps, and audit summary.
    """
    __test__ = False
    test_run_id: str
    test_type: TestType
    verdict: Verdict
    summary: str
    calculated_values: Dict[str, Any] = field(default_factory=dict)
    regulatory_limits: Dict[str, Any] = field(default_factory=dict)
    observations_evaluated: int = 0
    intermediate_results: List[Dict[str, Any]] = field(default_factory=list)
    standard_reference: str = ""
    timestamp: str = field(default_factory=_current_timestamp)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_run_id": self.test_run_id,
            "test_type": self.test_type.value if isinstance(self.test_type, Enum) else self.test_type,
            "verdict": self.verdict.value if isinstance(self.verdict, Enum) else self.verdict,
            "summary": self.summary,
            "calculated_values": self.calculated_values,
            "regulatory_limits": self.regulatory_limits,
            "observations_evaluated": self.observations_evaluated,
            "intermediate_results": self.intermediate_results,
            "standard_reference": self.standard_reference,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }
