"""
MetrIQ Master API Router
Aggregates all sub-system routers (Regulatory, Instruments, Test Engine, Reports, etc.)
for integration by Person 1 (Team Lead).
"""

from typing import Dict, Any, Optional

try:
    from fastapi import APIRouter
    from app.regulatory.router import router as regulatory_router
    from app.api.instruments_router import router as instruments_router
    from app.api.jobs_router import router as jobs_router
    from app.reports.router import router as reports_router

    api_router = APIRouter()
    if regulatory_router:
        api_router.include_router(regulatory_router)
    if instruments_router:
        api_router.include_router(instruments_router)
    if jobs_router:
        api_router.include_router(jobs_router)
    if reports_router:
        api_router.include_router(reports_router)
except ImportError:
    api_router = None

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
]
