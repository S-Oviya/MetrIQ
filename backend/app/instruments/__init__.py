"""
MetrIQ Instruments Module — Person 3 (Job / Instrument Engineer)
================================================================
Exposes high-level models, services, and repositories for weighing instrument
management and statutory model approval tracking.
"""

from .models import (
    ApprovalStatus,
    ConsumerImpact,
    CustomerLocation,
    InstrumentLocation,
    GraduationType,
    IndicationType,
    Instrument,
    InstrumentStatus,
    InstrumentType,
    ManufacturerInfo,
    PhysicalSeal,
    RangeDefinition,
    SealStatus,
    SealType,
    SoftwareConfig,
    TareType,
    TransactionUsage,
    UsageType,
    VerificationStatus,
    ZeroSettingType,
    InstrumentLifecycleEvent,
    LifecycleEventType,
    VerificationReason,
)
from .model_approval import (
    MODEL_APPROVAL_REGISTRY,
    ModelApprovalCertificate,
    ModelApprovalRecord,
    ModelApprovalRegistry,
    ModelApprovalStatus,
    ModelApprovalStateTransitionError,
    LEGAL_MODEL_APPROVAL_TRANSITIONS,
)
from .registry import INSTRUMENT_REGISTRY, InstrumentRegistry
from .lifecycle import (
    InstrumentLifecycleManager,
    InstrumentLifecycleStateMachine,
    InstrumentLifecycleTransitionError,
    VerificationRecord,
)
from .scheduling import VERIFICATION_SCHEDULER, VerificationScheduler
from .service import INSTRUMENT_SERVICE, InstrumentService

__all__ = [
    # Models & Enums
    "ApprovalStatus",
    "ConsumerImpact",
    "CustomerLocation",
    "InstrumentLocation",
    "GraduationType",
    "IndicationType",
    "Instrument",
    "InstrumentStatus",
    "InstrumentType",
    "ManufacturerInfo",
    "PhysicalSeal",
    "RangeDefinition",
    "SealStatus",
    "SealType",
    "SoftwareConfig",
    "TareType",
    "TransactionUsage",
    "UsageType",
    "VerificationStatus",
    "ZeroSettingType",
    "InstrumentLifecycleEvent",
    "LifecycleEventType",
    "VerificationReason",
    # Model Approval
    "MODEL_APPROVAL_REGISTRY",
    "ModelApprovalCertificate",
    "ModelApprovalRecord",
    "ModelApprovalRegistry",
    "ModelApprovalStatus",
    "ModelApprovalStateTransitionError",
    "LEGAL_MODEL_APPROVAL_TRANSITIONS",
    # Registry & Lifecycle
    "INSTRUMENT_REGISTRY",
    "InstrumentRegistry",
    "InstrumentLifecycleManager",
    "InstrumentLifecycleStateMachine",
    "InstrumentLifecycleTransitionError",
    "VerificationRecord",
    # Verification Scheduling
    "VERIFICATION_SCHEDULER",
    "VerificationScheduler",
    # Service Facade
    "INSTRUMENT_SERVICE",
    "InstrumentService",
]
