"""
MetrIQ P4: FastAPI Calculations Router
======================================
Person 4: Rachitha (Test Engine + Calculations Lead)

Exposes RESTful endpoints for NAWI test execution and metrological calculations
under the '/calculations' prefix.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from fastapi import APIRouter, Body, HTTPException, Query, status
    HAS_FASTAPI = True
    router = APIRouter(prefix="/calculations", tags=["Test Engine & Calculations"])
    _post = router.post
    _get = router.get
except ImportError:
    HAS_FASTAPI = False
    router = None
    def _noop_dec(*args, **kwargs):
        def wrap(f):
            return f
        return wrap
    _post = _get = _noop_dec
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: Any):
            self.status_code = status_code
            self.detail = detail
            super().__init__(f"HTTP {status_code}: {detail}")

from app.calculations.engine import TestEngine
from app.calculations.models import TestRun
from app.calculations.mpe import MPEAdapter
from app.calculations.weighing import WeighingPerformanceCalculator
from app.calculations.eccentricity import EccentricityCalculator
from app.calculations.repeatability import RepeatabilityCalculator
from app.calculations.zero_return import ZeroReturnCalculator
from app.calculations.creep import CreepCalculator
from app.calculations.discrimination import DiscriminationCalculator
from app.calculations.tare import TareCalculator
from app.calculations.temperature import TemperatureCalculator
from app.calculations.examination import ExaminationCalculator


@_post("/mpe")
def get_statutory_mpe(payload: Dict[str, Any]):
    """
    Calculates statutory Maximum Permissible Error by querying Person 2 Regulatory Engine.
    """
    try:
        load = float(payload["load"])
        acc_class = payload["accuracy_class"]
        e = float(payload["e"])
        v_type = payload.get("verification_type", "INITIAL")
        unit = payload.get("unit", "kg")
        ranges = payload.get("partial_ranges")
        tare = float(payload.get("tare_load", 0.0))

        limit = MPEAdapter.get_mpe(
            load=load,
            accuracy_class=acc_class,
            e=e,
            verification_type=v_type,
            unit=unit,
            partial_ranges=ranges,
            tare_load=tare,
        )
        return {"success": True, "data": limit.to_dict()}
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))


@_post("/execute")
def execute_test_run_endpoint(payload: Dict[str, Any]):
    """
    Executes a complete test run against instrument specifications and returns PASS/FAIL verdict.
    """
    try:
        test_run_dict = payload.get("test_run", payload)
        instrument_dict = payload.get("instrument", {})
        v_type = payload.get("verification_type", "INITIAL")

        test_run = TestRun.from_dict(test_run_dict)
        res = TestEngine.execute(test_run, instrument_dict, v_type)
        return {"success": True, "data": res.to_dict()}
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))


@_post("/weighing")
def calculate_weighing(payload: Dict[str, Any]):
    """Calculates weighing performance test."""
    try:
        observations = payload["observations"]
        acc_class = payload["accuracy_class"]
        e = float(payload["e"])
        v_type = payload.get("verification_type", "INITIAL")
        unit = payload.get("unit", "kg")
        ranges = payload.get("partial_ranges")

        res = WeighingPerformanceCalculator.evaluate_run(
            observations=observations,
            accuracy_class=acc_class,
            e=e,
            verification_type=v_type,
            unit=unit,
            partial_ranges=ranges,
        )
        return {"success": True, "data": res.to_dict()}
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))


@_post("/eccentricity")
def calculate_eccentricity(payload: Dict[str, Any]):
    """Calculates eccentricity test."""
    try:
        observations = payload["observations"]
        acc_class = payload["accuracy_class"]
        e = float(payload["e"])
        v_type = payload.get("verification_type", "INITIAL")
        unit = payload.get("unit", "kg")
        receptor = payload.get("receptor_type", "STANDARD_PLATTER")
        ranges = payload.get("partial_ranges")

        res = EccentricityCalculator.evaluate(
            observations=observations,
            accuracy_class=acc_class,
            e=e,
            verification_type=v_type,
            unit=unit,
            receptor_type=receptor,
            partial_ranges=ranges,
        )
        return {"success": True, "data": res.to_dict()}
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))


@_post("/repeatability")
def calculate_repeatability(payload: Dict[str, Any]):
    """Calculates repeatability test."""
    try:
        observations = payload["observations"]
        acc_class = payload["accuracy_class"]
        e = float(payload["e"])
        v_type = payload.get("verification_type", "INITIAL")
        unit = payload.get("unit", "kg")
        ranges = payload.get("partial_ranges")

        res = RepeatabilityCalculator.evaluate_run(
            observations=observations,
            accuracy_class=acc_class,
            e=e,
            verification_type=v_type,
            unit=unit,
            partial_ranges=ranges,
        )
        return {"success": True, "data": res.to_dict()}
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))


@_post("/zero-return")
def calculate_zero_return(payload: Dict[str, Any]):
    """Calculates zero return test."""
    try:
        observations = payload.get("observations")
        e = float(payload["e"])
        unit = payload.get("unit", "kg")
        ranges = payload.get("partial_ranges")

        if observations:
            res = ZeroReturnCalculator.evaluate_run(
                observations=observations,
                e=e,
                unit=unit,
                partial_ranges=ranges,
            )
        else:
            res = ZeroReturnCalculator.evaluate(
                initial_zero=float(payload.get("initial_zero", 0.0)),
                returned_zero=float(payload["returned_zero"]),
                e=e,
                unit=unit,
                load_applied=float(payload.get("load_applied")) if payload.get("load_applied") is not None else None,
                duration_minutes=float(payload.get("duration_minutes", 30.0)),
                partial_ranges=ranges,
            )
        return {"success": True, "data": res.to_dict()}
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))


@_post("/creep")
def calculate_creep(payload: Dict[str, Any]):
    """Calculates creep test."""
    try:
        load = float(payload["load"])
        time_obs = payload["time_observations"]
        acc_class = payload["accuracy_class"]
        e = float(payload["e"])
        v_type = payload.get("verification_type", "INITIAL")
        unit = payload.get("unit", "kg")
        ranges = payload.get("partial_ranges")

        res = CreepCalculator.evaluate(
            load=load,
            time_observations=time_obs,
            accuracy_class=acc_class,
            e=e,
            verification_type=v_type,
            unit=unit,
            partial_ranges=ranges,
        )
        return {"success": True, "data": res.to_dict()}
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))


@_post("/discrimination")
def calculate_discrimination(payload: Dict[str, Any]):
    """Calculates digital discrimination test."""
    try:
        observations = payload["observations"]
        d = float(payload["d"])
        unit = payload.get("unit", "kg")

        res = DiscriminationCalculator.evaluate_run(
            observations=observations,
            d=d,
            unit=unit,
        )
        return {"success": True, "data": res.to_dict()}
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))


@_post("/tare")
def calculate_tare(payload: Dict[str, Any]):
    """Calculates tare test."""
    try:
        tare_load = float(payload["tare_load"])
        tare_setting_obs = payload["tare_setting_observation"]
        net_obs = payload["net_observations"]
        acc_class = payload["accuracy_class"]
        e = float(payload["e"])
        v_type = payload.get("verification_type", "INITIAL")
        unit = payload.get("unit", "kg")
        ranges = payload.get("partial_ranges")

        res = TareCalculator.evaluate_run(
            tare_load=tare_load,
            tare_setting_observation=tare_setting_obs,
            net_observations=net_obs,
            accuracy_class=acc_class,
            e=e,
            verification_type=v_type,
            unit=unit,
            partial_ranges=ranges,
        )
        return {"success": True, "data": res.to_dict()}
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))


@_post("/temperature")
def calculate_temperature(payload: Dict[str, Any]):
    """Calculates temperature effect test."""
    try:
        observations = payload["observations"]
        acc_class = payload["accuracy_class"]
        e = float(payload["e"])
        v_type = payload.get("verification_type", "INITIAL")
        unit = payload.get("unit", "kg")
        ranges = payload.get("partial_ranges")

        res = TemperatureCalculator.evaluate(
            observations=observations,
            accuracy_class=acc_class,
            e=e,
            verification_type=v_type,
            unit=unit,
            partial_ranges=ranges,
        )
        return {"success": True, "data": res.to_dict()}
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))


@_post("/examination")
def calculate_examination(payload: Dict[str, Any]):
    """Calculates construction or software examination test."""
    try:
        test_type = payload.get("test_type", "CONSTRUCTION_EXAMINATION").upper()
        checklist_items = payload["checklist_items"]

        if "SOFTWARE" in test_type:
            res = ExaminationCalculator.evaluate_software(
                checklist_items=checklist_items,
                expected_version=payload.get("expected_version"),
                observed_version=payload.get("observed_version"),
                expected_hash=payload.get("expected_hash"),
                observed_hash=payload.get("observed_hash"),
            )
        else:
            res = ExaminationCalculator.evaluate_construction(
                checklist_items=checklist_items
            )
        return {"success": True, "data": res.to_dict()}
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))
