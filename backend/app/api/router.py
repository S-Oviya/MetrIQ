"""
MetrIQ Master API Router
Aggregates all sub-system routers (Regulatory, Instruments, Test Engine, Reports, etc.)
for integration by Person 1 (Team Lead).
"""

from typing import Dict, Any, Optional

try:
    from fastapi import APIRouter
    api_router = APIRouter()
except ImportError:
    api_router = None

if api_router is not None:
    try:
        from app.regulatory.router import router as regulatory_router
        if regulatory_router:
            api_router.include_router(regulatory_router)
    except Exception:
        regulatory_router = None

    try:
        from app.api.instruments_router import router as instruments_router
        if instruments_router:
            api_router.include_router(instruments_router)
    except Exception:
        instruments_router = None

    try:
        from app.workflow.router import router as workflow_router
        if workflow_router:
            api_router.include_router(workflow_router)
    except Exception:
        workflow_router = None

    try:
        from app.equipment.router import router as equipment_router
        if equipment_router:
            api_router.include_router(equipment_router)
    except Exception:
        equipment_router = None

    try:
        from app.environment.router import router as environment_router
        if environment_router:
            api_router.include_router(environment_router)
    except Exception:
        environment_router = None

    try:
        from app.attempts.router import router as attempts_router
        if attempts_router:
            api_router.include_router(attempts_router)
    except Exception:
        attempts_router = None

    try:
        from app.evidence.router import router as evidence_router
        if evidence_router:
            api_router.include_router(evidence_router)
    except Exception:
        evidence_router = None

    try:
        from app.review.router import router as review_router
        if review_router:
            api_router.include_router(review_router)
    except Exception:
        review_router = None

    try:
        from app.audit.router import router as audit_router
        if audit_router:
            api_router.include_router(audit_router)
    except Exception:
        audit_router = None

    try:
        from app.api.jobs_router import router as jobs_router
        if jobs_router:
            api_router.include_router(jobs_router)
    except Exception:
        jobs_router = None

    try:
        from app.calculations.router import router as calculations_router
        if calculations_router:
            api_router.include_router(calculations_router)
    except Exception:
        calculations_router = None

    try:
        from app.tests_execution.router import router as tests_execution_router
        if tests_execution_router:
            api_router.include_router(tests_execution_router)
    except Exception:
        tests_execution_router = None

    try:
        from app.reports.router import router as reports_router
        if reports_router:
            api_router.include_router(reports_router)
    except Exception:
        reports_router = None

# High-level service functions for Person 1 direct invocation
from app.regulatory.api import (
    validate_instrument_api,
    calculate_mpe_api,
    determine_applicable_tests_api,
    generate_test_plan_api,
    get_regulatory_profile_api,
    get_rule_or_source_api,
    RegulatoryAPI,
)
from app.instruments.service import INSTRUMENT_SERVICE, InstrumentService
from app.jobs.service import TEST_JOB_SERVICE, TestJobService
from app.instruments.registry import INSTRUMENT_REGISTRY
from app.jobs.repository import TEST_JOB_REPOSITORY
from app.instruments.model_approval import MODEL_APPROVAL_REGISTRY
from app.api.p3_api import (
    Person3API,
    api_register_instrument,
    api_list_instruments,
    api_get_instrument,
    api_update_instrument,
    api_delete_instrument,
    api_register_model_approval,
    api_list_model_approvals,
    api_get_model_approval,
    api_update_model_approval,
    api_create_test_job,
    api_list_test_jobs,
    api_get_test_job,
    api_update_test_job,
    api_validate_test_job,
    api_generate_job_test_plan,
    api_get_instrument_lifecycle,
    api_record_lifecycle_event,
    api_get_due_for_verification,
    api_create_verification_job,
    api_complete_verification_job,
)
from app.api.schemas import success_envelope, error_envelope

__all__ = [
    "api_router",
    # Person 2 Services
    "validate_instrument_api",
    "calculate_mpe_api",
    "determine_applicable_tests_api",
    "generate_test_plan_api",
    "get_regulatory_profile_api",
    "get_rule_or_source_api",
    "RegulatoryAPI",
    # Person 3 Services & Facade
    "Person3API",
    "INSTRUMENT_SERVICE",
    "InstrumentService",
    "TEST_JOB_SERVICE",
    "TestJobService",
    "INSTRUMENT_REGISTRY",
    "TEST_JOB_REPOSITORY",
    "MODEL_APPROVAL_REGISTRY",
    "api_register_instrument",
    "api_list_instruments",
    "api_get_instrument",
    "api_update_instrument",
    "api_delete_instrument",
    "api_register_model_approval",
    "api_list_model_approvals",
    "api_get_model_approval",
    "api_update_model_approval",
    "api_create_test_job",
    "api_list_test_jobs",
    "api_get_test_job",
    "api_update_test_job",
    "api_validate_test_job",
    "api_generate_job_test_plan",
    "api_get_instrument_lifecycle",
    "api_record_lifecycle_event",
    "api_get_due_for_verification",
    "api_create_verification_job",
    "api_complete_verification_job",
    "success_envelope",
    "error_envelope",
    # Person 4 Services
    "CalculationService",
    "calculate_mpe_service",
    "execute_test_service",
    # Person 5 Services
    "WorkflowService",
    "WORKFLOW_SERVICE",
    "WorkflowStateMachine",
    "WorkflowStateTransitionError",
    "transition_job",
    "transitionJob",
    "EquipmentService",
    "EQUIPMENT_SERVICE",
    "Equipment",
    "EquipmentStatus",
    "TestStandard",
    "CalibrationExpiredError",
    "EnvironmentService",
    "ENVIRONMENT_SERVICE",
    "EnvironmentCondition",
    "EnvironmentValidationError",
    "EnvironmentStageError",
    "EnvironmentUpdateRestrictedError",
    "AttemptService",
    "ATTEMPT_SERVICE",
    "TestAttempt",
    "RetestRequest",
    "AttemptStatus",
    "AttemptNotFoundError",
    "TestNotFoundError",
    "AttemptValidationError",
    "AttemptJobStateError",
    "AttemptAlreadyCompletedError",
    "DuplicateAttemptNumberError",
    "EvidenceService",
    "EVIDENCE_SERVICE",
    "Evidence",
    "EvidenceType",
    "EvidenceStatus",
    "EvidenceNotFoundError",
    "EvidenceValidationError",
    "EvidenceSecurityError",
    "EvidenceWorkflowStateError",
    "ReviewService",
    "REVIEW_SERVICE",
    "Review",
    "ReviewStatus",
    "ReviewDecision",
    "ReviewRole",
    "ReviewNotFoundError",
    "ReviewEligibilityError",
    "UnauthorizedReviewerError",
    "InvalidReviewDecisionError",
    "ReviewWorkflowStateError",
    "AuditService",
    "AUDIT_SERVICE",
    "AuditLog",
    "AuditAction",
    "EntityType",
    "AuditRepository",
    "AUDIT_REPOSITORY",
    "AuditImmutabilityError",
    "record_audit",
]

# Person 4 Services
from app.calculations.service import (
    CalculationService,
    calculate_mpe_service,
    execute_test_service,
)

# Person 5 Services
from app.workflow.service import (
    WorkflowService,
    WORKFLOW_SERVICE,
    transition_job,
    transitionJob,
)
from app.workflow.state_machine import (
    WorkflowStateMachine,
    WorkflowStateTransitionError,
)
from app.equipment.service import (
    EquipmentService,
    EQUIPMENT_SERVICE,
    CalibrationExpiredError,
)
from app.equipment.models import (
    Equipment,
    EquipmentStatus,
    TestStandard,
)
from app.environment.service import (
    EnvironmentService,
    ENVIRONMENT_SERVICE,
    EnvironmentValidationError,
    EnvironmentStageError,
    EnvironmentUpdateRestrictedError,
)
from app.environment.models import (
    EnvironmentCondition,
)
from app.attempts.service import (
    AttemptService,
    ATTEMPT_SERVICE,
    AttemptNotFoundError,
    TestNotFoundError,
    AttemptValidationError,
    AttemptJobStateError,
    AttemptAlreadyCompletedError,
    DuplicateAttemptNumberError,
)
from app.attempts.models import (
    TestAttempt,
    RetestRequest,
    AttemptStatus,
)
from app.evidence.service import (
    EvidenceService,
    EVIDENCE_SERVICE,
    EvidenceNotFoundError,
    EvidenceValidationError,
    EvidenceSecurityError,
    EvidenceWorkflowStateError,
)
from app.evidence.models import (
    Evidence,
    EvidenceType,
    EvidenceStatus,
)
from app.review.service import (
    ReviewService,
    REVIEW_SERVICE,
    ReviewNotFoundError,
    ReviewEligibilityError,
    UnauthorizedReviewerError,
    InvalidReviewDecisionError,
    ReviewWorkflowStateError,
)
from app.review.models import (
    Review,
    ReviewStatus,
    ReviewDecision,
    ReviewRole,
)
from app.audit.service import (
    AuditService,
    AUDIT_SERVICE,
    record_audit,
)
from app.audit.models import (
    AuditLog,
    AuditAction,
    EntityType,
)
from app.audit.repository import (
    AuditRepository,
    AUDIT_REPOSITORY,
    AuditImmutabilityError,
)



