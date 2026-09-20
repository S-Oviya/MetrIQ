"""
MetrIQ Database Foundation & SQLite Connection Manager
======================================================
Provides thread-safe local SQLite persistence with WAL mode, foreign keys,
and connection management for the MetrIQ Verification System.
"""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
from typing import Generator, Optional


# Predictable default file locations
_DEFAULT_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DATA_DIR = _DEFAULT_BASE_DIR / "data"
_DEFAULT_DB_PATH = _DEFAULT_DATA_DIR / "metriq.db"
_DEFAULT_REPORTS_DIR = _DEFAULT_DATA_DIR / "reports"


def get_db_path() -> str:
    """Returns the effective SQLite database path (configurable via METRIQ_DB_PATH)."""
    return os.getenv("METRIQ_DB_PATH", str(_DEFAULT_DB_PATH))


def get_reports_dir() -> Path:
    """Returns the directory for persistent report PDF storage as a Path."""
    rep_dir = Path(os.getenv("METRIQ_REPORTS_DIR", str(_DEFAULT_REPORTS_DIR)))
    os.makedirs(rep_dir, exist_ok=True)
    return rep_dir


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Creates and configures an active SQLite connection.
    Enables WAL mode and foreign key constraints for reliability.
    """
    path = db_path or get_db_path()
    # Ensure directory exists if not in-memory
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    conn = sqlite3.connect(
        path,
        timeout=30.0,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=10000;")
    return conn


@contextmanager
def db_session(db_path: Optional[str] = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager yielding a transactional SQLite connection."""
    conn = get_db_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[str] = None) -> None:
    """
    Initializes the SQLite schema if not already present.
    Safely creates tables and indexes without altering existing data.
    """
    path = db_path or get_db_path()
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    get_reports_dir()

    with db_session(path) as conn:
        cursor = conn.cursor()

        # 1. Instruments Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS instruments (
                instrument_id TEXT PRIMARY KEY,
                serial_number TEXT UNIQUE NOT NULL,
                manufacturer TEXT,
                model_name TEXT,
                model_number TEXT,
                accuracy_class TEXT,
                max_capacity REAL,
                min_capacity REAL,
                e REAL,
                d REAL,
                unit TEXT,
                instrument_type TEXT,
                status TEXT,
                model_approval_number TEXT,
                customer_name TEXT,
                created_at TEXT,
                updated_at TEXT,
                data_json TEXT NOT NULL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inst_serial ON instruments(serial_number);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inst_status ON instruments(status);")

        # 2. Test Jobs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                job_number TEXT,
                instrument_id TEXT NOT NULL,
                status TEXT NOT NULL,
                job_type TEXT NOT NULL,
                priority TEXT,
                assigned_inspector_id TEXT,
                assigned_inspector_name TEXT,
                testing_centre_id TEXT,
                testing_centre_name TEXT,
                created_at TEXT,
                updated_at TEXT,
                data_json TEXT NOT NULL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_inst ON jobs(instrument_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(job_type);")

        # 3. Test Attempts Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_attempts (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                test_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                status TEXT NOT NULL,
                result TEXT,
                operator TEXT,
                started_at TEXT,
                completed_at TEXT,
                data_json TEXT NOT NULL,
                UNIQUE(job_id, test_id, attempt_number)
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_att_job ON test_attempts(job_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_att_job_test ON test_attempts(job_id, test_id);")

        # 4. Retest Requests Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS retest_requests (
                retest_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                test_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                attempt_number INTEGER,
                data_json TEXT NOT NULL,
                requested_at TEXT
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_retest_job ON retest_requests(job_id);")

        # 5. Reviews Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                status TEXT NOT NULL,
                decision TEXT,
                created_at TEXT,
                updated_at TEXT,
                data_json TEXT NOT NULL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rev_job ON reviews(job_id);")

        # 6. Reports Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                report_id TEXT PRIMARY KEY,
                report_number TEXT UNIQUE NOT NULL,
                job_id TEXT,
                instrument_id TEXT,
                serial_number TEXT,
                report_type TEXT NOT NULL,
                status TEXT NOT NULL,
                generation_status TEXT,
                pdf_path TEXT,
                created_at TEXT,
                updated_at TEXT,
                data_json TEXT NOT NULL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rep_num ON reports(report_number);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rep_job ON reports(job_id);")

        # 7. Audit Logs Table (Strictly Append-Only)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id TEXT PRIMARY KEY,
                job_id TEXT,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                created_at TEXT,
                data_json TEXT NOT NULL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_aud_job ON audit_logs(job_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_aud_entity ON audit_logs(entity_type, entity_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_aud_action ON audit_logs(action);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_aud_timestamp ON audit_logs(timestamp);")
