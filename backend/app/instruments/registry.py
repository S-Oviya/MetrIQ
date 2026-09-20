"""
MetrIQ Instrument Registry Repository — Person 3 (Job / Instrument Engineer)
===========================================================================
Provides high-performance, thread-safe persistence and search capabilities
for Non-Automatic Weighing Instruments.
"""

from datetime import datetime, timezone
import json
import threading
from typing import Any, Dict, List, Optional, Union

from app.database.connection import db_session, init_db
from app.regulatory.models import AccuracyClass, MassUnit
from .models import (
    ApprovalStatus,
    ConsumerImpact,
    CustomerLocation,
    GraduationType,
    IndicationType,
    Instrument,
    InstrumentStatus,
    InstrumentType,
    ManufacturerInfo,
    PhysicalSeal,
    SealStatus,
    SealType,
    SoftwareConfig,
    TareType,
    TransactionUsage,
    UsageType,
    VerificationStatus,
    ZeroSettingType,
)


class _InstrumentsDict(dict):
    """
    Dict subclass that transparently synchronizes item assignments and clears
    with the underlying SQLite database.
    """

    def __init__(self, registry: "InstrumentRegistry"):
        super().__init__()
        self._registry = registry

    def clear(self) -> None:
        super().clear()
        if getattr(self._registry, "_persistent", False):
            try:
                with db_session() as conn:
                    conn.execute("DELETE FROM instruments")
            except Exception:
                pass

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        if getattr(self._registry, "_persistent", False):
            try:
                if hasattr(value, "to_dict"):
                    self._registry._persist_to_db(value)
            except Exception:
                pass

    def pop(self, key: str, default: Any = None) -> Any:
        res = super().pop(key, default)
        if getattr(self._registry, "_persistent", False):
            try:
                with db_session() as conn:
                    conn.execute("DELETE FROM instruments WHERE instrument_id = ?", (key,))
            except Exception:
                pass
        return res


class InstrumentRegistry:
    """
    Thread-safe storage repository for weighing instruments with advanced
    metrological, serial, and customer search capabilities.
    """

    def __init__(self, persistent: bool = False) -> None:
        self._lock = threading.RLock()
        self._persistent = persistent
        self._instruments: Dict[str, Instrument] = _InstrumentsDict(self)
        self._serial_index: Dict[str, str] = {}  # serial_number -> instrument_id
        if self._persistent:
            init_db()
            self._load_from_db()
        self._load_seed_instruments()

    def _persist_to_db(self, instrument: Instrument) -> None:
        now = datetime.now(timezone.utc).isoformat()
        created_at = getattr(instrument, "created_at", None) or now
        updated_at = getattr(instrument, "updated_at", None) or now
        data_json = json.dumps(instrument.to_dict())
        acc_class = instrument.accuracy_class.roman if hasattr(instrument.accuracy_class, "roman") else str(instrument.accuracy_class)
        unit_val = instrument.unit.value if hasattr(instrument.unit, "value") else str(instrument.unit)
        status_val = instrument.status.value if hasattr(instrument.status, "value") else str(instrument.status)
        cust_name = instrument.location.customer_name if getattr(instrument, "location", None) else "Standard Client"

        with db_session() as conn:
            conn.execute(
                """
                INSERT INTO instruments (
                    instrument_id, serial_number, model_approval_number, accuracy_class,
                    max_capacity, unit, status, customer_name, data_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(instrument_id) DO UPDATE SET
                    serial_number=excluded.serial_number,
                    model_approval_number=excluded.model_approval_number,
                    accuracy_class=excluded.accuracy_class,
                    max_capacity=excluded.max_capacity,
                    unit=excluded.unit,
                    status=excluded.status,
                    customer_name=excluded.customer_name,
                    data_json=excluded.data_json,
                    updated_at=excluded.updated_at
                """,
                (
                    instrument.instrument_id,
                    instrument.serial_number,
                    instrument.model_approval_number,
                    acc_class,
                    instrument.max_capacity,
                    unit_val,
                    status_val,
                    cust_name,
                    data_json,
                    created_at,
                    updated_at,
                ),
            )

    def _load_from_db(self) -> None:
        try:
            with db_session() as conn:
                rows = conn.execute("SELECT data_json FROM instruments").fetchall()
                for r in rows:
                    try:
                        data = json.loads(r["data_json"])
                        inst = Instrument.from_dict(data)
                        super(_InstrumentsDict, self._instruments).__setitem__(inst.instrument_id, inst)
                        self._serial_index[inst.serial_number.strip().upper()] = inst.instrument_id
                    except Exception:
                        pass
        except Exception:
            pass

    def _load_seed_instruments(self) -> None:
        """Loads representative pre-configured instruments for immediate testing."""
        # 1. Retail Grocery Counter Scale (Class III, 15 kg, e=5g)
        inst_1 = Instrument(
            instrument_id="INST-RETAIL-001",
            serial_number="ESSAE-2024-9981",
            manufacturer="Essae-Teraoka Ltd.",
            model_name="DS-215 Electronic Retail Scale",
            model_number="DS-215",
            instrument_name="Essae DS-215 Retail Counter Scale",
            description="Digital counter scale for retail supermarket checkout and trade packaging.",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=15.0,
            min_capacity=0.1,
            e=0.005,
            d=0.005,
            unit=MassUnit.KG,
            instrument_type=InstrumentType.ELECTRONIC_COUNTER_SCALE,
            graduation_type=GraduationType.GRADUATED,
            status=InstrumentStatus.ACTIVE,
            model_approval_number="IND/09/2024/001",
            model_approval_date="2024-01-15",
            model_approval_mark="IND-LM-2024-001",
            approval_status=ApprovalStatus.APPROVED,
            manufacturer_info=ManufacturerInfo(
                name="Essae-Teraoka Ltd.",
                country_of_origin="INDIA",
                dealer_license_number="DL-KA-2021-9981",
            ),
            usage_type=UsageType.COMMERCIAL_TRADE,
            transaction_usage=TransactionUsage.COMMERCIAL_TRANSACTION,
            consumer_impact=ConsumerImpact.HIGH_DIRECT_RETAIL,
            indication_type=IndicationType.DIGITAL,
            is_electronic=True,
            has_zero_setting=True,
            zero_setting_type=ZeroSettingType.SEMI_AUTOMATIC,
            zero_setting_range_percent=4.0,
            initial_zero_setting_range_percent=20.0,
            has_tare=True,
            tare_type=TareType.SUBTRACTIVE,
            max_tare=7.5,
            receptor_type="STAINLESS_STEEL_PAN",
            manufacturing_year=2024,
            location=CustomerLocation(
                customer_name="FreshMart Supermarket",
                contact_person="Ramesh Kumar",
                phone="+91-9876543210",
                site_name="FreshMart Indiranagar Branch",
                department="Produce & Grocery Checkout",
                installation_environment="RETAIL_COUNTER",
                address="Shop 12, Main Market, Indiranagar",
                city="Bengaluru",
                state="Karnataka",
                pincode="560038",
            ),
            seals=[
                PhysicalSeal(
                    seal_id="SEAL-001",
                    seal_type=SealType.LEAD_AND_WIRE,
                    seal_number="KA-LM-2024-5541",
                    location="Calibration Port Cover",
                    applied_date="2024-02-01",
                    applied_by="Insp. V. Sharma (LM Dept)",
                    status=SealStatus.INTACT,
                )
            ],
            verification_status=VerificationStatus.VERIFIED,
            verification_officer="Insp. V. Sharma (LM Dept)",
            stamp_mark="STAMP-KA-2024-Q1",
            last_verification_date="2024-02-01",
            last_verification_certificate="CERT-KA-2024-8871",
            next_re_verification_due="2025-02-01",
            re_verification_interval_months=12,
            manufactured_date="2024-01-10",
            installed_date="2024-01-25",
        )
        self.register(inst_1)

        # 2. Precision Laboratory Balance (Class II, 6000 g, e=0.1g)
        inst_2 = Instrument(
            instrument_id="INST-LAB-002",
            serial_number="SART-2023-4102",
            manufacturer="Sartorius India Pvt. Ltd.",
            model_name="Entris II Analytical Lab Balance",
            model_number="ENTRIS-II-6000",
            instrument_name="Sartorius Entris II Precision Laboratory Balance",
            description="High-precision laboratory electronic balance for chemical analysis and pharmaceutical formulation.",
            accuracy_class=AccuracyClass.CLASS_II,
            max_capacity=6000.0,
            min_capacity=5.0,
            e=0.1,
            d=0.1,
            unit=MassUnit.G,
            instrument_type=InstrumentType.PRECISION_BALANCE,
            graduation_type=GraduationType.GRADUATED,
            status=InstrumentStatus.ACTIVE,
            model_approval_number="IND/09/2023/045",
            model_approval_date="2023-04-10",
            model_approval_mark="IND-LM-2023-045",
            approval_status=ApprovalStatus.APPROVED,
            manufacturer_info=ManufacturerInfo(
                name="Sartorius India Pvt. Ltd.",
                country_of_origin="INDIA",
                dealer_license_number="DL-KA-2020-4102",
            ),
            usage_type=UsageType.LABORATORY_RESEARCH,
            transaction_usage=TransactionUsage.INTERNAL_QUALITY_CONTROL,
            consumer_impact=ConsumerImpact.CRITICAL_HEALTHCARE,
            indication_type=IndicationType.DIGITAL,
            is_electronic=True,
            has_zero_setting=True,
            zero_setting_type=ZeroSettingType.SEMI_AUTOMATIC,
            has_tare=True,
            tare_type=TareType.SUBTRACTIVE,
            max_tare=3000.0,
            receptor_type="CIRCULAR_PAN",
            manufacturing_year=2023,
            location=CustomerLocation(
                customer_name="Apex Pharma QC Laboratories",
                contact_person="Dr. Ananya Sen",
                phone="+91-9845012345",
                site_name="Peenya Quality Control Facility",
                department="Analytical Chemistry Wing",
                installation_environment="LAB_CLEANROOM",
                address="Plot 45, Peenya Industrial Area",
                city="Bengaluru",
                state="Karnataka",
                pincode="560058",
            ),
            seals=[
                PhysicalSeal(
                    seal_id="SEAL-002",
                    seal_type=SealType.TAMPER_EVIDENT_LABEL,
                    seal_number="KA-SEC-2023-1120",
                    location="Main Housing Seam",
                    applied_date="2023-06-15",
                    applied_by="Insp. R. Patil",
                    status=SealStatus.INTACT,
                )
            ],
            verification_status=VerificationStatus.VERIFIED,
            verification_officer="Insp. R. Patil",
            stamp_mark="STAMP-KA-2023-Q2",
            last_verification_date="2023-06-15",
            last_verification_certificate="CERT-KA-2023-4412",
            next_re_verification_due="2025-06-15",
            re_verification_interval_months=24,
            manufactured_date="2023-05-02",
            installed_date="2023-06-01",
        )
        self.register(inst_2)

        # 3. Commercial Road Weighbridge (Class III, 60,000 kg, e=20kg)
        inst_3 = Instrument(
            instrument_id="INST-WEIGHBRIDGE-003",
            serial_number="AVERY-2022-8819",
            manufacturer="Avery India Ltd.",
            model_name="BridgeMont Pitless Road Weighbridge",
            model_number="BRIDGEMONT-60T",
            instrument_name="Avery BridgeMont Pitless Road Weighbridge",
            description="Heavy capacity 60-tonne road truck scale for bulk cement logistics and axle weighing.",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=60000.0,
            min_capacity=400.0,
            e=20.0,
            d=20.0,
            unit=MassUnit.KG,
            instrument_type=InstrumentType.WEIGHBRIDGE,
            graduation_type=GraduationType.GRADUATED,
            status=InstrumentStatus.ACTIVE,
            model_approval_number="IND/09/2022/112",
            model_approval_date="2022-08-15",
            model_approval_mark="IND-LM-2022-112",
            approval_status=ApprovalStatus.APPROVED,
            manufacturer_info=ManufacturerInfo(
                name="Avery India Ltd.",
                country_of_origin="INDIA",
                dealer_license_number="DL-TS-2019-8819",
            ),
            usage_type=UsageType.INDUSTRIAL,
            transaction_usage=TransactionUsage.COMMERCIAL_TRANSACTION,
            consumer_impact=ConsumerImpact.MEDIUM_COMMERCIAL,
            indication_type=IndicationType.DIGITAL,
            is_electronic=True,
            has_zero_setting=True,
            zero_setting_type=ZeroSettingType.SEMI_AUTOMATIC,
            has_tare=True,
            tare_type=TareType.SUBTRACTIVE,
            max_tare=30000.0,
            receptor_type="STEEL_DECK",
            manufacturing_year=2022,
            location=CustomerLocation(
                customer_name="Deccan Cement Logistics Yard",
                contact_person="M. K. Reddy",
                phone="+91-9988776655",
                site_name="Yard Ingate Scale 1",
                department="Logistics & Dispatch",
                installation_environment="WEIGHBRIDGE_OUTDOOR",
                address="NH-44 Highway Mile 18",
                city="Hyderabad",
                state="Telangana",
                pincode="500072",
            ),
            seals=[
                PhysicalSeal(
                    seal_id="SEAL-003",
                    seal_type=SealType.LEAD_AND_WIRE,
                    seal_number="TS-WB-2023-9901",
                    location="Junction Box 1",
                    applied_date="2023-09-10",
                    applied_by="Insp. K. Rao (TS LM Dept)",
                    status=SealStatus.INTACT,
                )
            ],
            verification_status=VerificationStatus.VERIFIED,
            verification_officer="Insp. K. Rao (TS LM Dept)",
            stamp_mark="STAMP-TS-2023-Q3",
            last_verification_date="2023-09-10",
            last_verification_certificate="CERT-TS-2023-0910",
            next_re_verification_due="2024-09-10",
            re_verification_interval_months=12,
            manufactured_date="2022-09-01",
            installed_date="2022-10-15",
        )
        for inst in (inst_1, inst_2, inst_3):
            if not self.exists(inst.instrument_id):
                self.register(inst)
            else:
                self.get(inst.instrument_id)

    def register(self, instrument: Instrument) -> Instrument:
        """Registers a new instrument in the repository."""
        with self._lock:
            clean_serial = instrument.serial_number.strip().upper()
            if clean_serial in self._serial_index:
                existing_id = self._serial_index[clean_serial]
                if existing_id != instrument.instrument_id:
                    raise ValueError(
                        f"Serial number '{instrument.serial_number}' is already registered "
                        f"under instrument ID '{existing_id}'."
                    )
            if self._persistent:
                with db_session() as conn:
                    row = conn.execute(
                        "SELECT instrument_id FROM instruments WHERE UPPER(serial_number) = ? AND instrument_id != ?",
                        (clean_serial, instrument.instrument_id),
                    ).fetchone()
                    if row:
                        raise ValueError(
                            f"Serial number '{instrument.serial_number}' is already registered "
                            f"under instrument ID '{row['instrument_id']}'."
                        )

            self._instruments[instrument.instrument_id] = instrument
            self._serial_index[clean_serial] = instrument.instrument_id
            return instrument

    def get(self, instrument_id: str) -> Optional[Instrument]:
        """Retrieves an instrument by instrument_id."""
        with self._lock:
            clean_id = instrument_id.strip()
            if clean_id in self._instruments:
                return self._instruments[clean_id]
            if self._persistent:
                with db_session() as conn:
                    row = conn.execute(
                        "SELECT data_json FROM instruments WHERE instrument_id = ?",
                        (clean_id,),
                    ).fetchone()
                    if row:
                        inst = Instrument.from_dict(json.loads(row["data_json"]))
                        super(_InstrumentsDict, self._instruments).__setitem__(inst.instrument_id, inst)
                        self._serial_index[inst.serial_number.strip().upper()] = inst.instrument_id
                        return inst
            return None

    def get_by_serial(self, serial_number: str) -> Optional[Instrument]:
        """Retrieves an instrument by serial_number."""
        with self._lock:
            clean_serial = serial_number.strip().upper()
            inst_id = self._serial_index.get(clean_serial)
            if inst_id:
                return self.get(inst_id)
            if self._persistent:
                with db_session() as conn:
                    row = conn.execute(
                        "SELECT instrument_id, data_json FROM instruments WHERE UPPER(serial_number) = ?",
                        (clean_serial,),
                    ).fetchone()
                    if row:
                        inst = Instrument.from_dict(json.loads(row["data_json"]))
                        super(_InstrumentsDict, self._instruments).__setitem__(inst.instrument_id, inst)
                        self._serial_index[clean_serial] = inst.instrument_id
                        return inst
            return None

    def exists(self, instrument_id: str) -> bool:
        """Checks if an instrument exists."""
        with self._lock:
            clean_id = instrument_id.strip()
            if clean_id in self._instruments:
                return True
            if self._persistent:
                with db_session() as conn:
                    row = conn.execute(
                        "SELECT 1 FROM instruments WHERE instrument_id = ?",
                        (clean_id,),
                    ).fetchone()
                    return row is not None
            return False

    def update(self, instrument: Instrument) -> Instrument:
        """Updates an existing instrument in the repository."""
        with self._lock:
            if not self.exists(instrument.instrument_id):
                raise KeyError(f"Instrument with ID '{instrument.instrument_id}' does not exist.")

            instrument.updated_at = datetime.now(timezone.utc).isoformat()
            return self.register(instrument)

    def delete(self, instrument_id: str) -> bool:
        """Deletes an instrument from the repository."""
        with self._lock:
            clean_id = instrument_id.strip()
            deleted = False
            if self._persistent:
                with db_session() as conn:
                    cur = conn.execute("DELETE FROM instruments WHERE instrument_id = ?", (clean_id,))
                    if cur.rowcount > 0:
                        deleted = True
            inst = super(_InstrumentsDict, self._instruments).pop(clean_id, None)
            if inst:
                clean_serial = inst.serial_number.strip().upper()
                self._serial_index.pop(clean_serial, None)
                return True
            return deleted

    def list_all(
        self,
        status: Optional[Union[str, InstrumentStatus]] = None,
        accuracy_class: Optional[Union[str, AccuracyClass]] = None,
        instrument_type: Optional[Union[str, InstrumentType]] = None,
        usage_type: Optional[Union[str, UsageType]] = None,
        verification_status: Optional[Union[str, VerificationStatus]] = None,
        approval_status: Optional[Union[str, ApprovalStatus]] = None,
        gatc_code: Optional[str] = None,
        manufacturer: Optional[str] = None,
        customer_name: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Instrument]:
        """Lists and filters instruments matching specified attributes."""
        with self._lock:
            if self._persistent:
                with db_session() as conn:
                    rows = conn.execute("SELECT data_json FROM instruments").fetchall()
                    for r in rows:
                        try:
                            data = json.loads(r["data_json"])
                            iid = data.get("instrument_id")
                            if iid and iid not in self._instruments:
                                inst = Instrument.from_dict(data)
                                super(_InstrumentsDict, self._instruments).__setitem__(inst.instrument_id, inst)
                                self._serial_index[inst.serial_number.strip().upper()] = inst.instrument_id
                        except Exception:
                            pass

            results: List[Instrument] = []
            target_status = InstrumentStatus.from_value(status) if status is not None else None
            target_class = AccuracyClass.from_string(str(accuracy_class)) if accuracy_class is not None else None
            target_type = InstrumentType.from_value(instrument_type) if instrument_type is not None else None
            target_usage = UsageType.from_value(usage_type) if usage_type is not None else None
            target_ver_status = VerificationStatus.from_value(verification_status) if verification_status is not None else None
            target_app_status = ApprovalStatus.from_value(approval_status) if approval_status is not None else None
            target_gatc = gatc_code.strip().upper() if gatc_code else None
            search_term = search.lower().strip() if search else None

            for inst in self._instruments.values():
                if target_status and inst.status != target_status:
                    continue
                if target_class and inst.accuracy_class != target_class:
                    continue
                if target_type and inst.instrument_type != target_type:
                    continue
                if target_usage and inst.usage_type != target_usage:
                    continue
                if target_ver_status and inst.verification_status != target_ver_status:
                    continue
                if target_app_status and inst.approval_status != target_app_status:
                    continue
                if target_gatc and (not inst.gatc_code or target_gatc not in inst.gatc_code.upper()):
                    continue
                if manufacturer and manufacturer.lower() not in inst.manufacturer.lower():
                    continue
                if customer_name and customer_name.lower() not in inst.location.customer_name.lower():
                    continue
                if search_term:
                    match_found = (
                        search_term in inst.instrument_id.lower()
                        or search_term in inst.serial_number.lower()
                        or search_term in inst.manufacturer.lower()
                        or search_term in inst.model_name.lower()
                        or search_term in inst.model_number.lower()
                        or search_term in inst.instrument_name.lower()
                        or search_term in inst.description.lower()
                        or search_term in inst.location.customer_name.lower()
                        or (inst.location.site_name and search_term in inst.location.site_name.lower())
                        or (inst.model_approval_number and search_term in inst.model_approval_number.lower())
                        or (inst.gatc_code and search_term in inst.gatc_code.lower())
                    )
                    if not match_found:
                        continue

                results.append(inst)

            return results

    def count(self) -> int:
        """Returns total instrument count in registry."""
        with self._lock:
            if self._persistent:
                with db_session() as conn:
                    row = conn.execute("SELECT COUNT(*) AS cnt FROM instruments").fetchone()
                    db_cnt = row["cnt"] if row else 0
                return max(len(self._instruments), db_cnt)
            return len(self._instruments)

    def clear(self) -> None:
        """Clears all instruments (used for testing isolation)."""
        with self._lock:
            self._instruments.clear()
            self._serial_index.clear()
            if self._persistent:
                with db_session() as conn:
                    conn.execute("DELETE FROM instruments")


# Singleton instance for application runtime
INSTRUMENT_REGISTRY = InstrumentRegistry(persistent=True)
