"""
MetrIQ Test Execution Router
==============================
FastAPI surface for submitting test observations and querying results.

Routes
------
POST /test-execution/submit
    Submit raw observations for a single test type within an IN_PROGRESS job.
    Automatically runs the P4 calculation engine and records the attempt.

GET  /test-execution/{job_id}/results
    Retrieve all completed test attempts for a job, grouped by test type.

GET  /test-execution/attempts/{attempt_id}
    Retrieve a single attempt by ID.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from fastapi import APIRouter, HTTPException, Path, Body
    router = APIRouter(prefix="/test-execution", tags=["Test Execution"])
    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    router = None
    _HAS_FASTAPI = False

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: Any) -> None:
            self.status_code = status_code
            self.detail = detail

    def Body(default: Any = None, **kwargs: Any) -> Any:  # type: ignore[misc]
        return default

    def Path(*args: Any, **kwargs: Any) -> Any:  # type: ignore[misc]
        return None

from app.api.schemas import success_envelope
from app.tests_execution.service import (
    TEST_EXECUTION_SERVICE,
    ExecutionJobNotFoundError,
    ExecutionJobStateError,
    ExecutionInstrumentError,
    ExecutionValidationError,
)


def _handle(result: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap a service result in the standard success envelope."""
    return success_envelope(result)


if router is not None:
    @router.post("/submit")
    def submit_test_observations(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        """
        Submit raw observations for a single statutory test within a job.

        The service will:
          1. Validate the job is IN_PROGRESS
          2. Load the instrument parameters
          3. Run the P4 calculation engine
          4. Record a TestAttempt with the PASS/FAIL verdict
          5. Return the full calculation result

        Required fields:
          - job_id      : The IN_PROGRESS job
          - test_type   : e.g. "WEIGHING_PERFORMANCE", "ECCENTRICITY", …
          - observations: List of RawObservation dicts
          - operator    : Verification officer ID

        Optional:
          - notes    : Free-text comment
          - metadata : Forwarded to the test run
        """
        job_id = str(payload.get("job_id") or "").strip()
        test_type = str(payload.get("test_type") or "").strip()
        observations = payload.get("observations") or []
        operator = str(payload.get("operator") or "").strip()
        notes = str(payload.get("notes") or "")
        metadata = payload.get("metadata")

        if not job_id:
            raise HTTPException(status_code=422, detail={"message": "job_id is required."})
        if not test_type:
            raise HTTPException(status_code=422, detail={"message": "test_type is required."})
        if not operator:
            raise HTTPException(status_code=422, detail={"message": "operator is required."})
        if not isinstance(observations, list):
            raise HTTPException(status_code=422, detail={"message": "observations must be a list."})

        try:
            result = TEST_EXECUTION_SERVICE.submit_observations(
                job_id=job_id,
                test_type=test_type,
                observations=observations,
                operator=operator,
                notes=notes,
                metadata=metadata,
            )
            return _handle(result)
        except ExecutionJobNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"message": str(exc)})
        except ExecutionJobStateError as exc:
            raise HTTPException(status_code=409, detail={"message": str(exc)})
        except ExecutionInstrumentError as exc:
            raise HTTPException(status_code=409, detail={"message": str(exc)})
        except ExecutionValidationError as exc:
            raise HTTPException(status_code=422, detail={"message": str(exc)})
        except Exception as exc:
            raise HTTPException(status_code=500, detail={"message": f"Internal error: {exc}"})

    @router.get("/{job_id}/results")
    def get_job_test_results(job_id: str = Path(...)) -> Dict[str, Any]:
        """
        Return all test attempts for a job, grouped by test type.

        Provides the reviewer with a complete picture of which tests have
        been executed, how many attempts were made, and the current verdict
        for each test type.
        """
        try:
            result = TEST_EXECUTION_SERVICE.get_results_for_job(job_id)
            return _handle(result)
        except ExecutionJobNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"message": str(exc)})
        except Exception as exc:
            raise HTTPException(status_code=500, detail={"message": f"Internal error: {exc}"})

    @router.get("/attempts/{attempt_id}")
    def get_attempt(attempt_id: str = Path(...)) -> Dict[str, Any]:
        """Return a single test attempt by ID."""
        result = TEST_EXECUTION_SERVICE.get_attempt(attempt_id)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail={"message": f"Attempt '{attempt_id}' not found."},
            )
        return _handle(result)
