"""
MetrIQ Master API Router
Aggregates all sub-system routers (Regulatory, Instruments, Test Engine, Reports, etc.)
for integration by Person 1 (Team Lead).
"""

from typing import Dict, Any, Optional

try:
    from fastapi import APIRouter
    from app.regulatory.router import router as regulatory_router

    api_router = APIRouter()
    if regulatory_router:
        api_router.include_router(regulatory_router)
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

__all__ = [
    "api_router",
    "validate_instrument_api",
    "calculate_mpe_api",
    "determine_applicable_tests_api",
    "generate_test_plan_api",
    "get_regulatory_profile_api",
    "get_rule_or_source_api",
    "RegulatoryAPI",
]
