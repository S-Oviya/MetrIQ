"""
MetrIQ P5 Test-Job Workflow Models
==================================
Person 5: Workflow + Evidence Engineer

Defines domain models, enums, and schemas for NAWI test job lifecycle state management.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from app.jobs.models import JobStatus, JobStateTransitionRecord, TestJob

__all__ = [
    "JobStatus",
    "JobStateTransitionRecord",
    "TestJob",
]
