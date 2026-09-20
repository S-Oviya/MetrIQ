"""
MetrIQ Test Execution Integration Module
=========================================
Bridges the P4 calculation engine with the P5 attempt tracker and workflow,
providing a single transactional API for submitting observations and
receiving PASS/FAIL verdicts that are automatically persisted.
"""

from .service import (
    TestExecutionService,
    TEST_EXECUTION_SERVICE,
    ExecutionJobNotFoundError,
    ExecutionJobStateError,
    ExecutionInstrumentError,
    ExecutionValidationError,
)

__all__ = [
    "TestExecutionService",
    "TEST_EXECUTION_SERVICE",
    "ExecutionJobNotFoundError",
    "ExecutionJobStateError",
    "ExecutionInstrumentError",
    "ExecutionValidationError",
]
