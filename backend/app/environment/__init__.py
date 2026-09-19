"""
MetrIQ P5 Environment Package
=============================
Person 5: Workflow + Evidence Engineer

Exports domain models, repository, service, router, and custom exceptions
for environment condition tracking and legal metrology ambient monitoring.
"""

from .models import EnvironmentCondition
from .repository import (
    ENVIRONMENT_REPOSITORY,
    EnvironmentRepository,
)
from .service import (
    ENVIRONMENT_SERVICE,
    EnvironmentNotFoundError,
    EnvironmentService,
    EnvironmentStageError,
    EnvironmentUpdateRestrictedError,
    EnvironmentValidationError,
)
from .router import router

__all__ = [
    "EnvironmentCondition",
    "EnvironmentRepository",
    "ENVIRONMENT_REPOSITORY",
    "EnvironmentService",
    "ENVIRONMENT_SERVICE",
    "EnvironmentValidationError",
    "EnvironmentNotFoundError",
    "EnvironmentStageError",
    "EnvironmentUpdateRestrictedError",
    "router",
]
