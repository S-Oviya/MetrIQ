"""
MetrIQ Instrument Models — Person 3 (Job / Instrument Engineer)
===============================================================
Defines comprehensive data structures for Non-Automatic Weighing Instruments (NAWI)
under the Legal Metrology Act, 2009 and OIML R 76-1:2006.

Captures all metrological characteristics, physical construction, auxiliary devices,
customer location, and lifecycle status.
"""

from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

# Import canonical enums from Person 2 (strictly preserved without duplication)
from app.regulatory.models import AccuracyClass, MassUnit


def parse_mass_unit(val: Any) -> MassUnit:
    """Parses and normalizes MassUnit from string, symbol, or enum."""
    if isinstance(val, MassUnit):
        return val
    clean = str(val or "kg").strip().lower()
    for m in MassUnit:
        if m.value == clean or m.name.lower() == clean:
            return m
    return MassUnit.KG


class InstrumentType(str, Enum):
    """Statutory NAWI instrument classification categories."""
    ELECTRONIC_COUNTER_SCALE = "ELECTRONIC_COUNTER_SCALE"
    BENCH_SCALE = "BENCH_SCALE"
    PLATFORM_SCALE = "PLATFORM_SCALE"
    WEIGHBRIDGE = "WEIGHBRIDGE"
    CRANE_SCALE = "CRANE_SCALE"
    PRECISION_BALANCE = "PRECISION_BALANCE"
    ANALYTICAL_BALANCE = "ANALYTICAL_BALANCE"
    HOPPER_SCALE = "HOPPER_SCALE"
    CHECKWEIGHER = "CHECKWEIGHER"
    SUSPENDED_SCALE = "SUSPENDED_SCALE"
    PRICE_COMPUTING_SCALE = "PRICE_COMPUTING_SCALE"
    BABY_SCALE = "BABY_SCALE"
    PERSON_WEIGHER = "PERSON_WEIGHER"
    OTHER = "OTHER"

    @classmethod
    def from_value(cls, val: Any) -> "InstrumentType":
        if isinstance(val, cls):
            return val
        clean = str(val or "OTHER").strip().upper().replace(" ", "_").replace("-", "_")
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        return cls.OTHER


class InstrumentStatus(str, Enum):
    """Operational lifecycle state of a weighing instrument under Legal Metrology Rules."""
    REGISTERED = "REGISTERED"                       # Registered in MetrIQ inventory
    READY = "READY"                                 # Model approval linked / ready for testing
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED" # Stamping required (initial, post-repair, post-relocation)
    IN_VERIFICATION = "IN_VERIFICATION"             # Undergoing testing/verification job
    VERIFIED = "VERIFIED"                           # Passed test and stamped
    IN_SERVICE = "IN_SERVICE"                       # Operating legally in commercial trade
    RE_VERIFICATION_DUE = "RE_VERIFICATION_DUE"      # Approaching or past periodic re-stamping deadline
    REPAIR = "REPAIR"                               # Under repair / servicing
    POST_REPAIR_VERIFICATION = "POST_REPAIR_VERIFICATION" # Repaired, awaiting re-stamping
    DISMANTLED = "DISMANTLED"                       # Dismantled from site
    RELOCATED = "RELOCATED"                         # Relocated to new physical site
    REINSTALLED = "REINSTALLED"                     # Reassembled, pending re-stamping
    SUSPENDED = "SUSPENDED"                         # Prohibited by Legal Metrology Officer
    RETIRED = "RETIRED"                             # Permanently scrapped / retired (terminal)

    # Backward compatibility aliases
    ACTIVE = "ACTIVE"                               # Alias for IN_SERVICE
    PENDING_APPROVAL = "PENDING_APPROVAL"           # Alias for REGISTERED / READY
    REPAIR_REQUIRED = "REPAIR_REQUIRED"             # Alias for REPAIR
    DECOMMISSIONED = "DECOMMISSIONED"               # Alias for RETIRED

    @classmethod
    def from_value(cls, val: Any) -> "InstrumentStatus":
        if isinstance(val, cls):
            return val
        if hasattr(val, "value"):
            val = val.value
        clean = str(val or "ACTIVE").strip().upper().replace(" ", "_").replace("-", "_")
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        if clean in ("APPROVED", "APPROVED_READY"):
            return cls.READY
        if clean in ("IN_TRADE", "OPERATIONAL"):
            return cls.IN_SERVICE
        if clean in ("BROKEN", "MAINTENANCE"):
            return cls.REPAIR
        return cls.ACTIVE


class LifecycleEventType(str, Enum):
    """Statutory Legal Metrology workflow events."""
    REGISTRATION = "REGISTRATION"                                       # 1. Instrument registration
    MODEL_APPROVAL_ASSOCIATION = "MODEL_APPROVAL_ASSOCIATION"           # 2. Model approval association
    INITIAL_VERIFICATION = "INITIAL_VERIFICATION"                       # 3. Initial verification
    IN_SERVICE_USE = "IN_SERVICE_USE"                                   # 4. In-service use
    PERIODIC_RE_VERIFICATION = "PERIODIC_RE_VERIFICATION"               # 5. Periodic re-verification
    REPAIR = "REPAIR"                                                   # 6. Repair
    POST_REPAIR_VERIFICATION = "POST_REPAIR_VERIFICATION"               # 7. Post-repair re-verification
    DISMANTLING = "DISMANTLING"                                         # 8. Dismantling
    RELOCATION = "RELOCATION"                                           # 9. Relocation
    REINSTALLATION = "REINSTALLATION"                                   # 10. Reinstallation
    POST_RELOCATION_VERIFICATION = "POST_RELOCATION_VERIFICATION"       # 11. Post-relocation/reinstallation verification
    RETIREMENT = "RETIREMENT"                                           # 12. Retirement

    @classmethod
    def from_value(cls, val: Any) -> "LifecycleEventType":
        if isinstance(val, cls):
            return val
        if hasattr(val, "value"):
            val = val.value
        clean = str(val or "REGISTRATION").strip().upper().replace(" ", "_").replace("-", "_")
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        return cls.REGISTRATION


@dataclass
class InstrumentLifecycleEvent:
    """Immutable record of an instrument lifecycle transition event."""
    event_id: str
    instrument_id: str
    event_type: LifecycleEventType
    event_date: str                     # YYYY-MM-DD
    previous_status: InstrumentStatus
    new_status: InstrumentStatus
    related_job_id: Optional[str] = None
    notes: str = ""
    actor: str = "SYSTEM"
    timestamp: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = dc_field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "instrument_id": self.instrument_id,
            "event_type": self.event_type.value,
            "event_date": self.event_date,
            "previous_status": self.previous_status.value,
            "new_status": self.new_status.value,
            "related_job_id": self.related_job_id,
            "notes": self.notes,
            "actor": self.actor,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InstrumentLifecycleEvent":
        return cls(
            event_id=str(data.get("event_id") or f"EVT-{uuid.uuid4().hex[:8].upper()}"),
            instrument_id=str(data.get("instrument_id") or ""),
            event_type=LifecycleEventType.from_value(data.get("event_type")),
            event_date=str(data.get("event_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            previous_status=InstrumentStatus.from_value(data.get("previous_status")),
            new_status=InstrumentStatus.from_value(data.get("new_status")),
            related_job_id=data.get("related_job_id"),
            notes=str(data.get("notes") or ""),
            actor=str(data.get("actor") or data.get("user") or "SYSTEM"),
            timestamp=str(data.get("timestamp") or datetime.now(timezone.utc).isoformat()),
            metadata=dict(data.get("metadata") or {}),
        )



class IndicationType(str, Enum):
    """Display indication architecture."""
    DIGITAL = "DIGITAL"
    ANALOG = "ANALOG"
    NON_SELF_INDICATING = "NON_SELF_INDICATING"

    @classmethod
    def from_value(cls, val: Any) -> "IndicationType":
        if isinstance(val, cls):
            return val
        clean = str(val or "DIGITAL").strip().upper()
        if "DIGIT" in clean:
            return cls.DIGITAL
        if "ANALOG" in clean or "DIAL" in clean or "POINTER" in clean:
            return cls.ANALOG
        if "NON" in clean or "BEAM" in clean or "COUNTERPOISE" in clean:
            return cls.NON_SELF_INDICATING
        return cls.DIGITAL


class ZeroSettingType(str, Enum):
    """Zero-setting mechanism type per OIML R 76-1 Clause 4.5."""
    NON_AUTOMATIC = "NON_AUTOMATIC"
    SEMI_AUTOMATIC = "SEMI_AUTOMATIC"
    AUTOMATIC = "AUTOMATIC"
    INITIAL = "INITIAL"
    COMBINED = "COMBINED"
    NONE = "NONE"

    @classmethod
    def from_value(cls, val: Any) -> "ZeroSettingType":
        if isinstance(val, cls):
            return val
        clean = str(val or "SEMI_AUTOMATIC").strip().upper().replace(" ", "_").replace("-", "_")
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        return cls.SEMI_AUTOMATIC


class TareType(str, Enum):
    """Tare device classification per OIML R 76-1 Clause 4.6."""
    NONE = "NONE"
    SUBTRACTIVE = "SUBTRACTIVE"
    ADDITIVE = "ADDITIVE"
    TARE_BALANCING = "TARE_BALANCING"
    PRESET = "PRESET"

    @classmethod
    def from_value(cls, val: Any) -> "TareType":
        if isinstance(val, cls):
            return val
        clean = str(val or "SUBTRACTIVE").strip().upper().replace(" ", "_").replace("-", "_")
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        return cls.SUBTRACTIVE


class SealType(str, Enum):
    """Statutory physical and electronic seal formats."""
    LEAD_AND_WIRE = "LEAD_AND_WIRE"
    CRIMP_SEAL = "CRIMP_SEAL"
    TAMPER_EVIDENT_LABEL = "TAMPER_EVIDENT_LABEL"
    ELECTRONIC_AUDIT_TRAIL = "ELECTRONIC_AUDIT_TRAIL"
    SECURITY_COLLAR = "SECURITY_COLLAR"
    PASSCODE_PROTECTED = "PASSCODE_PROTECTED"


class SealStatus(str, Enum):
    """State of an inspection seal."""
    INTACT = "INTACT"
    BROKEN = "BROKEN"
    REPLACED = "REPLACED"
    MISSING = "MISSING"


class GraduationType(str, Enum):
    """Indication graduation format per OIML R 76-1 Clause 2.1."""
    GRADUATED = "GRADUATED"
    NON_GRADUATED = "NON_GRADUATED"
    MULTI_INTERVAL = "MULTI_INTERVAL"
    MULTI_RANGE = "MULTI_RANGE"

    @classmethod
    def from_value(cls, val: Any) -> "GraduationType":
        if isinstance(val, cls):
            return val
        clean = str(val or "GRADUATED").strip().upper().replace(" ", "_").replace("-", "_")
        for m in cls:
            if m.value == clean or m.name == clean:
                return m
        return cls.GRADUATED


class ApprovalStatus(str, Enum):
    """Statutory model approval status of the instrument."""
    APPROVED = "APPROVED"
    EXEMPTED = "EXEMPTED"
    PENDING = "PENDING"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    REVOKED = "REVOKED"

    @classmethod
    def from_value(cls, val: Any) -> "ApprovalStatus":
        if isinstance(val, cls):
            return val
        clean = str(val or "APPROVED").strip().upper().replace(" ", "_").replace("-", "_")
        for m in cls:
            if m.value == clean or m.name == clean:
                return m
        return cls.APPROVED


class UsageType(str, Enum):
    """Operational application domain of the weighing instrument."""
    COMMERCIAL_TRADE = "COMMERCIAL_TRADE"
    INDUSTRIAL = "INDUSTRIAL"
    LABORATORY_RESEARCH = "LABORATORY_RESEARCH"
    HEALTHCARE_MEDICAL = "HEALTHCARE_MEDICAL"
    LAW_ENFORCEMENT = "LAW_ENFORCEMENT"
    POSTAL = "POSTAL"
    AGRICULTURAL = "AGRICULTURAL"
    MINING_BULK = "MINING_BULK"
    OTHER = "OTHER"

    @classmethod
    def from_value(cls, val: Any) -> "UsageType":
        if isinstance(val, cls):
            return val
        clean = str(val or "COMMERCIAL_TRADE").strip().upper().replace(" ", "_").replace("-", "_")
        for m in cls:
            if m.value == clean or m.name == clean:
                return m
        return cls.COMMERCIAL_TRADE


class TransactionUsage(str, Enum):
    """Specific legal purpose: commercial transaction vs consumer protection vs statutory levies."""
    COMMERCIAL_TRANSACTION = "COMMERCIAL_TRANSACTION"
    CONSUMER_PROTECTION = "CONSUMER_PROTECTION"
    TAXATION_LEVIES = "TAXATION_LEVIES"
    MEDICAL_DIAGNOSIS = "MEDICAL_DIAGNOSIS"
    LAW_ENFORCEMENT_MEASUREMENT = "LAW_ENFORCEMENT_MEASUREMENT"
    INTERNAL_QUALITY_CONTROL = "INTERNAL_QUALITY_CONTROL"

    @classmethod
    def from_value(cls, val: Any) -> "TransactionUsage":
        if isinstance(val, cls):
            return val
        clean = str(val or "COMMERCIAL_TRANSACTION").strip().upper().replace(" ", "_").replace("-", "_")
        for m in cls:
            if m.value == clean or m.name == clean:
                return m
        return cls.COMMERCIAL_TRANSACTION


class ConsumerImpact(str, Enum):
    """Public and consumer impact classification under Legal Metrology Act."""
    HIGH_DIRECT_RETAIL = "HIGH_DIRECT_RETAIL"
    MEDIUM_COMMERCIAL = "MEDIUM_COMMERCIAL"
    LOW_INTERNAL = "LOW_INTERNAL"
    CRITICAL_HEALTHCARE = "CRITICAL_HEALTHCARE"

    @classmethod
    def from_value(cls, val: Any) -> "ConsumerImpact":
        if isinstance(val, cls):
            return val
        clean = str(val or "HIGH_DIRECT_RETAIL").strip().upper().replace(" ", "_").replace("-", "_")
        for m in cls:
            if m.value == clean or m.name == clean:
                return m
        return cls.HIGH_DIRECT_RETAIL


class VerificationStatus(str, Enum):
    """Current statutory verification condition of the instrument."""
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNDER_INSPECTION = "UNDER_INSPECTION"
    DUE = "DUE"
    OVERDUE = "OVERDUE"
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"

    @classmethod
    def from_value(cls, val: Any) -> "VerificationStatus":
        if isinstance(val, cls):
            return val
        clean = str(val or "VERIFIED").strip().upper().replace(" ", "_").replace("-", "_")
        for m in cls:
            if m.value == clean or m.name == clean:
                return m
        return cls.VERIFIED


class VerificationReason(str, Enum):
    """Statutory rationale for instrument verification."""
    INITIAL_STAMPING = "INITIAL_STAMPING"
    PERIODIC_EXPIRY = "PERIODIC_EXPIRY"
    POST_REPAIR = "POST_REPAIR"
    POST_RELOCATION = "POST_RELOCATION"
    POST_REINSTALLATION = "POST_REINSTALLATION"
    ENFORCEMENT_ORDER = "ENFORCEMENT_ORDER"
    VOLUNTARY_REVERIFICATION = "VOLUNTARY_REVERIFICATION"
    MANUAL_REVIEW = "MANUAL_REVIEW"

    @classmethod
    def from_value(cls, val: Any) -> "VerificationReason":
        if isinstance(val, cls):
            return val
        clean = str(val or "PERIODIC_EXPIRY").strip().upper().replace(" ", "_").replace("-", "_")
        for m in cls:
            if m.value == clean or m.name == clean:
                return m
        return cls.PERIODIC_EXPIRY


@dataclass
class ManufacturerInfo:
    """Details of the manufacturer or importer under Legal Metrology Rules."""
    name: str
    country_of_origin: str = "INDIA"
    dealer_license_number: Optional[str] = None
    importer_name: Optional[str] = None
    importer_address: Optional[str] = None
    address: Optional[str] = None
    contact_email: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "country_of_origin": self.country_of_origin,
            "dealer_license_number": self.dealer_license_number,
            "importer_name": self.importer_name,
            "importer_address": self.importer_address,
            "address": self.address,
            "contact_email": self.contact_email,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["ManufacturerInfo"]:
        if not data:
            return None
        return cls(
            name=str(data.get("name") or data.get("manufacturer") or "Generic Manufacturer"),
            country_of_origin=str(data.get("country_of_origin", "INDIA")),
            dealer_license_number=data.get("dealer_license_number"),
            importer_name=data.get("importer_name"),
            importer_address=data.get("importer_address"),
            address=data.get("address"),
            contact_email=data.get("contact_email"),
        )


@dataclass
class PhysicalSeal:
    """Represents an official statutory verification or calibration seal."""
    seal_id: str
    seal_type: SealType
    seal_number: str
    location: str                   # e.g., "Calibration jumper cover", "Junction box", "Main casing"
    applied_date: str
    applied_by: str                 # Inspector / Verification Officer ID or name
    status: SealStatus = SealStatus.INTACT
    broken_date: Optional[str] = None
    broken_reason: Optional[str] = None
    remarks: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seal_id": self.seal_id,
            "seal_type": self.seal_type.value,
            "seal_number": self.seal_number,
            "location": self.location,
            "applied_date": self.applied_date,
            "applied_by": self.applied_by,
            "status": self.status.value,
            "broken_date": self.broken_date,
            "broken_reason": self.broken_reason,
            "remarks": self.remarks,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PhysicalSeal":
        return cls(
            seal_id=data.get("seal_id") or str(uuid.uuid4())[:8],
            seal_type=SealType(data.get("seal_type", "LEAD_AND_WIRE")),
            seal_number=str(data.get("seal_number", "")),
            location=str(data.get("location", "Main Casing")),
            applied_date=str(data.get("applied_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))),
            applied_by=str(data.get("applied_by", "")),
            status=SealStatus(data.get("status", "INTACT")),
            broken_date=data.get("broken_date"),
            broken_reason=data.get("broken_reason"),
            remarks=str(data.get("remarks", "")),
        )


@dataclass
class RangeDefinition:
    """Defines an individual sub-range for multi-range or multi-interval instruments."""
    range_index: int
    max_capacity: float
    min_capacity: float
    e: float
    d: float
    unit: MassUnit = MassUnit.KG

    @property
    def n(self) -> float:
        return self.max_capacity / self.e if self.e > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "range_index": self.range_index,
            "max_capacity": self.max_capacity,
            "min_capacity": self.min_capacity,
            "e": self.e,
            "d": self.d,
            "n": self.n,
            "unit": self.unit.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RangeDefinition":
        return cls(
            range_index=int(data.get("range_index", 1)),
            max_capacity=float(data.get("max_capacity") if data.get("max_capacity") is not None else data.get("Max", 0.0)),
            min_capacity=float(data.get("min_capacity") if data.get("min_capacity") is not None else data.get("Min", 0.0)),
            e=float(data.get("e", 1.0)),
            d=float(data.get("d", data.get("e", 1.0))),
            unit=parse_mass_unit(data.get("unit", "kg")),
        )


@dataclass
class SoftwareConfig:
    """Legally relevant software attributes per OIML R 76-1 Clause 5.5."""
    has_software: bool = True
    software_version: Optional[str] = None
    software_checksum: Optional[str] = None
    is_legally_relevant: bool = True
    menu_accessible: bool = True
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_software": self.has_software,
            "software_version": self.software_version,
            "software_checksum": self.software_checksum,
            "is_legally_relevant": self.is_legally_relevant,
            "menu_accessible": self.menu_accessible,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SoftwareConfig":
        return cls(
            has_software=bool(data.get("has_software", True)),
            software_version=data.get("software_version"),
            software_checksum=data.get("software_checksum"),
            is_legally_relevant=bool(data.get("is_legally_relevant", True)),
            menu_accessible=bool(data.get("menu_accessible", True)),
            notes=str(data.get("notes", "")),
        )


@dataclass
class CustomerLocation:
    """Deployment and installation location metadata."""
    customer_name: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    site_name: Optional[str] = None
    department: Optional[str] = None
    installation_environment: Optional[str] = None  # e.g., "RETAIL_COUNTER", "LAB_CLEANROOM", "FACTORY_FLOOR", "WEIGHBRIDGE_OUTDOOR"
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "customer_name": self.customer_name,
            "contact_person": self.contact_person,
            "phone": self.phone,
            "email": self.email,
            "site_name": self.site_name,
            "department": self.department,
            "installation_environment": self.installation_environment,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "district": self.district,
            "pincode": self.pincode,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "CustomerLocation":
        if not data:
            return cls(customer_name="Standard Client")
        return cls(
            customer_name=str(data.get("customer_name", "Standard Client")),
            contact_person=data.get("contact_person"),
            phone=data.get("phone"),
            email=data.get("email"),
            site_name=data.get("site_name"),
            department=data.get("department"),
            installation_environment=data.get("installation_environment"),
            address=data.get("address"),
            city=data.get("city"),
            state=data.get("state"),
            district=data.get("district"),
            pincode=data.get("pincode"),
            latitude=float(data["latitude"]) if data.get("latitude") is not None else None,
            longitude=float(data["longitude"]) if data.get("longitude") is not None else None,
        )


# Statutory Alias
InstrumentLocation = CustomerLocation


@dataclass
class Instrument:
    """
    Complete weighing instrument registry representation.
    Consolidates metrology parameters, physical configuration, model approval reference,
    usage classifications, verification history, and lifecycle status.
    """
    # 1. Identity
    instrument_id: str
    serial_number: str
    manufacturer: str
    model_name: str
    model_number: str = ""
    instrument_name: str = ""
    description: str = ""

    # 2. Classification Input
    accuracy_class: AccuracyClass = AccuracyClass.CLASS_III
    max_capacity: float = 15.0
    min_capacity: float = 0.1
    e: float = 0.005
    d: float = 0.005
    unit: MassUnit = MassUnit.KG
    instrument_type: InstrumentType = InstrumentType.ELECTRONIC_COUNTER_SCALE
    graduation_type: GraduationType = GraduationType.GRADUATED
    is_electronic: bool = True

    # 3. Indication & Auxiliary Devices
    indication_type: IndicationType = IndicationType.DIGITAL
    has_zero_setting: bool = True
    zero_setting_type: ZeroSettingType = ZeroSettingType.SEMI_AUTOMATIC
    zero_setting_range_percent: float = 4.0
    initial_zero_setting_range_percent: float = 20.0
    has_zero_tracking: bool = True
    has_tare: bool = True
    tare_type: TareType = TareType.SUBTRACTIVE
    max_tare: Optional[float] = None

    # 4. Advanced range configurations
    is_multi_range: bool = False
    is_multi_interval: bool = False
    ranges: List[RangeDefinition] = dc_field(default_factory=list)

    # 5. Software & Construction
    software: SoftwareConfig = dc_field(default_factory=SoftwareConfig)
    receptor_type: str = "PLATFORM"          # PLATFORM, HOOK, VESSEL, HOPPER, WEIGHBRIDGE_DECK
    manufacturing_year: Optional[int] = None
    temp_min_celsius: float = -10.0
    temp_max_celsius: float = 40.0

    # 6. Legal / Model Approval Information
    model_approval_number: Optional[str] = None
    model_approval_date: Optional[str] = None
    model_approval_mark: Optional[str] = None
    approval_status: ApprovalStatus = ApprovalStatus.APPROVED
    manufacturer_info: Optional[ManufacturerInfo] = None

    # 7. Usage & Consumer Impact
    usage_type: UsageType = UsageType.COMMERCIAL_TRADE
    transaction_usage: TransactionUsage = TransactionUsage.COMMERCIAL_TRANSACTION
    consumer_impact: ConsumerImpact = ConsumerImpact.HIGH_DIRECT_RETAIL
    location: CustomerLocation = dc_field(default_factory=lambda: CustomerLocation("Standard Client"))

    # 8. Verification & Statutory Seals
    status: InstrumentStatus = InstrumentStatus.ACTIVE
    verification_status: VerificationStatus = VerificationStatus.VERIFIED
    verification_officer: Optional[str] = None
    stamp_mark: Optional[str] = None
    gatc_code: Optional[str] = None
    last_verification_date: Optional[str] = None
    last_verification_certificate: Optional[str] = None
    next_re_verification_due: Optional[str] = None
    re_verification_interval_months: int = 12
    verification_reason: Optional[str] = None
    active_verification_job_id: Optional[str] = None
    last_verification_job_id: Optional[str] = None
    applicable_regulatory_profile_id: Optional[str] = None
    applicable_regulatory_version: Optional[str] = None
    manual_review_required: bool = False
    manual_review_reason: Optional[str] = None
    scheduling_metadata: Dict[str, Any] = dc_field(default_factory=dict)
    seals: List[PhysicalSeal] = dc_field(default_factory=list)

    # 9. Complete Lifecycle Dates
    manufactured_date: Optional[str] = None
    registered_date: Optional[str] = None
    installed_date: Optional[str] = None
    repair_date: Optional[str] = None
    dismantled_date: Optional[str] = None
    reinstalled_date: Optional[str] = None
    retired_date: Optional[str] = None

    # 10. Audit Timestamps, Notes & Lifecycle Events
    lifecycle_events: List[InstrumentLifecycleEvent] = dc_field(default_factory=list)
    created_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = dc_field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.model_number:
            self.model_number = self.model_name
        if not self.instrument_name:
            self.instrument_name = self.model_name
        if not self.registered_date and self.created_at:
            self.registered_date = self.created_at[:10]

    @property
    def next_verification_date(self) -> Optional[str]:
        """Synchronized alias for next_re_verification_due."""
        return self.next_re_verification_due

    @next_verification_date.setter
    def next_verification_date(self, val: Optional[str]) -> None:
        self.next_re_verification_due = val

    @property
    def n(self) -> float:
        """Calculates verification intervals n = Max / e."""
        return self.max_capacity / self.e if self.e > 0 else 0.0

    @property
    def is_software_controlled(self) -> bool:
        """Indicates whether the instrument is software-controlled."""
        return self.software.has_software if self.software else False

    def to_regulatory_payload(self) -> Dict[str, Any]:
        """
        Formats instrument specifications for Person 2's Regulatory Engine
        (e.g., validate_instrument_api or generate_test_plan_api).
        """
        payload: Dict[str, Any] = {
            "instrument_id": self.instrument_id,
            "serial_number": self.serial_number,
            "manufacturer": self.manufacturer,
            "model_name": self.model_name,
            "accuracy_class": self.accuracy_class.roman,
            "Max": self.max_capacity,
            "Min": self.min_capacity,
            "e": self.e,
            "d": self.d,
            "unit": self.unit.value,
            "instrument_type": self.instrument_type.value,
            "is_electronic": self.is_electronic,
            "indication_type": self.indication_type.value,
            "has_zero_setting": self.has_zero_setting,
            "zero_setting_type": self.zero_setting_type.value,
            "zero_setting_range_percent": self.zero_setting_range_percent,
            "initial_zero_setting_range_percent": self.initial_zero_setting_range_percent,
            "has_tare": self.has_tare,
            "tare_type": self.tare_type.value,
            "max_tare": self.max_tare,
            "is_multi_range": self.is_multi_range,
            "is_multi_interval": self.is_multi_interval,
            "has_software": self.is_software_controlled,
            "software_version": self.software.software_version if self.software else None,
            "software_checksum": self.software.software_checksum if self.software else None,
            "receptor_type": self.receptor_type,
            "model_approval_number": self.model_approval_number,
        }
        if self.ranges:
            payload["ranges"] = [r.to_dict() for r in self.ranges]
        return payload

    def to_dict(self) -> Dict[str, Any]:
        """Converts complete instrument entity to a serializable dictionary."""
        return {
            "instrument_id": self.instrument_id,
            "serial_number": self.serial_number,
            "manufacturer": self.manufacturer,
            "model_name": self.model_name,
            "model_number": self.model_number,
            "instrument_name": self.instrument_name,
            "description": self.description,
            "accuracy_class": self.accuracy_class.roman,
            "max_capacity": self.max_capacity,
            "min_capacity": self.min_capacity,
            "Max": self.max_capacity,
            "Min": self.min_capacity,
            "e": self.e,
            "d": self.d,
            "n": self.n,
            "unit": self.unit.value,
            "instrument_type": self.instrument_type.value,
            "graduation_type": self.graduation_type.value,
            "status": self.status.value,
            "is_electronic": self.is_electronic,
            "is_software_controlled": self.is_software_controlled,
            "model_approval_number": self.model_approval_number,
            "model_approval_date": self.model_approval_date,
            "model_approval_mark": self.model_approval_mark,
            "approval_status": self.approval_status.value,
            "manufacturer_info": self.manufacturer_info.to_dict() if self.manufacturer_info else None,
            "usage_type": self.usage_type.value,
            "transaction_usage": self.transaction_usage.value,
            "consumer_impact": self.consumer_impact.value,
            "indication_type": self.indication_type.value,
            "has_zero_setting": self.has_zero_setting,
            "zero_setting_type": self.zero_setting_type.value,
            "zero_setting_range_percent": self.zero_setting_range_percent,
            "initial_zero_setting_range_percent": self.initial_zero_setting_range_percent,
            "has_zero_tracking": self.has_zero_tracking,
            "has_tare": self.has_tare,
            "tare_type": self.tare_type.value,
            "max_tare": self.max_tare,
            "is_multi_range": self.is_multi_range,
            "is_multi_interval": self.is_multi_interval,
            "ranges": [r.to_dict() for r in self.ranges],
            "software": self.software.to_dict(),
            "receptor_type": self.receptor_type,
            "manufacturing_year": self.manufacturing_year,
            "temp_min_celsius": self.temp_min_celsius,
            "temp_max_celsius": self.temp_max_celsius,
            "location": self.location.to_dict(),
            "seals": [s.to_dict() for s in self.seals],
            "verification_status": self.verification_status.value,
            "verification_officer": self.verification_officer,
            "stamp_mark": self.stamp_mark,
            "gatc_code": self.gatc_code,
            "last_verification_date": self.last_verification_date,
            "last_verification_certificate": self.last_verification_certificate,
            "next_re_verification_due": self.next_re_verification_due,
            "next_verification_date": self.next_re_verification_due,
            "re_verification_interval_months": self.re_verification_interval_months,
            "verification_reason": self.verification_reason,
            "active_verification_job_id": self.active_verification_job_id,
            "last_verification_job_id": self.last_verification_job_id,
            "applicable_regulatory_profile_id": self.applicable_regulatory_profile_id,
            "applicable_regulatory_version": self.applicable_regulatory_version,
            "manual_review_required": self.manual_review_required,
            "manual_review_reason": self.manual_review_reason,
            "scheduling_metadata": self.scheduling_metadata,
            "manufactured_date": self.manufactured_date,
            "registered_date": self.registered_date,
            "installed_date": self.installed_date,
            "repair_date": self.repair_date,
            "dismantled_date": self.dismantled_date,
            "reinstalled_date": self.reinstalled_date,
            "retired_date": self.retired_date,
            "lifecycle_events": [e.to_dict() for e in self.lifecycle_events],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Instrument":
        """Creates an Instrument instance from raw or API payload dictionary."""
        inst_id = str(data.get("instrument_id") or data.get("id") or f"INST-{uuid.uuid4().hex[:8].upper()}")
        serial = str(data.get("serial_number") or data.get("serial") or f"SN-{uuid.uuid4().hex[:6].upper()}")
        mfr = str(data.get("manufacturer") or data.get("brand") or "Generic Manufacturer")
        model = str(data.get("model_name") or data.get("model_number") or data.get("model") or "Standard NAWI")
        model_num = str(data.get("model_number") or data.get("model_name") or model)
        inst_name = str(data.get("instrument_name") or data.get("name") or model)
        desc = str(data.get("description") or data.get("notes") or "")

        # Parse accuracy class
        raw_class = data.get("accuracy_class") or data.get("class") or "III"
        acc_class = AccuracyClass.from_string(str(raw_class))

        # Capacities and intervals
        max_cap = float(data.get("max_capacity") if data.get("max_capacity") is not None else data.get("Max", 15.0))
        min_cap = float(data.get("min_capacity") if data.get("min_capacity") is not None else data.get("Min", 0.1))
        e_val = float(data.get("e", 0.005))
        d_val = float(data.get("d", e_val))
        unit_val = parse_mass_unit(data.get("unit", "kg"))

        # Sub-ranges if multi-range / multi-interval
        ranges_list: List[RangeDefinition] = []
        if "ranges" in data and isinstance(data["ranges"], list):
            for r_data in data["ranges"]:
                ranges_list.append(RangeDefinition.from_dict(r_data))

        # Seals
        seals_list: List[PhysicalSeal] = []
        if "seals" in data and isinstance(data["seals"], list):
            for s_data in data["seals"]:
                seals_list.append(PhysicalSeal.from_dict(s_data))

        # Software
        soft_data = data.get("software")
        has_soft = bool(data.get("software_controlled", data.get("is_software_controlled", data.get("has_software", True))))
        software_obj = SoftwareConfig.from_dict(soft_data) if isinstance(soft_data, dict) else SoftwareConfig(
            has_software=has_soft,
            software_version=data.get("software_version"),
            software_checksum=data.get("software_checksum"),
        )

        # Manufacturer info
        mfr_info_data = data.get("manufacturer_info")
        mfr_info_obj = ManufacturerInfo.from_dict(mfr_info_data) if isinstance(mfr_info_data, dict) else None

        # Lifecycle events
        events_list: List[InstrumentLifecycleEvent] = []
        if "lifecycle_events" in data and isinstance(data["lifecycle_events"], list):
            for e_data in data["lifecycle_events"]:
                events_list.append(InstrumentLifecycleEvent.from_dict(e_data))

        return cls(
            instrument_id=inst_id,
            serial_number=serial,
            manufacturer=mfr,
            model_name=model,
            model_number=model_num,
            instrument_name=inst_name,
            description=desc,
            accuracy_class=acc_class,
            max_capacity=max_cap,
            min_capacity=min_cap,
            e=e_val,
            d=d_val,
            unit=unit_val,
            instrument_type=InstrumentType.from_value(data.get("instrument_type")),
            graduation_type=GraduationType.from_value(data.get("graduation_type")),
            status=InstrumentStatus.from_value(data.get("status")),
            model_approval_number=data.get("model_approval_number"),
            model_approval_date=data.get("model_approval_date"),
            model_approval_mark=data.get("model_approval_mark") or data.get("model_approval_reference"),
            approval_status=ApprovalStatus.from_value(data.get("approval_status")),
            manufacturer_info=mfr_info_obj,
            usage_type=UsageType.from_value(data.get("usage_type")),
            transaction_usage=TransactionUsage.from_value(data.get("transaction_usage") or data.get("transaction_type")),
            consumer_impact=ConsumerImpact.from_value(data.get("consumer_impact") or data.get("consumer_impact_classification")),
            indication_type=IndicationType.from_value(data.get("indication_type")),
            is_electronic=bool(data.get("electronic_status", data.get("is_electronic", True))),
            has_zero_setting=bool(data.get("has_zero_setting", True)),
            zero_setting_type=ZeroSettingType.from_value(data.get("zero_setting_type")),
            zero_setting_range_percent=float(data.get("zero_setting_range_percent", 4.0)),
            initial_zero_setting_range_percent=float(data.get("initial_zero_setting_range_percent", 20.0)),
            has_zero_tracking=bool(data.get("has_zero_tracking", True)),
            has_tare=bool(data.get("has_tare", True)),
            tare_type=TareType.from_value(data.get("tare_type")),
            max_tare=float(data["max_tare"]) if data.get("max_tare") is not None else None,
            is_multi_range=bool(data.get("multi_range_status", data.get("is_multi_range", False))),
            is_multi_interval=bool(data.get("multi_interval_status", data.get("is_multi_interval", False))),
            ranges=ranges_list,
            software=software_obj,
            receptor_type=str(data.get("receptor_type", "PLATFORM")),
            manufacturing_year=int(data["manufacturing_year"]) if data.get("manufacturing_year") else None,
            temp_min_celsius=float(data.get("temp_min_celsius", -10.0)),
            temp_max_celsius=float(data.get("temp_max_celsius", 40.0)),
            location=CustomerLocation.from_dict(data.get("location")),
            seals=seals_list,
            verification_status=VerificationStatus.from_value(data.get("verification_status")),
            verification_officer=data.get("verification_officer"),
            stamp_mark=data.get("stamp_mark") or data.get("stamp_mark_reference") or data.get("stamp_information"),
            gatc_code=data.get("gatc_code"),
            last_verification_date=data.get("last_verification_date"),
            last_verification_certificate=data.get("last_verification_certificate"),
            next_re_verification_due=data.get("next_re_verification_due") or data.get("next_verification_date"),
            re_verification_interval_months=int(data.get("re_verification_interval_months", 12)),
            verification_reason=data.get("verification_reason"),
            active_verification_job_id=data.get("active_verification_job_id"),
            last_verification_job_id=data.get("last_verification_job_id"),
            applicable_regulatory_profile_id=data.get("applicable_regulatory_profile_id"),
            applicable_regulatory_version=data.get("applicable_regulatory_version"),
            manual_review_required=bool(data.get("manual_review_required", False)),
            manual_review_reason=data.get("manual_review_reason"),
            scheduling_metadata=dict(data.get("scheduling_metadata") or {}),
            manufactured_date=data.get("manufactured_date") or data.get("manufacturing_date"),
            registered_date=data.get("registered_date"),
            installed_date=data.get("installed_date") or data.get("installation_date"),
            repair_date=data.get("repair_date") or data.get("last_repair_date"),
            dismantled_date=data.get("dismantled_date"),
            reinstalled_date=data.get("reinstalled_date") or data.get("relocated_date"),
            retired_date=data.get("retired_date") or data.get("decommissioned_date"),
            lifecycle_events=events_list,
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            updated_at=str(data.get("updated_at") or datetime.now(timezone.utc).isoformat()),
            notes=str(data.get("notes", "")),
        )
