"""
MetrIQ Model Approval — Person 3 (Job / Instrument Engineer)
=============================================================
Implements statutory Model Approval (Pattern Approval) management, certificate tracking,
and metrological envelope verification under Section 22 of the Legal Metrology Act, 2009
and the Legal Metrology (Approval of Models) Rules, 2011.

Supports the complete model approval lifecycle:
DRAFT -> SUBMITTED -> UNDER_TESTING -> APPROVED -> EXPIRED / SUPERSEDED (or REJECTED)
and associates approved models with one or more physical instruments.
"""

from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from enum import Enum
import threading
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

# Consumes Person 2 exposed API without modifying Person 2 code
from app.regulatory.api import validate_instrument_api
from app.regulatory.models import AccuracyClass, MassUnit
from .models import Instrument, InstrumentType, parse_mass_unit


class ModelApprovalStatus(str, Enum):
    """Statutory lifecycle status of a model approval under Legal Metrology Rules, 2011."""
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_TESTING = "UNDER_TESTING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"
    # Compatibility & legacy aliases
    VALID = "VALID"         # Treated as APPROVED
    REVOKED = "REVOKED"
    SUSPENDED = "SUSPENDED"
    PENDING = "PENDING"     # Treated as SUBMITTED / UNDER_TESTING

    @classmethod
    def from_value(cls, val: Any) -> "ModelApprovalStatus":
        if isinstance(val, cls):
            return val
        if hasattr(val, "value"):
            val = val.value
        clean = str(val or "DRAFT").strip().upper()
        if "." in clean:
            clean = clean.split(".")[-1]
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        return cls.DRAFT


class ModelApprovalStateTransitionError(ValueError):
    """Raised when an invalid model approval lifecycle transition is attempted."""
    pass


LEGAL_MODEL_APPROVAL_TRANSITIONS: Dict[ModelApprovalStatus, List[ModelApprovalStatus]] = {
    ModelApprovalStatus.DRAFT: [
        ModelApprovalStatus.SUBMITTED,
        ModelApprovalStatus.REJECTED,
    ],
    ModelApprovalStatus.SUBMITTED: [
        ModelApprovalStatus.UNDER_TESTING,
        ModelApprovalStatus.DRAFT,     # Returned for corrections/amendments
        ModelApprovalStatus.REJECTED,
    ],
    ModelApprovalStatus.UNDER_TESTING: [
        ModelApprovalStatus.APPROVED,
        ModelApprovalStatus.REJECTED,
    ],
    ModelApprovalStatus.APPROVED: [
        ModelApprovalStatus.EXPIRED,
        ModelApprovalStatus.SUPERSEDED,
        ModelApprovalStatus.REVOKED,
        ModelApprovalStatus.SUSPENDED,
    ],
    ModelApprovalStatus.VALID: [
        ModelApprovalStatus.EXPIRED,
        ModelApprovalStatus.SUPERSEDED,
        ModelApprovalStatus.REVOKED,
        ModelApprovalStatus.SUSPENDED,
    ],
    ModelApprovalStatus.REJECTED: [],     # Terminal state
    ModelApprovalStatus.EXPIRED: [
        ModelApprovalStatus.SUPERSEDED,
    ],
    ModelApprovalStatus.SUPERSEDED: [],   # Terminal state
    ModelApprovalStatus.REVOKED: [],      # Terminal state
    ModelApprovalStatus.SUSPENDED: [
        ModelApprovalStatus.APPROVED,     # Suspension lifted
        ModelApprovalStatus.REVOKED,
    ],
    ModelApprovalStatus.PENDING: [
        ModelApprovalStatus.UNDER_TESTING,
        ModelApprovalStatus.APPROVED,
        ModelApprovalStatus.REJECTED,
    ],
}


@dataclass
class ModelApprovalRecord:
    """
    Statutory Model Approval Record and Certificate under Legal Metrology Rules, 2011.
    Tracks application, laboratory evaluation, approval credentials, and metrological bounds.
    """
    # 1. Identity & Application Reference
    approval_number: Optional[str] = None
    application_reference: Optional[str] = None
    model_number: str = ""
    manufacturer: str = ""
    model_name: str = ""
    instrument_type: InstrumentType = InstrumentType.OTHER

    # 2. Statutory Credentials (assigned once APPROVED)
    issuing_authority: str = "Director of Legal Metrology, Government of India / CSIR-NPL"
    issue_date: Optional[str] = None
    approval_date: Optional[str] = None
    approval_mark: Optional[str] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    status: ModelApprovalStatus = ModelApprovalStatus.DRAFT

    # 3. Metrological parameters (OIML R 76-1 / Indian Seventh Schedule)
    accuracy_class: AccuracyClass = AccuracyClass.CLASS_III
    accuracy_classes: List[AccuracyClass] = dc_field(default_factory=lambda: [AccuracyClass.CLASS_III])
    max_capacity: float = 15.0      # Max
    min_capacity: float = 0.1       # Min
    e: float = 0.005
    d: float = 0.005
    unit: MassUnit = MassUnit.KG

    # 4. Capacity Envelope in kg (for envelope checks & multi-capacity approvals)
    min_capacity_kg: float = 0.1
    max_capacity_kg: float = 50.0
    allowable_e_values_grams: Optional[List[float]] = None
    min_n: int = 100
    max_n: int = 10000

    # 5. Recognized Testing Laboratory & Documents
    testing_laboratory: Optional[str] = None
    testing_laboratory_reference: Optional[str] = None
    certificate_metadata: Dict[str, Any] = dc_field(default_factory=dict)
    rejection_reason: Optional[str] = None

    # 6. Construction & Hardware Modules
    approved_load_cell_models: List[str] = dc_field(default_factory=list)
    approved_indicator_models: List[str] = dc_field(default_factory=list)
    allows_multi_range: bool = False
    allows_multi_interval: bool = False
    allows_tare: bool = True

    # 7. Associated Instruments (1-to-many relationship)
    associated_instrument_ids: List[str] = dc_field(default_factory=list)

    # 8. Metadata
    notes: str = ""
    created_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if not self.application_reference:
            if self.approval_number:
                self.application_reference = f"APP-{self.approval_number.replace('/', '-')}"
            else:
                self.application_reference = f"APP-{uuid.uuid4().hex[:8].upper()}"

        if not self.model_number and self.model_name:
            self.model_number = self.model_name.split()[0]
        elif not self.model_name and self.model_number:
            self.model_name = self.model_number

        if self.issue_date and not self.approval_date:
            self.approval_date = self.issue_date
        elif self.approval_date and not self.issue_date:
            self.issue_date = self.approval_date

        if self.accuracy_class and not self.accuracy_classes:
            self.accuracy_classes = [self.accuracy_class]
        elif self.accuracy_classes and not self.accuracy_class:
            self.accuracy_class = self.accuracy_classes[0]

        # Synchronize min/max kg
        if self.max_capacity and (not self.max_capacity_kg or self.max_capacity_kg == 50.0):
            try:
                self.max_capacity_kg = MassUnit.convert(self.max_capacity, from_unit=self.unit, to_unit=MassUnit.KG)
            except Exception:
                self.max_capacity_kg = self.max_capacity

        if self.min_capacity and (not self.min_capacity_kg or self.min_capacity_kg == 0.1):
            try:
                self.min_capacity_kg = MassUnit.convert(self.min_capacity, from_unit=self.unit, to_unit=MassUnit.KG)
            except Exception:
                self.min_capacity_kg = self.min_capacity

    def is_valid_on_date(self, target_date: Optional[str] = None) -> bool:
        """Evaluates whether the certificate is legally active on target_date (YYYY-MM-DD)."""
        if self.status not in (ModelApprovalStatus.APPROVED, ModelApprovalStatus.VALID):
            return False
        eval_date = target_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.valid_from and eval_date < self.valid_from:
            return False
        if self.valid_until and eval_date > self.valid_until:
            return False
        return True

    def verify_instrument_envelope(self, instrument: Instrument) -> Tuple[bool, List[str]]:
        """
        Verifies whether an instrument's physical and metrological parameters
        fall strictly within the certificate's approved envelope.
        """
        reasons: List[str] = []

        # 1. Status and validity check
        if self.status not in (ModelApprovalStatus.APPROVED, ModelApprovalStatus.VALID):
            reasons.append(
                f"Model approval {self.approval_number or self.application_reference} is in {self.status.value} status (not APPROVED)."
            )
        elif not self.is_valid_on_date():
            reasons.append(
                f"Model approval certificate {self.approval_number} is {self.status.value} "
                f"(valid: {self.valid_from} to {self.valid_until})."
            )

        # 2. Manufacturer match
        if self.manufacturer.lower().strip() not in instrument.manufacturer.lower().strip() and \
           instrument.manufacturer.lower().strip() not in self.manufacturer.lower().strip():
            reasons.append(
                f"Manufacturer mismatch: Certificate authorizes '{self.manufacturer}', "
                f"but instrument declares '{instrument.manufacturer}'."
            )

        # 3. Accuracy Class match
        if instrument.accuracy_class not in self.accuracy_classes:
            allowed = [c.roman for c in self.accuracy_classes]
            reasons.append(
                f"Accuracy class mismatch: Certificate authorizes Class {allowed}, "
                f"but instrument declares Class {instrument.accuracy_class.roman}."
            )

        # 4. Capacity range match (in kg)
        max_kg = MassUnit.convert(instrument.max_capacity, from_unit=instrument.unit, to_unit=MassUnit.KG)
        if max_kg > self.max_capacity_kg + 1e-6:
            reasons.append(
                f"Capacity exceeds approved envelope: Maximum approved capacity is {self.max_capacity_kg} kg, "
                f"but instrument Max is {max_kg:.4f} kg ({instrument.max_capacity} {instrument.unit.value})."
            )

        min_kg = MassUnit.convert(instrument.min_capacity, from_unit=instrument.unit, to_unit=MassUnit.KG)
        if min_kg < self.min_capacity_kg - 1e-6:
            reasons.append(
                f"Minimum capacity below approved envelope: Minimum approved capacity is {self.min_capacity_kg} kg, "
                f"but instrument Min is {min_kg:.4f} kg ({instrument.min_capacity} {instrument.unit.value})."
            )

        # 5. Number of intervals n
        n_val = instrument.n
        if n_val < self.min_n - 1e-4 or n_val > self.max_n + 1e-4:
            reasons.append(
                f"Verification intervals n = {n_val:,.0f} outside approved range [{self.min_n:,}, {self.max_n:,}]."
            )

        # 6. Allowable e values (in grams) if restricted
        if self.allowable_e_values_grams:
            e_grams = MassUnit.convert(instrument.e, from_unit=instrument.unit, to_unit=MassUnit.G)
            matched = any(abs(e_grams - ae) < 1e-5 for ae in self.allowable_e_values_grams)
            if not matched:
                reasons.append(
                    f"Scale interval e = {e_grams} g not in approved list: {self.allowable_e_values_grams} g."
                )

        # 7. Multi-range / Multi-interval features
        if instrument.is_multi_range and not self.allows_multi_range:
            reasons.append("Instrument declares multi-range operation, but model approval certificate does not permit multi-range.")

        if instrument.is_multi_interval and not self.allows_multi_interval:
            reasons.append("Instrument declares multi-interval operation, but model approval certificate does not permit multi-interval.")

        is_valid = len(reasons) == 0
        return is_valid, reasons

    @property
    def approval_id(self) -> str:
        return self.approval_number or self.application_reference

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "application_reference": self.application_reference,
            "approval_number": self.approval_number,
            "model_number": self.model_number,
            "model_name": self.model_name,
            "manufacturer": self.manufacturer,
            "instrument_type": self.instrument_type.value if hasattr(self.instrument_type, "value") else str(self.instrument_type),
            "accuracy_class": self.accuracy_class.roman if hasattr(self.accuracy_class, "roman") else str(self.accuracy_class),
            "accuracy_classes": [c.roman if hasattr(c, "roman") else str(c) for c in self.accuracy_classes],
            "max_capacity": self.max_capacity,
            "min_capacity": self.min_capacity,
            "e": self.e,
            "d": self.d,
            "unit": self.unit.value if hasattr(self.unit, "value") else str(self.unit),
            "status": self.status.value,
            "issuing_authority": self.issuing_authority,
            "issue_date": self.issue_date,
            "approval_date": self.approval_date,
            "approval_mark": self.approval_mark,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "is_valid_currently": self.is_valid_on_date(),
            "testing_laboratory": self.testing_laboratory,
            "testing_laboratory_reference": self.testing_laboratory_reference,
            "certificate_metadata": self.certificate_metadata,
            "rejection_reason": self.rejection_reason,
            "associated_instrument_ids": list(self.associated_instrument_ids),
            "min_capacity_kg": self.min_capacity_kg,
            "max_capacity_kg": self.max_capacity_kg,
            "allowable_e_values_grams": self.allowable_e_values_grams,
            "min_n": self.min_n,
            "max_n": self.max_n,
            "approved_load_cell_models": self.approved_load_cell_models,
            "approved_indicator_models": self.approved_indicator_models,
            "allows_multi_range": self.allows_multi_range,
            "allows_multi_interval": self.allows_multi_interval,
            "allows_tare": self.allows_tare,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelApprovalRecord":
        raw_classes = data.get("accuracy_classes")
        if not raw_classes and data.get("accuracy_class"):
            raw_classes = [data["accuracy_class"]]
        elif not raw_classes:
            raw_classes = ["III"]

        classes: List[AccuracyClass] = []
        for c in raw_classes:
            if isinstance(c, AccuracyClass):
                classes.append(c)
            else:
                classes.append(AccuracyClass.from_string(str(c)))

        primary_class = classes[0] if classes else AccuracyClass.CLASS_III

        # Instrument type
        itype = InstrumentType.from_value(data.get("instrument_type"))

        # Unit
        munit = parse_mass_unit(data.get("unit", "kg"))

        # Status
        status_raw = data.get("status") or data.get("approval_status") or "DRAFT"
        mstatus = ModelApprovalStatus.from_value(status_raw)

        app_num = data.get("approval_number") or data.get("number")
        if app_num:
            app_num = str(app_num).strip().upper()
        else:
            app_num = None

        app_ref = data.get("application_reference") or data.get("application_number")
        if app_ref:
            app_ref = str(app_ref).strip().upper()
        elif app_num:
            app_ref = f"APP-{app_num.replace('/', '-')}"
        else:
            app_ref = f"APP-{uuid.uuid4().hex[:8].upper()}"

        max_val = float(data.get("max_capacity") if data.get("max_capacity") is not None else data.get("Max", 15.0))
        min_val = float(data.get("min_capacity") if data.get("min_capacity") is not None else data.get("Min", 0.1))
        e_val = float(data.get("e", 0.005))
        d_val = float(data.get("d", 0.005))

        # Convert to kg for bounds
        max_kg = float(data.get("max_capacity_kg", 0.0))
        if max_kg <= 0:
            try:
                max_kg = MassUnit.convert(max_val, from_unit=munit, to_unit=MassUnit.KG)
            except Exception:
                max_kg = max_val

        min_kg = float(data.get("min_capacity_kg", 0.0))
        if min_kg <= 0:
            try:
                min_kg = MassUnit.convert(min_val, from_unit=munit, to_unit=MassUnit.KG)
            except Exception:
                min_kg = min_val

        issue_d = data.get("issue_date") or data.get("approval_date")
        app_date = data.get("approval_date") or issue_d

        return cls(
            approval_number=app_num,
            application_reference=app_ref,
            model_number=str(data.get("model_number") or data.get("model_name") or ""),
            manufacturer=str(data.get("manufacturer", "")),
            model_name=str(data.get("model_name") or data.get("model_number") or ""),
            instrument_type=itype,
            issuing_authority=str(data.get("issuing_authority", "Director of Legal Metrology, Government of India / CSIR-NPL")),
            issue_date=str(issue_d) if issue_d else None,
            approval_date=str(app_date) if app_date else None,
            approval_mark=str(data["approval_mark"]) if data.get("approval_mark") else None,
            valid_from=str(data.get("valid_from") or app_date or "2024-01-01"),
            valid_until=str(data.get("valid_until", "2034-01-01")),
            status=mstatus,
            accuracy_class=primary_class,
            accuracy_classes=classes,
            max_capacity=max_val,
            min_capacity=min_val,
            e=e_val,
            d=d_val,
            unit=munit,
            min_capacity_kg=min_kg,
            max_capacity_kg=max_kg,
            allowable_e_values_grams=[float(x) for x in data["allowable_e_values_grams"]] if data.get("allowable_e_values_grams") else None,
            min_n=int(data.get("min_n", 100)),
            max_n=int(data.get("max_n", 10000)),
            testing_laboratory=str(data["testing_laboratory"]) if data.get("testing_laboratory") else None,
            testing_laboratory_reference=str(data["testing_laboratory_reference"]) if data.get("testing_laboratory_reference") else None,
            certificate_metadata=dict(data.get("certificate_metadata", {})),
            rejection_reason=str(data["rejection_reason"]) if data.get("rejection_reason") else None,
            approved_load_cell_models=list(data.get("approved_load_cell_models", [])),
            approved_indicator_models=list(data.get("approved_indicator_models", [])),
            allows_multi_range=bool(data.get("allows_multi_range", False)),
            allows_multi_interval=bool(data.get("allows_multi_interval", False)),
            allows_tare=bool(data.get("allows_tare", True)),
            associated_instrument_ids=list(data.get("associated_instrument_ids", [])),
            notes=str(data.get("notes", "")),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            updated_at=str(data.get("updated_at") or datetime.now(timezone.utc).isoformat()),
        )


# Backward-compatibility alias
ModelApprovalCertificate = ModelApprovalRecord


def validate_model_approval_fields(
    data: Dict[str, Any],
    target_status: Optional[ModelApprovalStatus] = None,
) -> Tuple[bool, List[str]]:
    """
    Validates required fields for a Model Approval record based on target status.
    """
    errors: List[str] = []

    # Common required fields across all statuses
    app_ref = str(data.get("application_reference") or data.get("application_number") or "").strip()
    # If approval_number is provided in legacy/seed data, application_reference can be derived
    if not app_ref and not data.get("approval_number"):
        errors.append("Model approval application reference is required.")

    mfr = str(data.get("manufacturer") or "").strip()
    if not mfr:
        errors.append("Manufacturer name is required.")

    m_num = str(data.get("model_number") or data.get("model_name") or "").strip()
    if not m_num:
        errors.append("Model number or model name is required.")

    # Accuracy class
    ac = data.get("accuracy_class") or data.get("accuracy_classes")
    if not ac:
        errors.append("Accuracy class is required.")

    # Capacity and interval numeric validity
    try:
        max_c = float(data.get("max_capacity") if data.get("max_capacity") is not None else data.get("Max", 0.0))
        if max_c <= 0:
            errors.append("Maximum capacity (Max) must be greater than zero.")
    except (TypeError, ValueError):
        errors.append("Maximum capacity (Max) must be a valid positive number.")
        max_c = 0.0

    try:
        min_c = float(data.get("min_capacity") if data.get("min_capacity") is not None else data.get("Min", 0.0))
        if min_c <= 0:
            errors.append("Minimum capacity (Min) must be greater than zero.")
        elif max_c > 0 and min_c > max_c:
            errors.append("Minimum capacity (Min) cannot exceed maximum capacity (Max).")
    except (TypeError, ValueError):
        errors.append("Minimum capacity (Min) must be a valid positive number.")

    try:
        e_val = float(data.get("e", 0.0))
        if e_val <= 0:
            errors.append("Verification scale interval (e) must be greater than zero.")
    except (TypeError, ValueError):
        errors.append("Verification scale interval (e) must be a valid positive number.")

    try:
        d_val = float(data.get("d", 0.0))
        if d_val <= 0:
            errors.append("Actual scale interval (d) must be greater than zero.")
    except (TypeError, ValueError):
        errors.append("Actual scale interval (d) must be a valid positive number.")

    # Determine effective status for prerequisite checks
    effective_status = target_status or ModelApprovalStatus.from_value(data.get("status") or data.get("approval_status") or "DRAFT")

    if effective_status == ModelApprovalStatus.UNDER_TESTING:
        lab = str(data.get("testing_laboratory") or "").strip()
        if not lab:
            errors.append("Recognized testing laboratory is required when model is UNDER_TESTING.")

    if effective_status in (ModelApprovalStatus.APPROVED, ModelApprovalStatus.VALID):
        app_num = str(data.get("approval_number") or "").strip()
        if not app_num:
            errors.append("Approval certificate number is required when model is APPROVED.")
        app_date = str(data.get("approval_date") or data.get("issue_date") or "").strip()
        if not app_date:
            errors.append("Approval date is required when model is APPROVED.")
        app_mark = str(data.get("approval_mark") or "").strip()
        if not app_mark:
            errors.append("Statutory approval mark is required when model is APPROVED.")

    if effective_status == ModelApprovalStatus.REJECTED:
        reason = str(data.get("rejection_reason") or data.get("reason") or "").strip()
        if not reason:
            errors.append("Rejection reason is required when status is REJECTED.")

    return len(errors) == 0, errors


def validate_model_approval_regulatory(data: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]], List[str]]:
    """
    Consumes Person 2's validate_instrument_api to check statutory metrological rules:
    - Step sequence e in {1, 2, 5} x 10^k
    - d <= e <= 10d
    - n = Max / e within statutory bounds for accuracy class
    - Min >= 20e (Class III/IIII) or 50e (Class II)
    Returns (valid, errors, warnings).
    """
    raw_class = data.get("accuracy_class")
    if hasattr(raw_class, "roman"):
        ac_str = raw_class.roman
    elif isinstance(raw_class, list) and raw_class:
        ac_str = raw_class[0].roman if hasattr(raw_class[0], "roman") else str(raw_class[0])
    else:
        ac_str = str(raw_class or "III")

    p2_payload = {
        "accuracy_class": ac_str,
        "Max": float(data.get("max_capacity") if data.get("max_capacity") is not None else data.get("Max", 15.0)),
        "Min": float(data.get("min_capacity") if data.get("min_capacity") is not None else data.get("Min", 0.1)),
        "e": float(data.get("e", 0.005)),
        "d": float(data.get("d", 0.005)),
        "unit": data.get("unit", "kg"),
    }
    res = validate_instrument_api(p2_payload)
    val_data = res.get("data", {})
    valid = val_data.get("valid", False)
    errors = val_data.get("errors", [])
    warnings = val_data.get("warnings", [])
    return valid, errors, warnings


class ModelApprovalRegistry:
    """
    Thread-safe registry for Model Approval Applications and Certificates
    under Section 22 of the Legal Metrology Act, 2009 and Model Approval Rules, 2011.
    """
    def __init__(self) -> None:
        self._records_by_app_ref: Dict[str, ModelApprovalRecord] = {}
        self._certificates: Dict[str, ModelApprovalRecord] = {}  # Indexed by approval_number
        self._lock = threading.RLock()
        self._load_seed_certificates()

    def _load_seed_certificates(self) -> None:
        """Populates representative Indian statutory model approval certificates."""
        # 1. Standard Retail Counter Scale (Class III, 15 kg / 35 kg)
        self.register(
            ModelApprovalRecord(
                approval_number="IND/09/2024/001",
                application_reference="APP-IND-2024-001",
                model_number="DS-215",
                model_name="DS-215 / DS-852 Series",
                manufacturer="Essae-Teraoka Ltd.",
                instrument_type=InstrumentType.ELECTRONIC_COUNTER_SCALE,
                issuing_authority="Director of Legal Metrology, GoI / CSIR-NPL",
                issue_date="2024-01-15",
                approval_date="2024-01-15",
                approval_mark="IND-LM-2024-001",
                valid_from="2024-01-15",
                valid_until="2034-01-14",
                status=ModelApprovalStatus.APPROVED,
                accuracy_class=AccuracyClass.CLASS_III,
                accuracy_classes=[AccuracyClass.CLASS_III],
                max_capacity=35.0,
                min_capacity=0.04,
                e=0.005,
                d=0.005,
                unit=MassUnit.KG,
                min_capacity_kg=0.04,
                max_capacity_kg=35.0,
                allowable_e_values_grams=[1.0, 2.0, 5.0],
                min_n=500,
                max_n=10000,
                testing_laboratory="CSIR-National Physical Laboratory (NPL), New Delhi",
                testing_laboratory_reference="NPL/MET/2024/TR-0881",
                approved_load_cell_models=["Teraoka LC-30", "Zemic L6D"],
                approved_indicator_models=["DI-160"],
                allows_multi_range=True,
                allows_multi_interval=False,
                allows_tare=True,
                associated_instrument_ids=["INST-RETAIL-001"],
                certificate_metadata={
                    "test_report_number": "NPL/MET/2024/TR-0881",
                    "gazette_notification": "G.S.R. 124(E)/2024",
                },
                notes="Approved for general retail and commercial grocery trade.",
            )
        )

        # 2. Precision Laboratory Balance (Class II, up to 6,000 g)
        cert_lab = ModelApprovalRecord(
            approval_number="IND/09/2023/045",
            application_reference="APP-IND-2023-045",
            model_number="ENTRIS-II-6000",
            model_name="Entris II / Practum Series",
            manufacturer="Sartorius India Pvt. Ltd.",
            instrument_type=InstrumentType.PRECISION_BALANCE,
            issuing_authority="Director of Legal Metrology, GoI / RRSL Bangalore",
            issue_date="2023-05-10",
            approval_date="2023-05-10",
            approval_mark="IND-LM-2023-045",
            valid_from="2023-05-10",
            valid_until="2033-05-09",
            status=ModelApprovalStatus.APPROVED,
            accuracy_class=AccuracyClass.CLASS_II,
            accuracy_classes=[AccuracyClass.CLASS_II],
            max_capacity=6000.0,
            min_capacity=5.0,
            e=0.1,
            d=0.1,
            unit=MassUnit.G,
            min_capacity_kg=0.005,
            max_capacity_kg=6.2,
            allowable_e_values_grams=[0.01, 0.02, 0.05, 0.1],
            min_n=1000,
            max_n=100000,
            testing_laboratory="Regional Reference Standards Laboratory (RRSL), Bangalore",
            testing_laboratory_reference="RRSL-BLR/TR/2023/502",
            approved_load_cell_models=["Monolithic EMFC Sensor M1"],
            approved_indicator_models=["Internal Digital LCD Display"],
            allows_multi_range=False,
            allows_multi_interval=False,
            allows_tare=True,
            associated_instrument_ids=["INST-LAB-002"],
            certificate_metadata={
                "test_report_number": "RRSL-BLR/TR/2023/502",
            },
            notes="Approved for chemical, pharmaceutical, and precious metal evaluation.",
        )
        self.register(cert_lab)
        # Also alias IND/09/2023/104 referenced by seed INST-LAB-002
        self._certificates["IND/09/2023/104"] = cert_lab

        # 3. Heavy Duty Weighbridge (Class III, up to 100 Tonnes)
        cert_wb = ModelApprovalRecord(
            approval_number="IND/09/2022/112",
            application_reference="APP-IND-2022-112",
            model_number="BRIDGEMONT-HD",
            model_name="BridgeMont HD Series",
            manufacturer="Avery India Ltd.",
            instrument_type=InstrumentType.WEIGHBRIDGE,
            issuing_authority="Director of Legal Metrology, GoI / CSIR-NPL",
            issue_date="2022-08-20",
            approval_date="2022-08-20",
            approval_mark="IND-LM-2022-112",
            valid_from="2022-08-20",
            valid_until="2032-08-19",
            status=ModelApprovalStatus.APPROVED,
            accuracy_class=AccuracyClass.CLASS_III,
            accuracy_classes=[AccuracyClass.CLASS_III, AccuracyClass.CLASS_IIII],
            max_capacity=100000.0,
            min_capacity=200.0,
            e=20.0,
            d=20.0,
            unit=MassUnit.KG,
            min_capacity_kg=200.0,
            max_capacity_kg=100000.0,
            allowable_e_values_grams=[10000.0, 20000.0, 50000.0],
            min_n=500,
            max_n=10000,
            testing_laboratory="CSIR-National Physical Laboratory (NPL), New Delhi",
            testing_laboratory_reference="NPL/MET/2022/TR-9941",
            approved_load_cell_models=["Avery T302", "Sensortronics 65016"],
            approved_indicator_models=["Avery E1205 Indicator"],
            allows_multi_range=True,
            allows_multi_interval=False,
            allows_tare=True,
            associated_instrument_ids=["INST-WEIGHBRIDGE-003"],
            certificate_metadata={
                "test_report_number": "NPL/MET/2022/TR-9941",
            },
            notes="Approved for commercial road vehicle weighbridge operations.",
        )
        self.register(cert_wb)
        # Also alias IND/09/2022/550 referenced by seed INST-WEIGHBRIDGE-003
        self._certificates["IND/09/2022/550"] = cert_wb

    def register(self, record: ModelApprovalRecord) -> ModelApprovalRecord:
        """Registers or updates a Model Approval record in the registry."""
        with self._lock:
            if record.application_reference:
                self._records_by_app_ref[record.application_reference.strip().upper()] = record
            if record.approval_number:
                self._certificates[record.approval_number.strip().upper()] = record
            return record

    def create_record(self, data: Dict[str, Any], skip_regulatory_val: bool = False) -> ModelApprovalRecord:
        """
        Creates and registers a new Model Approval record:
        1. Validates required fields for status.
        2. Validates uniqueness of application_reference and approval_number.
        3. Consumes Person 2's regulatory validation for metrological parameters.
        4. Saves and returns the record.
        """
        with self._lock:
            # 1. Field validation
            valid_fields, field_errs = validate_model_approval_fields(data)
            if not valid_fields:
                raise ValueError(f"Model approval validation failed: {'; '.join(field_errs)}")

            # 2. Check duplicates
            app_ref = str(data.get("application_reference") or data.get("application_number") or "").strip().upper()
            if app_ref and app_ref in self._records_by_app_ref:
                raise ValueError(f"Model approval application reference '{app_ref}' already exists in registry.")

            app_num = data.get("approval_number")
            if app_num:
                norm_app_num = str(app_num).strip().upper()
                if norm_app_num in self._certificates:
                    raise ValueError(f"Model approval certificate number '{norm_app_num}' is already issued to another model.")

            # 3. Regulatory validation via Person 2
            st_raw = data.get("status") or data.get("approval_status") or "DRAFT"
            status = ModelApprovalStatus.from_value(st_raw)
            if status != ModelApprovalStatus.DRAFT and not skip_regulatory_val:
                reg_valid, reg_errs, _ = validate_model_approval_regulatory(data)
                if not reg_valid:
                    err_msgs = [f"[{e.get('rule_id', 'ERROR')}] {e.get('message', 'Invalid metrology')}" for e in reg_errs]
                    raise ValueError(f"Metrological parameters violate Legal Metrology rules: {'; '.join(err_msgs)}")

            # 4. Instantiate and register
            record = ModelApprovalRecord.from_dict(data)
            return self.register(record)

    def update_record(self, reference: str, update_data: Dict[str, Any]) -> ModelApprovalRecord:
        """
        Updates an existing model approval record.
        Enforces state machine transitions, required fields, and Person 2 metrology re-validation.
        """
        with self._lock:
            existing = self.get_by_reference(reference)
            if not existing:
                raise KeyError(f"Model approval record with reference '{reference}' not found.")

            merged = existing.to_dict()
            for k, v in update_data.items():
                if k not in ("created_at",) and v is not None:
                    merged[k] = v

            # 1. State transition check
            new_status_raw = update_data.get("status") or update_data.get("approval_status")
            if new_status_raw:
                new_status = ModelApprovalStatus.from_value(new_status_raw)
                if new_status != existing.status:
                    allowed_next = LEGAL_MODEL_APPROVAL_TRANSITIONS.get(existing.status, [])
                    if new_status not in allowed_next:
                        raise ModelApprovalStateTransitionError(
                            f"Illegal state transition from {existing.status.value} to {new_status.value}. "
                            f"Allowed transitions from {existing.status.value} are: {[s.value for s in allowed_next]}"
                        )
                    merged["status"] = new_status.value

            # 2. Validate fields for the merged data
            valid_fields, field_errs = validate_model_approval_fields(merged)
            if not valid_fields:
                raise ValueError(f"Model approval validation failed: {'; '.join(field_errs)}")

            # 3. If approval number is newly added/changed, check uniqueness
            if update_data.get("approval_number"):
                new_num = str(update_data["approval_number"]).strip().upper()
                if new_num in self._certificates and self._certificates[new_num].application_reference != existing.application_reference:
                    raise ValueError(f"Approval certificate number '{new_num}' already issued to another model.")

            # 4. Re-validate metrology via Person 2 if core scale parameters changed
            metrology_keys = {"accuracy_class", "accuracy_classes", "Max", "max_capacity", "Min", "min_capacity", "e", "d", "unit"}
            if any(k in update_data for k in metrology_keys):
                reg_valid, reg_errs, _ = validate_model_approval_regulatory(merged)
                if not reg_valid:
                    err_msgs = [f"[{e.get('rule_id', 'ERROR')}] {e.get('message', 'Invalid metrology')}" for e in reg_errs]
                    raise ValueError(f"Updated metrological parameters violate Legal Metrology rules: {'; '.join(err_msgs)}")

            merged["updated_at"] = datetime.now(timezone.utc).isoformat()
            updated_record = ModelApprovalRecord.from_dict(merged)
            return self.register(updated_record)

    def transition_status(
        self,
        reference: str,
        to_status: Union[str, ModelApprovalStatus],
        **kwargs: Any,
    ) -> ModelApprovalRecord:
        """Transitions model approval lifecycle status with contextual updates."""
        update_payload: Dict[str, Any] = {"status": to_status}
        update_payload.update(kwargs)
        return self.update_record(reference, update_payload)

    def link_instrument(self, reference: str, instrument_id: str) -> ModelApprovalRecord:
        """Associates an instrument with this model approval."""
        with self._lock:
            record = self.get_by_reference(reference)
            if not record:
                raise KeyError(f"Model approval '{reference}' not found.")
            inst_clean = str(instrument_id).strip()
            if inst_clean and inst_clean not in record.associated_instrument_ids:
                record.associated_instrument_ids.append(inst_clean)
                record.updated_at = datetime.now(timezone.utc).isoformat()
            return record

    def get_associated_instruments(self, reference: str) -> List[str]:
        """Returns the list of instrument IDs associated with this model approval."""
        with self._lock:
            record = self.get_by_reference(reference)
            if not record:
                raise KeyError(f"Model approval '{reference}' not found.")
            return list(record.associated_instrument_ids)

    def get(self, approval_number: str) -> Optional[ModelApprovalRecord]:
        """Retrieves certificate by approval number (or falls back to application reference)."""
        with self._lock:
            key = str(approval_number).strip().upper()
            if key in self._certificates:
                return self._certificates[key]
            return self._records_by_app_ref.get(key)

    def get_by_application(self, application_reference: str) -> Optional[ModelApprovalRecord]:
        """Retrieves record by application reference."""
        with self._lock:
            key = str(application_reference).strip().upper()
            return self._records_by_app_ref.get(key)

    def get_by_reference(self, reference: str) -> Optional[ModelApprovalRecord]:
        """Retrieves record by approval number, application reference, or approval_id."""
        with self._lock:
            key = str(reference).strip().upper()
            if key in self._certificates:
                return self._certificates[key]
            if key in self._records_by_app_ref:
                return self._records_by_app_ref[key]
            for rec in self._records_by_app_ref.values():
                if rec.approval_id and rec.approval_id.strip().upper() == key:
                    return rec
                if rec.approval_number and rec.approval_number.strip().upper() == key:
                    return rec
            return None

    def exists(self, reference: str) -> bool:
        """Checks if a model approval is registered by number or application reference."""
        return self.get_by_reference(reference) is not None

    def list_all(
        self,
        manufacturer: Optional[str] = None,
        accuracy_class: Optional[Union[str, AccuracyClass]] = None,
        status: Optional[Union[str, ModelApprovalStatus]] = None,
        instrument_type: Optional[Union[str, InstrumentType]] = None,
        search: Optional[str] = None,
        valid_only: bool = False,
    ) -> List[ModelApprovalRecord]:
        """Queries model approvals matching multi-field criteria."""
        with self._lock:
            results: List[ModelApprovalRecord] = []
            target_class = (
                AccuracyClass.from_string(str(accuracy_class))
                if accuracy_class is not None
                else None
            )
            target_status = ModelApprovalStatus.from_value(status) if status is not None else None

            seen_refs = set()
            for record in self._records_by_app_ref.values():
                if record.application_reference in seen_refs:
                    continue
                seen_refs.add(record.application_reference)

                if valid_only and not record.is_valid_on_date():
                    continue
                if target_status and record.status != target_status:
                    continue
                if manufacturer and manufacturer.lower() not in record.manufacturer.lower():
                    continue
                if target_class and target_class not in record.accuracy_classes:
                    continue
                if instrument_type:
                    itype_str = instrument_type.value if hasattr(instrument_type, "value") else str(instrument_type)
                    rec_type_str = record.instrument_type.value if hasattr(record.instrument_type, "value") else str(record.instrument_type)
                    if itype_str.upper() != rec_type_str.upper():
                        continue
                if search:
                    s_low = search.lower().strip()
                    searchable = " ".join([
                        record.application_reference or "",
                        record.approval_number or "",
                        record.model_number or "",
                        record.model_name or "",
                        record.manufacturer or "",
                        record.testing_laboratory or "",
                        record.notes or "",
                    ]).lower()
                    if s_low not in searchable:
                        continue

                results.append(record)

            return results

    def verify_instrument(
        self,
        instrument: Instrument,
    ) -> Tuple[bool, Optional[ModelApprovalRecord], List[str]]:
        """
        Validates an instrument against its declared model approval number.
        Returns (is_compliant, cert_object, error_reasons).
        """
        if not instrument.model_approval_number:
            return True, None, ["No model approval number declared on instrument."]

        cert = self.get(instrument.model_approval_number)
        if not cert:
            return (
                False,
                None,
                [
                    f"Model approval certificate '{instrument.model_approval_number}' is not registered "
                    f"in the National Model Approval Registry under Section 22 of the Legal Metrology Act, 2009."
                ],
            )

        is_valid, reasons = cert.verify_instrument_envelope(instrument)
        return is_valid, cert, reasons


# Singleton instance for application runtime
MODEL_APPROVAL_REGISTRY = ModelApprovalRegistry()

