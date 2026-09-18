"""
MetrIQ Regulatory Engine - Regulatory Errors & Issues
Defines standard error codes, issue containers, exceptions, and validation result models
aligned with OIML R 76-1:2006 and Indian Legal Metrology (General) Rules, 2011.
"""

from dataclasses import dataclass, field as dataclass_field, asdict
from enum import Enum
from typing import List, Dict, Any, Optional


class IssueSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class RegulatoryErrorCode(str, Enum):
    # Scale interval errors
    INVALID_SCALE_INTERVAL_FORM = "REG_ERR_SCALE_INTERVAL_FORM"  # e != 1, 2, 5 * 10^k
    INVALID_AUXILIARY_DEVICE = "REG_ERR_AUXILIARY_DEVICE"        # d > e, e > 10d, or aux on Class III/IIII
    SCALE_INTERVAL_MISMATCH = "REG_ERR_SCALE_INTERVAL_MISMATCH"

    # Capacity and Range errors
    MIN_CAPACITY_VIOLATION = "REG_ERR_MIN_CAPACITY"              # Min < required (100e, 50e, 20e, 10e)
    MAX_LESS_THAN_MIN = "REG_ERR_MAX_LESS_THAN_MIN"              # Max <= Min
    N_OUT_OF_BOUNDS = "REG_ERR_N_OUT_OF_BOUNDS"                  # n < n_min or n > n_max for class
    N_CALCULATION_MISMATCH = "REG_ERR_N_MISMATCH"

    # Accuracy Class errors
    INVALID_ACCURACY_CLASS = "REG_ERR_INVALID_ACCURACY_CLASS"
    CLASS_CAPACITY_INCOMPATIBLE = "REG_ERR_CLASS_INCOMPATIBLE"

    # Multi-Interval / Multi-Range errors
    MULTI_INTERVAL_INVALID = "REG_ERR_MULTI_INTERVAL_INVALID"
    PARTIAL_RANGE_ORDERING = "REG_ERR_PARTIAL_RANGE_ORDERING"

    # Test and Load errors
    INVALID_LOAD_VALUE = "REG_ERR_INVALID_LOAD"
    LOAD_EXCEEDS_CAPACITY = "REG_ERR_LOAD_EXCEEDS_CAPACITY"
    ECCENTRICITY_LOAD_INVALID = "REG_ERR_ECCENTRICITY_LOAD"
    TARE_VALUE_INVALID = "REG_ERR_TARE_INVALID"

    # Job & Standards errors
    INVALID_JOB_TYPE = "REG_ERR_INVALID_JOB_TYPE"
    REGULATORY_SOURCE_NOT_FOUND = "REG_ERR_SOURCE_NOT_FOUND"
    INVALID_CONFIGURATION = "REG_ERR_INVALID_CONFIG"

    # Warnings & Discretionary review
    MARGINAL_COMPLIANCE = "REG_WARN_MARGINAL_COMPLIANCE"
    MANUAL_REVIEW_REQUIRED = "REG_WARN_MANUAL_REVIEW"
    ENVIRONMENT_LIMIT_WARNING = "REG_WARN_ENVIRONMENT_LIMIT"


@dataclass
class RegulatoryIssue:
    """
    Structured representation of a metrological compliance issue, warning, or manual review trigger.
    """
    code: RegulatoryErrorCode
    message: str
    field: Optional[str] = None
    severity: IssueSeverity = IssueSeverity.ERROR
    reference_clause: Optional[str] = None
    regulatory_standard: Optional[str] = None
    suggestion: Optional[str] = None
    metadata: Dict[str, Any] = dataclass_field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code.value if isinstance(self.code, Enum) else self.code,
            "message": self.message,
            "field": self.field,
            "severity": self.severity.value if isinstance(self.severity, Enum) else self.severity,
            "reference_clause": self.reference_clause,
            "regulatory_standard": self.regulatory_standard,
            "suggestion": self.suggestion,
            "metadata": self.metadata,
        }


@dataclass
class ValidationResult:
    """
    Container for metrological validation outcomes.
    Holds boolean validity, error lists, warning lists, and manual inspection flags.
    """
    is_valid: bool = True
    issues: List[RegulatoryIssue] = dataclass_field(default_factory=list)
    metadata: Dict[str, Any] = dataclass_field(default_factory=dict)

    def add_issue(self, issue: RegulatoryIssue) -> None:
        self.issues.append(issue)
        if issue.severity == IssueSeverity.ERROR:
            self.is_valid = False

    def add_error(
        self,
        code: RegulatoryErrorCode,
        message: str,
        field: Optional[str] = None,
        reference_clause: Optional[str] = None,
        suggestion: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.add_issue(
            RegulatoryIssue(
                code=code,
                message=message,
                field=field,
                severity=IssueSeverity.ERROR,
                reference_clause=reference_clause,
                suggestion=suggestion,
                metadata=metadata or {},
            )
        )

    def add_warning(
        self,
        code: RegulatoryErrorCode,
        message: str,
        field: Optional[str] = None,
        reference_clause: Optional[str] = None,
        suggestion: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.add_issue(
            RegulatoryIssue(
                code=code,
                message=message,
                field=field,
                severity=IssueSeverity.WARNING,
                reference_clause=reference_clause,
                suggestion=suggestion,
                metadata=metadata or {},
            )
        )

    def add_manual_review(
        self,
        code: RegulatoryErrorCode,
        message: str,
        field: Optional[str] = None,
        reference_clause: Optional[str] = None,
        suggestion: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.add_issue(
            RegulatoryIssue(
                code=code,
                message=message,
                field=field,
                severity=IssueSeverity.MANUAL_REVIEW,
                reference_clause=reference_clause,
                suggestion=suggestion,
                metadata=metadata or {},
            )
        )

    @property
    def errors(self) -> List[RegulatoryIssue]:
        return [i for i in self.issues if i.severity == IssueSeverity.ERROR]

    @property
    def warnings(self) -> List[RegulatoryIssue]:
        return [i for i in self.issues if i.severity == IssueSeverity.WARNING]

    @property
    def manual_reviews(self) -> List[RegulatoryIssue]:
        return [i for i in self.issues if i.severity == IssueSeverity.MANUAL_REVIEW]

    def raise_if_invalid(self) -> None:
        if not self.is_valid:
            error_msgs = "; ".join(e.message for e in self.errors)
            raise RegulatoryValidationError(f"Regulatory validation failed: {error_msgs}", result=self)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "manual_review_count": len(self.manual_reviews),
            "issues": [i.to_dict() for i in self.issues],
            "metadata": self.metadata,
        }


class RegulatoryValidationError(Exception):
    """
    Raised when metrological validation strictly fails and execution cannot proceed.
    """
    def __init__(self, message: str, result: Optional[ValidationResult] = None):
        super().__init__(message)
        self.result = result or ValidationResult(is_valid=False)
