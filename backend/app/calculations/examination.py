"""
MetrIQ P4: Examination Tests (Construction & Software)
======================================================
Person 4: Rachitha (Test Engine + Calculations Lead)

Statutory Reference:
- Construction: OIML R 76-1:2006 Clause 3.9, Clause 4, Clause 7.1
- Software: OIML R 76-1:2006 Clause 5.5 & WELMEC Guide 7.2

Implements structured checklist and integrity verification models for
qualitative examination tests without inventing fictitious numerical formulas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.calculations.models import (
    ChecklistItem,
    ChecklistStatus,
    TestType,
    Verdict,
)


# Standard Statutory Construction Examination Checklist Items
DEFAULT_CONSTRUCTION_CHECKLIST = [
    {
        "item_id": "CONST-01",
        "title": "Descriptive Markings & Inscription Plate",
        "clause": "OIML R 76-1:2006 Clause 7.1",
        "is_mandatory": True,
    },
    {
        "item_id": "CONST-02",
        "title": "Leveling Device & Sensitivity Indicator",
        "clause": "OIML R 76-1:2006 Clause 3.9.1.1",
        "is_mandatory": True,
    },
    {
        "item_id": "CONST-03",
        "title": "Security Sealing & Stamping Provisions",
        "clause": "OIML R 76-1:2006 Clause 3.9.4",
        "is_mandatory": True,
    },
    {
        "item_id": "CONST-04",
        "title": "Fraud Prevention & Non-Invertible Receptors",
        "clause": "OIML R 76-1:2006 Clause 4.1.1",
        "is_mandatory": True,
    },
    {
        "item_id": "CONST-05",
        "title": "Stability & Rigidity of Support",
        "clause": "OIML R 76-1:2006 Clause 3.9.3",
        "is_mandatory": True,
    },
]

# Standard Statutory Software Examination Checklist Items
DEFAULT_SOFTWARE_CHECKLIST = [
    {
        "item_id": "SOFT-01",
        "title": "Software Identification & Exact Version Match",
        "clause": "OIML R 76-1:2006 Clause 5.5.1",
        "is_mandatory": True,
    },
    {
        "item_id": "SOFT-02",
        "title": "Software Cryptographic Hash / Checksum Verification",
        "clause": "OIML R 76-1:2006 Clause 5.5.1",
        "is_mandatory": True,
    },
    {
        "item_id": "SOFT-03",
        "title": "Metrological Separation of Software Components",
        "clause": "OIML R 76-1:2006 Clause 5.5.2.1",
        "is_mandatory": True,
    },
    {
        "item_id": "SOFT-04",
        "title": "Parameter Protection & Audit Trail Event Logger",
        "clause": "OIML R 76-1:2006 Clause 5.5.2.2",
        "is_mandatory": True,
    },
    {
        "item_id": "SOFT-05",
        "title": "Storage of Legally Relevant Measurement Records",
        "clause": "OIML R 76-1:2006 Clause 5.5.3",
        "is_mandatory": True,
    },
]


@dataclass
class ExaminationTestResult:
    """Evaluation result for checklist examination tests."""
    test_type: TestType
    verdict: Verdict
    summary: str
    items: List[ChecklistItem]
    total_items: int
    compliant_count: int
    non_compliant_count: int
    not_applicable_count: int
    non_compliant_items: List[Dict[str, Any]]
    software_version_match: Optional[bool] = None
    software_hash_match: Optional[bool] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_type": self.test_type.value,
            "verdict": self.verdict.value,
            "summary": self.summary,
            "items": [i.to_dict() for i in self.items],
            "total_items": self.total_items,
            "compliant_count": self.compliant_count,
            "non_compliant_count": self.non_compliant_count,
            "not_applicable_count": self.not_applicable_count,
            "non_compliant_items": self.non_compliant_items,
            "software_version_match": self.software_version_match,
            "software_hash_match": self.software_hash_match,
            "metadata": self.metadata,
        }


class ExaminationCalculator:
    """
    Evaluates qualitative examination observations for Construction and Software tests.
    """

    @classmethod
    def evaluate_construction(
        cls,
        checklist_items: List[Dict[str, Any]],
    ) -> ExaminationTestResult:
        """
        Evaluates physical construction examination checklist.
        """
        if not checklist_items:
            raise ValueError("Construction examination checklist items cannot be empty.")

        parsed_items: List[ChecklistItem] = []
        non_compliant: List[Dict[str, Any]] = []
        compliant_cnt = 0
        non_compliant_cnt = 0
        na_cnt = 0

        for itm in checklist_items:
            chk = itm if isinstance(itm, ChecklistItem) else ChecklistItem.from_dict(itm)
            parsed_items.append(chk)

            if chk.status == ChecklistStatus.COMPLIANT:
                compliant_cnt += 1
            elif chk.status == ChecklistStatus.NOT_APPLICABLE:
                na_cnt += 1
            else:
                non_compliant_cnt += 1
                if chk.is_mandatory:
                    non_compliant.append(chk.to_dict())

        verdict = Verdict.FAIL if non_compliant else Verdict.PASS
        summary = (
            f"Construction Examination {verdict.value}: {compliant_cnt} compliant, "
            f"{non_compliant_cnt} non-compliant, {na_cnt} not applicable."
        )

        return ExaminationTestResult(
            test_type=TestType.CONSTRUCTION_EXAMINATION,
            verdict=verdict,
            summary=summary,
            items=parsed_items,
            total_items=len(parsed_items),
            compliant_count=compliant_cnt,
            non_compliant_count=non_compliant_cnt,
            not_applicable_count=na_cnt,
            non_compliant_items=non_compliant,
        )

    @classmethod
    def evaluate_software(
        cls,
        checklist_items: List[Dict[str, Any]],
        expected_version: Optional[str] = None,
        observed_version: Optional[str] = None,
        expected_hash: Optional[str] = None,
        observed_hash: Optional[str] = None,
    ) -> ExaminationTestResult:
        """
        Evaluates software examination checklist and cryptographic integrity.
        """
        if not checklist_items:
            raise ValueError("Software examination checklist items cannot be empty.")

        parsed_items: List[ChecklistItem] = []
        non_compliant: List[Dict[str, Any]] = []
        compliant_cnt = 0
        non_compliant_cnt = 0
        na_cnt = 0

        for itm in checklist_items:
            chk = itm if isinstance(itm, ChecklistItem) else ChecklistItem.from_dict(itm)
            parsed_items.append(chk)

            if chk.status == ChecklistStatus.COMPLIANT:
                compliant_cnt += 1
            elif chk.status == ChecklistStatus.NOT_APPLICABLE:
                na_cnt += 1
            else:
                non_compliant_cnt += 1
                if chk.is_mandatory:
                    non_compliant.append(chk.to_dict())

        # Version match verification
        version_match = None
        if expected_version is not None and observed_version is not None:
            version_match = expected_version.strip().lower() == observed_version.strip().lower()
            if not version_match:
                non_compliant.append({
                    "item_id": "VERSION_MISMATCH",
                    "title": "Software Version Mismatch",
                    "clause": "OIML R 76-1:2006 Clause 5.5.1",
                    "expected": expected_version,
                    "observed": observed_version,
                })

        # Cryptographic checksum verification
        hash_match = None
        if expected_hash is not None and observed_hash is not None:
            hash_match = expected_hash.strip().lower() == observed_hash.strip().lower()
            if not hash_match:
                non_compliant.append({
                    "item_id": "HASH_MISMATCH",
                    "title": "Software Hash / Checksum Mismatch",
                    "clause": "OIML R 76-1:2006 Clause 5.5.1",
                    "expected": expected_hash,
                    "observed": observed_hash,
                })

        verdict = Verdict.FAIL if non_compliant else Verdict.PASS
        summary = (
            f"Software Examination {verdict.value}: {compliant_cnt} compliant, "
            f"{non_compliant_cnt} non-compliant."
        )
        if version_match is not None:
            summary += f" Version match: {version_match}."
        if hash_match is not None:
            summary += f" Hash match: {hash_match}."

        return ExaminationTestResult(
            test_type=TestType.SOFTWARE_EXAMINATION,
            verdict=verdict,
            summary=summary,
            items=parsed_items,
            total_items=len(parsed_items),
            compliant_count=compliant_cnt,
            non_compliant_count=non_compliant_cnt,
            not_applicable_count=na_cnt,
            non_compliant_items=non_compliant,
            software_version_match=version_match,
            software_hash_match=hash_match,
        )
