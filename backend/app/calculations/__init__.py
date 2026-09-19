"""
MetrIQ P4: Test Engine + Calculations Package
=============================================
Person 4: Rachitha (Test Engine + Calculations Lead)

Exposes the complete metrological calculation engine for Non-Automatic
Weighing Instruments (NAWI) per OIML R 76-1:2006 and Indian Legal Metrology Rules, 2011.
"""

from app.calculations.models import (
    ChecklistItem,
    ChecklistStatus,
    RawObservation,
    TestDefinition,
    TestExecutionResult,
    TestRun,
    TestType,
    Verdict,
)
from app.calculations.mpe import (
    MPEAdapter,
    MPEEvaluationResult,
    RegulatoryMPELimit,
)
from app.calculations.weighing import (
    WeighingPerformanceCalculator,
    WeighingPointResult,
    WeighingTestResult,
)
from app.calculations.eccentricity import (
    EccentricityCalculator,
    EccentricityPositionResult,
    EccentricityTestResult,
)
from app.calculations.repeatability import (
    RepeatabilityCalculator,
    RepeatabilitySeriesResult,
    RepeatabilityTestResult,
)
from app.calculations.zero_return import (
    ZeroReturnCalculator,
    ZeroReturnTestResult,
)
from app.calculations.creep import (
    CreepCalculator,
    CreepTestResult,
    CreepTimeObservation,
)
from app.calculations.discrimination import (
    DiscriminationCalculator,
    DiscriminationPointResult,
    DiscriminationTestResult,
)
from app.calculations.tare import (
    NetWeighingPointResult,
    TareCalculator,
    TareSettingResult,
    TareTestResult,
)
from app.calculations.temperature import (
    TemperatureCalculator,
    TemperatureChamberPoint,
    TemperatureTestResult,
    ZeroDriftPairResult,
)
from app.calculations.examination import (
    ExaminationCalculator,
    ExaminationTestResult,
)
from app.calculations.engine import (
    STANDARD_CLAUSES,
    TestEngine,
)
from app.calculations.service import (
    CalculationService,
    calculate_mpe_service,
    execute_test_service,
)
from app.calculations.router import router as calculations_router

__all__ = [
    # Core models
    "Verdict",
    "TestType",
    "ChecklistStatus",
    "ChecklistItem",
    "RawObservation",
    "TestDefinition",
    "TestRun",
    "TestExecutionResult",
    # MPE P2 Adapter
    "MPEAdapter",
    "RegulatoryMPELimit",
    "MPEEvaluationResult",
    # 10 NAWI Calculators & Results
    "WeighingPerformanceCalculator",
    "WeighingPointResult",
    "WeighingTestResult",
    "EccentricityCalculator",
    "EccentricityPositionResult",
    "EccentricityTestResult",
    "RepeatabilityCalculator",
    "RepeatabilitySeriesResult",
    "RepeatabilityTestResult",
    "ZeroReturnCalculator",
    "ZeroReturnTestResult",
    "CreepCalculator",
    "CreepTestResult",
    "CreepTimeObservation",
    "DiscriminationCalculator",
    "DiscriminationPointResult",
    "DiscriminationTestResult",
    "TareCalculator",
    "TareSettingResult",
    "NetWeighingPointResult",
    "TareTestResult",
    "TemperatureCalculator",
    "TemperatureChamberPoint",
    "ZeroDriftPairResult",
    "TemperatureTestResult",
    "ExaminationCalculator",
    "ExaminationTestResult",
    # Test Engine & Service
    "TestEngine",
    "STANDARD_CLAUSES",
    "CalculationService",
    "calculate_mpe_service",
    "execute_test_service",
    # Router
    "calculations_router",
]
