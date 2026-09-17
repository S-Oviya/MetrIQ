"""
MetrIQ Instrument Service — Person 3 (Job / Instrument Engineer)
================================================================
High-level service coordinating instrument registration, Person 2 metrological
validation, Model Approval certificate verification, and lifecycle operations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

# Consumes Person 2 exposed API without modifying Person 2 code
from app.regulatory.api import validate_instrument_api, get_regulatory_profile_api
from .models import (
    CustomerLocation,
    Instrument,
    InstrumentLifecycleEvent,
    InstrumentStatus,
    InstrumentType,
    LifecycleEventType,
    PhysicalSeal,
    SealStatus,
    SealType,
    UsageType,
    VerificationStatus,
    VerificationReason,
    ApprovalStatus,
)
from .model_approval import (
    MODEL_APPROVAL_REGISTRY,
    ModelApprovalCertificate,
    ModelApprovalRecord,
    ModelApprovalStatus,
    ModelApprovalStateTransitionError,
)
from .registry import INSTRUMENT_REGISTRY, InstrumentRegistry
from .lifecycle import InstrumentLifecycleManager, InstrumentLifecycleTransitionError
from .scheduling import VERIFICATION_SCHEDULER, VerificationScheduler


def validate_lifecycle_dates(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validates chronological sequence of instrument lifecycle dates.
    Enforces that manufactured <= installed <= (repair, dismantled, retired).
    """
    errors: List[str] = []

    def parse_dt(k: str) -> Optional[datetime]:
        v = data.get(k)
        if not v or not isinstance(v, str):
            return None
        clean = v.strip()[:10]
        try:
            return datetime.strptime(clean, "%Y-%m-%d")
        except ValueError:
            return None

    m_dt = parse_dt("manufactured_date") or parse_dt("manufacturing_date")
    i_dt = parse_dt("installed_date") or parse_dt("installation_date")
    rep_dt = parse_dt("repair_date") or parse_dt("last_repair_date")
    dis_dt = parse_dt("dismantled_date")
    reinst_dt = parse_dt("reinstalled_date") or parse_dt("relocated_date")
    ret_dt = parse_dt("retired_date") or parse_dt("decommissioned_date")

    if m_dt and i_dt and i_dt < m_dt:
        errors.append(f"Installation date ({data.get('installed_date')}) cannot precede manufacturing date ({data.get('manufactured_date')}).")

    if i_dt and rep_dt and rep_dt < i_dt:
        errors.append(f"Repair date ({data.get('repair_date')}) cannot precede installation date ({data.get('installed_date')}).")

    if i_dt and dis_dt and dis_dt < i_dt:
        errors.append(f"Dismantled date ({data.get('dismantled_date')}) cannot precede installation date ({data.get('installed_date')}).")

    if dis_dt and reinst_dt and reinst_dt < dis_dt:
        errors.append(f"Reinstallation/relocation date ({data.get('reinstalled_date')}) cannot precede dismantling date ({data.get('dismantled_date')}).")

    if i_dt and ret_dt and ret_dt < i_dt:
        errors.append(f"Retirement date ({data.get('retired_date')}) cannot precede installation date ({data.get('installed_date')}).")

    return len(errors) == 0, errors


class InstrumentService:
    """
    Core service for managing weighing instruments, integrating statutory validation,
    model approval verification, and physical seals.
    """

    def __init__(
        self,
        registry: Optional[InstrumentRegistry] = None,
        scheduler: Optional[VerificationScheduler] = None,
    ) -> None:
        self.registry = registry or INSTRUMENT_REGISTRY
        self.scheduler = scheduler or (
            VerificationScheduler(instrument_registry=self.registry)
            if registry
            else VERIFICATION_SCHEDULER
        )

    def validate_metrology(self, instrument_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Delegates metrological feasibility check to Person 2's Regulatory Engine.
        Returns Person 2's validation result dict.
        """
        # Call Person 2 canonical validation API directly
        validation_resp = validate_instrument_api(instrument_data)
        return validation_resp

    def create_instrument(
        self,
        data: Dict[str, Any],
        enforce_model_approval: bool = True,
    ) -> Dict[str, Any]:
        """
        Registers a new weighing instrument:
        1. Validates metrology via Person 2.
        2. Validates against Model Approval certificate envelope if declared.
        3. Initializes statutory lifecycle and re-verification due dates.
        4. Saves to InstrumentRegistry.
        """
        # 1. Lifecycle date validation
        valid_dates, date_errs = validate_lifecycle_dates(data)
        if not valid_dates:
            return {
                "success": False,
                "status_code": 422,
                "message": f"Instrument fails lifecycle date validation: {'; '.join(date_errs)}",
                "validation_errors": [{"rule_id": "RULE_LIFECYCLE_DATES", "message": err} for err in date_errs],
            }

        # 2. Metrological validation via Person 2
        validation_res = self.validate_metrology(data)
        val_data = validation_res.get("data", {})
        if not val_data.get("valid", False):
            errors = val_data.get("errors", [])
            err_msgs = [f"[{e.get('rule_id', 'ERROR')}] {e.get('message', 'Invalid metrology')}" for e in errors]
            return {
                "success": False,
                "status_code": 422,
                "message": f"Instrument fails statutory metrological validation: {'; '.join(err_msgs)}",
                "validation_errors": errors,
                "validation_warnings": val_data.get("warnings", []),
            }

        # 3. Construct Instrument entity
        inst = Instrument.from_dict(data)

        # 4. Model approval verification if declared
        model_approval_check: Dict[str, Any] = {"verified": True, "reasons": []}
        if inst.model_approval_number:
            is_valid_ma, cert, ma_reasons = MODEL_APPROVAL_REGISTRY.verify_instrument(inst)
            model_approval_check = {
                "verified": is_valid_ma,
                "approval_number": inst.model_approval_number,
                "certificate_found": cert is not None,
                "reasons": ma_reasons,
            }
            if not is_valid_ma and enforce_model_approval:
                return {
                    "success": False,
                    "status_code": 400,
                    "message": f"Instrument violates Model Approval envelope: {'; '.join(ma_reasons)}",
                    "model_approval_check": model_approval_check,
                    "validation_warnings": val_data.get("warnings", []),
                }

        # 5. Set statutory re-verification due date if verified/active
        if inst.last_verification_date and not inst.next_re_verification_due:
            inst.next_re_verification_due = InstrumentLifecycleManager.calculate_next_re_verification_due(
                inst, verification_date=inst.last_verification_date
            )

        # 6. Save to Registry
        try:
            saved = self.registry.register(inst)
            # Record statutory REGISTRATION lifecycle event
            try:
                InstrumentLifecycleManager.record_lifecycle_event(
                    instrument=saved,
                    event_type=LifecycleEventType.REGISTRATION,
                    new_status=saved.status,
                    actor=str(data.get("registered_by") or data.get("created_by") or "SYSTEM"),
                    event_date=saved.registered_date or datetime.now().strftime("%Y-%m-%d"),
                    notes=f"Instrument registered in MetrIQ inventory. Serial: {saved.serial_number}",
                )
            except Exception:
                pass

            # Auto-associate instrument with model approval record if registered
            if inst.model_approval_number and MODEL_APPROVAL_REGISTRY.exists(inst.model_approval_number):
                try:
                    MODEL_APPROVAL_REGISTRY.link_instrument(inst.model_approval_number, saved.instrument_id)
                    InstrumentLifecycleManager.record_lifecycle_event(
                        instrument=saved,
                        event_type=LifecycleEventType.MODEL_APPROVAL_ASSOCIATION,
                        new_status=saved.status,
                        actor="SYSTEM",
                        notes=f"Model approval certificate '{saved.model_approval_number}' associated.",
                    )
                except Exception:
                    pass
            self.registry.update(saved)
        except ValueError as e:
            return {
                "success": False,
                "status_code": 409,
                "message": str(e),
            }

        return {
            "success": True,
            "status_code": 201,
            "message": f"Instrument '{saved.instrument_id}' successfully registered.",
            "data": saved.to_dict(),
            "regulatory_validation": {
                "valid": True,
                "warnings": val_data.get("warnings", []),
                "manual_review_required": val_data.get("manual_review_required", False),
            },
            "model_approval_check": model_approval_check,
        }

    def get_instrument(self, instrument_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves an instrument by ID with live operational status evaluation."""
        inst = self.registry.get(instrument_id)
        if not inst:
            return None

        # Re-evaluate live operational status (e.g. check for expired due date or broken seals)
        live_status = InstrumentLifecycleManager.evaluate_operational_status(inst)
        if live_status != inst.status:
            inst.status = live_status
            self.registry.update(inst)

        return inst.to_dict()

    def get_by_serial(self, serial_number: str) -> Optional[Dict[str, Any]]:
        """Retrieves an instrument by its serial number."""
        inst = self.registry.get_by_serial(serial_number)
        return inst.to_dict() if inst else None

    def update_instrument(
        self,
        instrument_id: str,
        update_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Updates an instrument with re-validation if metrology is altered."""
        existing = self.registry.get(instrument_id)
        if not existing:
            return {
                "success": False,
                "status_code": 404,
                "message": f"Instrument '{instrument_id}' not found.",
            }

        # Merge dicts
        merged = existing.to_dict()
        for k, v in update_data.items():
            if k not in ("instrument_id", "created_at") and v is not None:
                merged[k] = v

        # Validate lifecycle dates
        valid_dates, date_errs = validate_lifecycle_dates(merged)
        if not valid_dates:
            return {
                "success": False,
                "status_code": 422,
                "message": f"Updated lifecycle dates are invalid: {'; '.join(date_errs)}",
                "validation_errors": [{"rule_id": "RULE_LIFECYCLE_DATES", "message": err} for err in date_errs],
            }

        # Re-validate metrology if any core scale parameters changed
        metrology_keys = {"accuracy_class", "Max", "max_capacity", "Min", "min_capacity", "e", "d", "unit"}
        if any(k in update_data for k in metrology_keys):
            val_res = self.validate_metrology(merged)
            val_data = val_res.get("data", {})
            if not val_data.get("valid", False):
                errs = [e.get("message", "Invalid") for e in val_data.get("errors", [])]
                return {
                    "success": False,
                    "status_code": 422,
                    "message": f"Updated metrology is invalid: {'; '.join(errs)}",
                    "validation_errors": val_data.get("errors", []),
                }

        updated_inst = Instrument.from_dict(merged)
        saved = self.registry.update(updated_inst)
        if saved.model_approval_number and MODEL_APPROVAL_REGISTRY.exists(saved.model_approval_number):
            try:
                MODEL_APPROVAL_REGISTRY.link_instrument(saved.model_approval_number, saved.instrument_id)
            except Exception:
                pass
        return {
            "success": True,
            "status_code": 200,
            "message": f"Instrument '{instrument_id}' updated successfully.",
            "data": saved.to_dict(),
        }

    def delete_instrument(self, instrument_id: str) -> bool:
        """Removes an instrument from the registry."""
        return self.registry.delete(instrument_id)

    def list_instruments(
        self,
        status: Optional[str] = None,
        accuracy_class: Optional[str] = None,
        instrument_type: Optional[str] = None,
        usage_type: Optional[str] = None,
        verification_status: Optional[str] = None,
        approval_status: Optional[str] = None,
        gatc_code: Optional[str] = None,
        manufacturer: Optional[str] = None,
        customer_name: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Lists instruments with optional filters."""
        instruments = self.registry.list_all(
            status=status,
            accuracy_class=accuracy_class,
            instrument_type=instrument_type,
            usage_type=usage_type,
            verification_status=verification_status,
            approval_status=approval_status,
            gatc_code=gatc_code,
            manufacturer=manufacturer,
            customer_name=customer_name,
            search=search,
        )
        return [inst.to_dict() for inst in instruments]

    def add_seal(
        self,
        instrument_id: str,
        seal_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Applies a statutory verification seal to the instrument."""
        inst = self.registry.get(instrument_id)
        if not inst:
            return {"success": False, "status_code": 404, "message": f"Instrument '{instrument_id}' not found."}

        seal = PhysicalSeal.from_dict(seal_data)
        InstrumentLifecycleManager.apply_seal(inst, seal)
        self.registry.update(inst)

        return {
            "success": True,
            "status_code": 200,
            "message": f"Seal '{seal.seal_number}' applied to instrument '{instrument_id}'.",
            "data": seal.to_dict(),
        }

    def report_broken_seal(
        self,
        instrument_id: str,
        seal_id: str,
        reason: str,
        reported_by: str,
    ) -> Dict[str, Any]:
        """Records a broken statutory seal, immediately invalidating commercial use."""
        inst = self.registry.get(instrument_id)
        if not inst:
            return {"success": False, "status_code": 404, "message": f"Instrument '{instrument_id}' not found."}

        ok, msg = InstrumentLifecycleManager.report_broken_seal(inst, seal_id, reason, reported_by)
        if ok:
            self.registry.update(inst)
            return {"success": True, "status_code": 200, "message": msg, "instrument_status": inst.status.value}
        return {"success": False, "status_code": 400, "message": msg}

    # =========================================================================
    # Model Approval Management Methods
    # =========================================================================

    def create_model_approval(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates and registers a new model approval record."""
        try:
            record = MODEL_APPROVAL_REGISTRY.create_record(data)
            return {
                "success": True,
                "status_code": 201,
                "message": f"Model approval record '{record.application_reference}' created successfully.",
                "data": record.to_dict(),
            }
        except ValueError as e:
            err_str = str(e)
            status_code = 409 if "already exists" in err_str or "already issued" in err_str else 422
            return {
                "success": False,
                "status_code": status_code,
                "message": err_str,
            }

    def update_model_approval(self, reference: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Updates an existing model approval record."""
        try:
            record = MODEL_APPROVAL_REGISTRY.update_record(reference, data)
            return {
                "success": True,
                "status_code": 200,
                "message": f"Model approval '{reference}' updated successfully.",
                "data": record.to_dict(),
            }
        except KeyError as e:
            return {"success": False, "status_code": 404, "message": str(e)}
        except ModelApprovalStateTransitionError as e:
            return {"success": False, "status_code": 400, "message": str(e)}
        except ValueError as e:
            err_str = str(e)
            status_code = 409 if "already issued" in err_str else 422
            return {"success": False, "status_code": status_code, "message": err_str}

    def transition_model_approval(self, reference: str, to_status: str, **kwargs: Any) -> Dict[str, Any]:
        """Transitions a model approval record's lifecycle status."""
        try:
            record = MODEL_APPROVAL_REGISTRY.transition_status(reference, to_status, **kwargs)
            return {
                "success": True,
                "status_code": 200,
                "message": f"Model approval '{reference}' transitioned to {record.status.value}.",
                "data": record.to_dict(),
            }
        except KeyError as e:
            return {"success": False, "status_code": 404, "message": str(e)}
        except ModelApprovalStateTransitionError as e:
            return {"success": False, "status_code": 400, "message": str(e)}
        except ValueError as e:
            return {"success": False, "status_code": 422, "message": str(e)}

    def get_model_approval(self, reference: str) -> Optional[Dict[str, Any]]:
        """Retrieves a model approval record by reference or certificate number."""
        record = MODEL_APPROVAL_REGISTRY.get_by_reference(reference)
        return record.to_dict() if record else None

    def list_model_approvals(
        self,
        manufacturer: Optional[str] = None,
        accuracy_class: Optional[str] = None,
        status: Optional[str] = None,
        instrument_type: Optional[str] = None,
        search: Optional[str] = None,
        valid_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Lists model approval records with multi-field filtering."""
        records = MODEL_APPROVAL_REGISTRY.list_all(
            manufacturer=manufacturer,
            accuracy_class=accuracy_class,
            status=status,
            instrument_type=instrument_type,
            search=search,
            valid_only=valid_only,
        )
        return [r.to_dict() for r in records]

    def link_model_approval_instrument(self, reference: str, instrument_id: str) -> Dict[str, Any]:
        """Associates an instrument with a model approval."""
        try:
            record = MODEL_APPROVAL_REGISTRY.link_instrument(reference, instrument_id)
            # Also update instrument if it exists in registry
            inst = self.registry.get(instrument_id)
            if inst:
                inst.model_approval_number = record.approval_number or record.application_reference
                self.registry.update(inst)

            return {
                "success": True,
                "status_code": 200,
                "message": f"Instrument '{instrument_id}' linked to model approval '{reference}'.",
                "associated_instruments": record.associated_instrument_ids,
                "data": record.to_dict(),
            }
        except KeyError as e:
            return {"success": False, "status_code": 404, "message": str(e)}

    def record_lifecycle_event(
        self,
        instrument_id: str,
        event_type: Union[str, LifecycleEventType],
        new_status: Union[str, InstrumentStatus],
        actor: str = "SYSTEM",
        event_date: Optional[str] = None,
        related_job_id: Optional[str] = None,
        notes: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes and records a statutory lifecycle transition event on an instrument.
        Validates sensible state transitions and maintains immutable audit history.
        """
        inst = self.registry.get(instrument_id)
        if not inst:
            return {"success": False, "status_code": 404, "message": f"Instrument '{instrument_id}' not found."}

        try:
            event = InstrumentLifecycleManager.record_lifecycle_event(
                instrument=inst,
                event_type=event_type,
                new_status=new_status,
                actor=actor,
                event_date=event_date,
                related_job_id=related_job_id,
                notes=notes,
                metadata=metadata,
            )
            self.registry.update(inst)
            return {
                "success": True,
                "status_code": 200,
                "message": f"Lifecycle event '{event.event_type.value}' recorded for instrument '{instrument_id}'.",
                "event": event.to_dict(),
                "instrument_status": inst.status.value,
                "data": inst.to_dict(),
            }
        except InstrumentLifecycleTransitionError as e:
            return {
                "success": False,
                "status_code": 400,
                "message": str(e),
            }

    def get_instrument_lifecycle_history(self, instrument_id: str) -> Dict[str, Any]:
        """Retrieves full immutable lifecycle history for an instrument."""
        inst = self.registry.get(instrument_id)
        if not inst:
            return {"success": False, "status_code": 404, "message": f"Instrument '{instrument_id}' not found."}

        events = InstrumentLifecycleManager.get_lifecycle_history(inst)
        return {
            "success": True,
            "status_code": 200,
            "instrument_id": instrument_id,
            "count": len(events),
            "data": [e.to_dict() for e in events],
        }

    # =========================================================================
    # Verification & Re-verification Scheduling Methods
    # =========================================================================

    def schedule_verification(
        self,
        instrument_id: str,
        base_date: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calculates and stores next verification date using authoritative profile interval."""
        inst = self.registry.get(instrument_id)
        if not inst:
            return {"success": False, "status_code": 404, "message": f"Instrument '{instrument_id}' not found."}
        return self.scheduler.calculate_and_store_next_verification_date(
            instrument=inst, base_date=base_date, profile_id=profile_id
        )

    def flag_verification_due(
        self,
        instrument_id: str,
        as_of_date: Optional[str] = None,
        reminder_window_days: int = 30,
    ) -> Dict[str, Any]:
        """Checks and flags whether instrument is due for verification."""
        inst = self.registry.get(instrument_id)
        if not inst:
            return {"success": False, "status_code": 404, "message": f"Instrument '{instrument_id}' not found."}
        is_due, msg = self.scheduler.flag_verification_due(
            instrument=inst, as_of_date=as_of_date, reminder_window_days=reminder_window_days
        )
        return {
            "success": True,
            "instrument_id": instrument_id,
            "is_due": is_due,
            "message": msg,
            "verification_status": inst.verification_status.value,
            "status": inst.status.value,
            "next_verification_date": inst.next_verification_date,
            "scheduling_metadata": inst.scheduling_metadata,
        }

    def flag_overdue(
        self,
        instrument_id: str,
        as_of_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Checks and flags whether instrument is overdue for verification."""
        inst = self.registry.get(instrument_id)
        if not inst:
            return {"success": False, "status_code": 404, "message": f"Instrument '{instrument_id}' not found."}
        is_overdue, msg = self.scheduler.flag_overdue(instrument=inst, as_of_date=as_of_date)
        return {
            "success": True,
            "instrument_id": instrument_id,
            "is_overdue": is_overdue,
            "message": msg,
            "verification_status": inst.verification_status.value,
            "status": inst.status.value,
            "next_verification_date": inst.next_verification_date,
            "scheduling_metadata": inst.scheduling_metadata,
        }

    def create_verification_job(
        self,
        instrument_id: str,
        job_type: str,
        reason: str,
        scheduled_date: Optional[str] = None,
        user_id: str = "SYSTEM",
        priority: Optional[str] = None,
        notes: str = "",
        inspector_id: Optional[str] = None,
        inspector_name: Optional[str] = None,
        testing_centre_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Provisions a verification test job for an instrument."""
        return self.scheduler.create_verification_job(
            instrument_id=instrument_id,
            job_type=job_type,
            reason=reason,
            scheduled_date=scheduled_date,
            user_id=user_id,
            priority=priority,
            notes=notes,
            inspector_id=inspector_id,
            inspector_name=inspector_name,
            testing_centre_name=testing_centre_name,
        )

    def identify_instruments_requiring_verification(
        self,
        as_of_date: Optional[str] = None,
        state: Optional[str] = None,
        reminder_window_days: int = 30,
        include_manual_review: bool = True,
    ) -> Dict[str, Any]:
        """Scans registry and lists all instruments requiring statutory verification."""
        return self.scheduler.identify_instruments_requiring_verification(
            as_of_date=as_of_date,
            state=state,
            reminder_window_days=reminder_window_days,
            include_manual_review=include_manual_review,
        )

    def complete_verification_job(
        self,
        job_id: str,
        outcome: str,
        certificate_number: Optional[str] = None,
        verification_date: Optional[str] = None,
        inspecting_officer: Optional[str] = None,
        stamping_authority: Optional[str] = None,
        applied_seals: Optional[List[PhysicalSeal]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Updates verification status and re-schedules next date after job completion."""
        return self.scheduler.update_verification_status_after_job(
            job_id=job_id,
            outcome=outcome,
            certificate_number=certificate_number,
            verification_date=verification_date,
            inspecting_officer=inspecting_officer,
            stamping_authority=stamping_authority,
            applied_seals=applied_seals,
            metadata=metadata,
        )


# Global singleton instance for application runtime
INSTRUMENT_SERVICE = InstrumentService()
