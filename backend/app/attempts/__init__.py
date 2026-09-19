"""
MetrIQ P5 Test Attempt & Retest Package
=======================================
Person 5: Workflow + Evidence Engineer

Exports TestAttempt, RetestRequest, AttemptStatus, Verdict,
AttemptRepository, ATTEMPT_REPOSITORY,
AttemptService, ATTEMPT_SERVICE,
custom exceptions, and the REST API router.
"""

from .models import (
    AttemptStatus,
    RetestRequest,
    TestAttempt,
    Verdict,
)
from .repository import (
    ATTEMPT_REPOSITORY,
    AttemptRepository,
    DuplicateAttemptNumberError,
)
from .service import (
    ATTEMPT_SERVICE,
    AttemptAlreadyCompletedError,
    AttemptJobStateError,
    AttemptNotFoundError,
    AttemptService,
    AttemptValidationError,
    TestNotFoundError,
)
from .router import router

__all__ = [
    "TestAttempt",
    "RetestRequest",
    "AttemptStatus",
    "Verdict",
    "AttemptRepository",
    "ATTEMPT_REPOSITORY",
    "DuplicateAttemptNumberError",
    "AttemptService",
    "ATTEMPT_SERVICE",
    "AttemptNotFoundError",
    "TestNotFoundError",
    "AttemptValidationError",
    "AttemptJobStateError",
    "AttemptAlreadyCompletedError",
    "router",
]
