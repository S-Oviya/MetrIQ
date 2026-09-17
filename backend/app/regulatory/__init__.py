"""
MetrIQ Regulatory Engine Module
Comprehensive OIML R 76-1 / Indian Legal Metrology compliance workflow engine.

Person 2 — Regulatory Engineer Deliverable.
"""

from .models import (
    AccuracyClass,
    ApplicableTest,
    InstrumentProfile,
    JobType,
    MassUnit,
    MPEValue,
    ReceptorType,
    TestPlan,
    TestPoint,
    TestType,
    WeighingRange,
)

from .errors import (
    IssueSeverity,
    RegulatoryErrorCode,
    RegulatoryIssue,
    RegulatoryValidationError,
    ValidationResult,
)

from .sources import (
    Jurisdiction,
    RegulatoryRegistry,
    RegulatorySource,
    StandardStatus,
    REGULATORY_REGISTRY,
)

from .accuracy_class import (
    CLASS_BOUNDARIES,
    ClassBoundary,
    determine_eligible_classes,
    get_class_boundary,
    validate_accuracy_class,
)

from .scale_validation import (
    is_valid_scale_interval_form,
    validate_auxiliary_device,
    validate_instrument_scales,
    validate_multi_interval,
)

from .mpe import (
    MPE_STEPS_BY_CLASS,
    MPEStep,
    calculate_mpe,
    calculate_mpe_in_e,
    get_effective_e_for_load,
    get_mpe_breakpoints_for_instrument,
    is_error_within_mpe,
)

from .mpe_engine import (
    MPEBandDefinition,
    MPECalculationResult,
    MPEEngine,
    MPE_STATUTORY_TABLE,
    VerificationType,
    calculate_mpe_statutory,
    DigitalIndicationErrorResult,
    calculate_digital_indication_error,
)

from .applicability import (
    get_applicable_tests,
    is_test_applicable,
    IndicationType,
    InstrumentCharacteristics,
    InstrumentIndicationMode,
    StatutoryTestDefinition,
    TestEvaluationResult,
    ApplicabilityReport,
    ALL_STATUTORY_TESTS,
    RegulatoryTestApplicabilityEngine,
    evaluate_test_applicability,
)

from .test_plan import (
    generate_discrimination_points,
    generate_eccentricity_points,
    generate_repeatability_points,
    generate_tare_points,
    generate_test_plan,
    generate_weighing_points,
    RegulatoryTestPlanGenerator,
    GeneratedTestPlan,
    TestLoadPoint,
    ExecutableTestItem,
    generate_regulatory_test_plan,
)

from .config import (
    ManualReviewItem,
    RegulatoryConfig,
    STANDARD_MANUAL_REVIEW_ITEMS,
    get_default_config,
    get_manual_review_checklist,
)

from .knowledge import (
    KNOWLEDGE_BASE,
    RegulatoryKnowledgeBase,
    LegalOrigin,
    VerificationStatus,
    RuleCategory,
    SourceCitation,
    RegulatoryRule,
    AccuracyClassDefinition,
    GATCRoutingDecision,
    evaluate_gatc_routing,
)

from .classification_validator import (
    ClassificationValidationIssue,
    ClassificationValidationResult,
    RegulatoryClassificationValidator,
    validate_classification,
)

from .api import (
    validate_instrument_api,
    calculate_mpe_api,
    determine_applicable_tests_api,
    generate_test_plan_api,
    get_regulatory_profile_api,
    get_rule_or_source_api,
    RegulatoryAPI,
    success_response,
    error_response,
)

from .profile import (
    ProfileStatus,
    RuleAuditTrace,
    RegulatoryProfile,
    RegulatoryProfileRegistry,
    PROFILE_REGISTRY,
    DEFAULT_INDIAN_LM_PROFILE,
    DRAFT_GSR_568E_PROFILE,
    SUPERSEDED_LM_2009_PROFILE,
    INTERNATIONAL_OIML_PROFILE,
    STATE_MAHARASHTRA_PROFILE,
)

__all__ = [
    # Regulatory Profile & Rule Versioning
    "ProfileStatus",
    "RuleAuditTrace",
    "RegulatoryProfile",
    "RegulatoryProfileRegistry",
    "PROFILE_REGISTRY",
    "DEFAULT_INDIAN_LM_PROFILE",
    "DRAFT_GSR_568E_PROFILE",
    "SUPERSEDED_LM_2009_PROFILE",
    "INTERNATIONAL_OIML_PROFILE",
    "STATE_MAHARASHTRA_PROFILE",
    # Models
    "AccuracyClass",
    "ApplicableTest",
    "InstrumentProfile",
    "JobType",
    "MassUnit",
    "MPEValue",
    "ReceptorType",
    "TestPlan",
    "TestPoint",
    "TestType",
    "WeighingRange",
    # Errors & Results
    "IssueSeverity",
    "RegulatoryErrorCode",
    "RegulatoryIssue",
    "RegulatoryValidationError",
    "ValidationResult",
    # Sources & Registry
    "Jurisdiction",
    "RegulatoryRegistry",
    "RegulatorySource",
    "StandardStatus",
    "REGULATORY_REGISTRY",
    # Accuracy Class
    "CLASS_BOUNDARIES",
    "ClassBoundary",
    "determine_eligible_classes",
    "get_class_boundary",
    "validate_accuracy_class",
    # Scale Validation
    "is_valid_scale_interval_form",
    "validate_auxiliary_device",
    "validate_instrument_scales",
    "validate_multi_interval",
    # MPE Calculation
    "MPE_STEPS_BY_CLASS",
    "MPEStep",
    "calculate_mpe",
    "calculate_mpe_in_e",
    "get_effective_e_for_load",
    "get_mpe_breakpoints_for_instrument",
    "is_error_within_mpe",
    "MPEBandDefinition",
    "MPECalculationResult",
    "MPEEngine",
    "MPE_STATUTORY_TABLE",
    "VerificationType",
    "calculate_mpe_statutory",
    "DigitalIndicationErrorResult",
    "calculate_digital_indication_error",
    # Applicability
    "get_applicable_tests",
    "is_test_applicable",
    "IndicationType",
    "InstrumentCharacteristics",
    "InstrumentIndicationMode",
    "StatutoryTestDefinition",
    "TestEvaluationResult",
    "ApplicabilityReport",
    "ALL_STATUTORY_TESTS",
    "RegulatoryTestApplicabilityEngine",
    "evaluate_test_applicability",
    # Test Plan Generator
    "generate_discrimination_points",
    "generate_eccentricity_points",
    "generate_repeatability_points",
    "generate_tare_points",
    "generate_test_plan",
    "generate_weighing_points",
    "RegulatoryTestPlanGenerator",
    "GeneratedTestPlan",
    "TestLoadPoint",
    "ExecutableTestItem",
    "generate_regulatory_test_plan",
    # Configuration & Review
    "ManualReviewItem",
    "RegulatoryConfig",
    "STANDARD_MANUAL_REVIEW_ITEMS",
    "get_default_config",
    "get_manual_review_checklist",
    # Knowledge Base
    "KNOWLEDGE_BASE",
    "RegulatoryKnowledgeBase",
    "LegalOrigin",
    "VerificationStatus",
    "RuleCategory",
    "SourceCitation",
    "RegulatoryRule",
    "AccuracyClassDefinition",
    "GATCRoutingDecision",
    "evaluate_gatc_routing",
    # Classification Validator
    "ClassificationValidationIssue",
    "ClassificationValidationResult",
    "RegulatoryClassificationValidator",
    "validate_classification",
    # API Layer & Facade (Person 1 Integration)
    "validate_instrument_api",
    "calculate_mpe_api",
    "determine_applicable_tests_api",
    "generate_test_plan_api",
    "get_regulatory_profile_api",
    "get_rule_or_source_api",
    "RegulatoryAPI",
    "success_response",
    "error_response",
]
