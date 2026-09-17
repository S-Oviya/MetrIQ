"""
MetrIQ Test Jobs Module — Person 3 (Job / Instrument Engineer)
==============================================================
Exposes high-level models, services, and repositories for statutory test job
workflows, GATC routing, and state machine lifecycle transitions.
"""

from .models import (
    JobPriority,
    JobStateTransitionRecord,
    JobStatus,
    JobType,
    StatutoryRoutingInfo,
    TestJob,
    VerificationLocationType,
)
from .location_service import (
    RegulatoryRoutingResult,
    RegulatoryRoutingService,
    REGULATORY_ROUTING_SERVICE,
    JobLocationRoutingResult,
    JobLocationService,
    JOB_LOCATION_SERVICE,
)
from .repository import TEST_JOB_REPOSITORY, TestJobRepository
from .state_machine import JobStateMachine, JobStateTransitionError
from .service import TEST_JOB_SERVICE, TestJobService

__all__ = [
    # Models & Enums
    "JobPriority",
    "JobStateTransitionRecord",
    "JobStatus",
    "JobType",
    "StatutoryRoutingInfo",
    "TestJob",
    "VerificationLocationType",
    # Location & Routing Services
    "RegulatoryRoutingResult",
    "RegulatoryRoutingService",
    "REGULATORY_ROUTING_SERVICE",
    "JobLocationRoutingResult",
    "JobLocationService",
    "JOB_LOCATION_SERVICE",
    # Repository & State Machine
    "TEST_JOB_REPOSITORY",
    "TestJobRepository",
    "JobStateMachine",
    "JobStateTransitionError",
    # Service Facade
    "TEST_JOB_SERVICE",
    "TestJobService",
]
