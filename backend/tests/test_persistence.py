"""
MetrIQ SQLite Persistence Test Suite
====================================
Validates that instruments, test jobs, test attempts, reviews, reports,
and audit logs persist in SQLite across repository re-instantiations,
and that PDF reports persist on the local filesystem.
"""

import os
import uuid
import pytest
from datetime import datetime, timezone

from app.database.connection import init_db, db_session, get_reports_dir
from app.instruments.models import Instrument, InstrumentStatus, ApprovalStatus
from app.instruments.registry import InstrumentRegistry
from app.jobs.models import TestJob, JobStatus, JobPriority
from app.jobs.repository import TestJobRepository
from app.regulatory.models import JobType, AccuracyClass, MassUnit
from app.attempts.models import TestAttempt, AttemptStatus
from app.attempts.repository import AttemptRepository
from app.review.models import Review, ReviewDecision, ReviewStatus
from app.review.repository import ReviewRepository
from app.reports.repository import ReportRepository
from app.reports.service import ReportService
from app.audit.models import AuditLog, AuditAction, EntityType
from app.audit.repository import AuditRepository, AuditImmutabilityError


@pytest.fixture
def temp_db_env(monkeypatch, tmp_path):
    """Configures a temporary SQLite database and reports folder for isolation."""
    db_file = tmp_path / "test_metriq.db"
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("METRIQ_DB_PATH", str(db_file))
    monkeypatch.setenv("METRIQ_REPORTS_DIR", str(reports_dir))

    init_db()
    yield str(db_file), str(reports_dir)


def test_sqlite_db_initialization(temp_db_env):
    """Verifies that init_db creates all required tables and WAL mode."""
    db_file, _ = temp_db_env
    assert os.path.exists(db_file)

    with db_session() as conn:
        tables = [
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        assert "instruments" in tables
        assert "jobs" in tables
        assert "test_attempts" in tables
        assert "retest_requests" in tables
        assert "reviews" in tables
        assert "reports" in tables
        assert "audit_logs" in tables


def test_instrument_persistence_across_instances(temp_db_env):
    """Verifies that an instrument saved in one registry instance is reloaded in a new instance."""
    inst_id = f"INST-TEST-{uuid.uuid4().hex[:6]}"
    instrument = Instrument(
        instrument_id=inst_id,
        serial_number=f"SN-{uuid.uuid4().hex[:6]}",
        manufacturer="Mettler Toledo",
        model_name="XP-205",
        accuracy_class=AccuracyClass.CLASS_II,
        max_capacity=220.0,
        min_capacity=0.01,
        e=0.001,
        d=0.0001,
        unit=MassUnit.G,
        status=InstrumentStatus.ACTIVE,
        approval_status=ApprovalStatus.APPROVED,
    )

    reg1 = InstrumentRegistry(persistent=True)
    reg1.register(instrument)

    assert reg1.exists(inst_id)
    loaded1 = reg1.get(inst_id)
    assert loaded1 is not None
    assert loaded1.manufacturer == "Mettler Toledo"

    # Simulate backend restart with a new persistent registry instance
    reg2 = InstrumentRegistry(persistent=True)
    assert reg2.exists(inst_id)
    loaded2 = reg2.get(inst_id)
    assert loaded2 is not None
    assert loaded2.instrument_id == inst_id
    assert loaded2.model_name == "XP-205"
    assert loaded2.max_capacity == 220.0


def test_job_persistence_across_instances(temp_db_env):
    """Verifies that a job saved in one repository instance is reloaded in a new instance."""
    job_id = f"JOB-TEST-{uuid.uuid4().hex[:6]}"
    inst_id = f"INST-JOB-{uuid.uuid4().hex[:6]}"
    job = TestJob(
        job_id=job_id,
        job_number="JOB/2026/PERSIST",
        instrument_id=inst_id,
        job_type=JobType.INITIAL_VERIFICATION,
        status=JobStatus.DRAFT,
        priority=JobPriority.NORMAL,
        assigned_inspector_id="INSP-01",
        assigned_inspector_name="Inspector Morse",
    )

    repo1 = TestJobRepository(persistent=True)
    repo1.save(job)
    assert repo1.exists(job_id)

    # Simulate restart
    repo2 = TestJobRepository(persistent=True)
    assert repo2.exists(job_id)
    loaded = repo2.get(job_id)
    assert loaded is not None
    assert loaded.job_id == job_id
    assert loaded.assigned_inspector_name == "Inspector Morse"

    # Query by instrument
    inst_jobs = repo2.get_by_instrument(inst_id)
    assert len(inst_jobs) == 1
    assert inst_jobs[0].job_id == job_id


def test_attempt_persistence_across_instances(temp_db_env):
    """Verifies test attempts and retest requests persist across repository reloads."""
    attempt_id = f"ATT-{uuid.uuid4().hex[:6]}"
    job_id = f"JOB-ATT-{uuid.uuid4().hex[:6]}"
    attempt = TestAttempt(
        id=attempt_id,
        job_id=job_id,
        test_id="repeatability",
        attempt_number=1,
        status=AttemptStatus.COMPLETED,
        entered_values={"readings": [100.0, 100.01, 100.0]},
        comments="Initial test run complete",
    )

    repo1 = AttemptRepository()
    repo1.save_attempt(attempt)
    assert repo1.get_attempt(attempt_id) is not None

    # Simulate restart
    repo2 = AttemptRepository()
    loaded = repo2.get_attempt(attempt_id)
    assert loaded is not None
    assert loaded.id == attempt_id
    assert loaded.job_id == job_id
    assert loaded.test_id == "repeatability"
    assert loaded.entered_values["readings"] == [100.0, 100.01, 100.0]

    by_job = repo2.get_attempts_by_job(job_id)
    assert len(by_job) == 1
    assert by_job[0].id == attempt_id


def test_review_persistence_across_instances(temp_db_env):
    """Verifies review records persist across repository reloads."""
    review_id = f"REV-{uuid.uuid4().hex[:6]}"
    job_id = f"JOB-REV-{uuid.uuid4().hex[:6]}"
    review = Review(
        id=review_id,
        job_id=job_id,
        reviewer="REV-OFFICER-01",
        decision=ReviewDecision.APPROVE,
        status=ReviewStatus.COMPLETED,
        comments="All legal metrology tolerances met.",
        reviewed_at=datetime.now(timezone.utc).isoformat(),
    )

    repo1 = ReviewRepository()
    repo1.save(review)
    assert repo1.get(review_id) is not None

    # Simulate restart
    repo2 = ReviewRepository()
    loaded = repo2.get(review_id)
    assert loaded is not None
    assert loaded.id == review_id
    assert loaded.job_id == job_id
    assert loaded.reviewer == "REV-OFFICER-01"
    assert loaded.decision == ReviewDecision.APPROVE

    by_job = repo2.get_by_job(job_id)
    assert len(by_job) == 1
    assert by_job[0].id == review_id


def test_report_and_pdf_filesystem_persistence(temp_db_env):
    """Verifies report metadata is persisted in SQLite and PDF bytes are stored on disk."""
    _, reports_dir = temp_db_env
    report_id = f"REP-{uuid.uuid4().hex[:6]}"
    job_id = f"JOB-REP-{uuid.uuid4().hex[:6]}"
    dummy_pdf = b"%PDF-1.4 Mock PDF Content for Persistence Test"

    report_record = {
        "report_id": report_id,
        "report_number": f"METRIQ/2026/{report_id}",
        "job_id": job_id,
        "instrument_id": "INST-01",
        "report_type": "VERIFICATION_CERTIFICATE",
        "status": "ISSUED",
        "generation_status": "GENERATED",
        "has_pdf": True,
        "pdf_filename": f"{report_id}.pdf",
    }

    repo1 = ReportRepository(persistent=True)
    repo1.save(report_record)
    assert repo1.get(report_id) is not None

    # Save PDF file to disk
    pdf_path = get_reports_dir() / f"{report_id}.pdf"
    pdf_path.write_bytes(dummy_pdf)
    assert os.path.exists(pdf_path)

    # Simulate restart
    repo2 = ReportRepository(persistent=True)
    loaded_report = repo2.get(report_id)
    assert loaded_report is not None
    assert loaded_report["report_id"] == report_id
    assert loaded_report["status"] == "ISSUED"

    service = ReportService(repository=repo2)
    pdf_bytes = service.get_pdf(report_id)
    assert pdf_bytes == dummy_pdf


def test_audit_log_persistence_and_immutability(temp_db_env):
    """Verifies audit events persist across reloads and cannot be modified or deleted."""
    event_id = f"AUD-{uuid.uuid4().hex[:6]}"
    log = AuditLog(
        id=event_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        user_id="ACTOR-99",
        action=AuditAction.TEST_ATTEMPT_COMPLETED,
        entity_type=EntityType.JOB,
        entity_id="JOB-12345",
        metadata={"result": "PASS", "job_id": "JOB-12345"},
    )

    repo1 = AuditRepository()
    repo1.record(log)
    events1 = repo1.get_by_job("JOB-12345")
    assert len(events1) == 1

    # Simulate restart
    repo2 = AuditRepository()
    events2 = repo2.get_by_job("JOB-12345")
    assert len(events2) == 1
    assert events2[0].id == event_id
    assert events2[0].action == AuditAction.TEST_ATTEMPT_COMPLETED
    assert events2[0].metadata["result"] == "PASS"

    # Immutability verification: delete and update must raise AuditImmutabilityError
    with pytest.raises(AuditImmutabilityError):
        repo2.delete(event_id)

    with pytest.raises(AuditImmutabilityError):
        repo2.update(event_id, {})
