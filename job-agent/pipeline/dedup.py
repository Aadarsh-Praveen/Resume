"""
SQLite-backed job deduplication and storage.
All job pipeline state lives here.
"""

import sqlite3
import os
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "db/jobs.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    title            TEXT    NOT NULL,
    company          TEXT    NOT NULL,
    url              TEXT    NOT NULL,
    jd_text          TEXT,
    source           TEXT,
    posted_date      TEXT,
    location         TEXT,
    processed        INTEGER NOT NULL DEFAULT 0,
    ats_score        REAL,
    pdf_path         TEXT,
    status           TEXT    DEFAULT 'pending',
    cover_letter     TEXT,
    approval_status  TEXT    DEFAULT 'pending_review',
    applied_at       TEXT,
    application_id   TEXT,
    created_at       TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_company_title    ON jobs (company, title);
CREATE INDEX IF NOT EXISTS idx_processed        ON jobs (processed);
CREATE INDEX IF NOT EXISTS idx_approval_status  ON jobs (approval_status);
"""

_MIGRATIONS = [
    "ALTER TABLE jobs ADD COLUMN location TEXT",
    "ALTER TABLE jobs ADD COLUMN cover_letter TEXT",
    "ALTER TABLE jobs ADD COLUMN approval_status TEXT DEFAULT 'pending_review'",
    "ALTER TABLE jobs ADD COLUMN applied_at TEXT",
    "ALTER TABLE jobs ADD COLUMN application_id TEXT",
]


def _connect(db_path: str = DB_PATH) -> sqlite3.Connection:
    if db_path != ":memory:":
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    """Create the jobs table (and index) if they don't exist, then run migrations."""
    with _connect(db_path) as conn:
        conn.executescript(_SCHEMA)
        for migration in _MIGRATIONS:
            try:
                conn.execute(migration)
            except sqlite3.OperationalError:
                pass  # column already exists
    logger.info("Database initialised at %s", db_path)


def is_duplicate(company: str, title: str, db_path: str = DB_PATH) -> bool:
    """Return True if (company, title) already exists in the database."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM jobs WHERE company = ? AND title = ?",
            (company.strip(), title.strip()),
        ).fetchone()
    return row is not None


def insert_job(job: dict, db_path: str = DB_PATH) -> int:
    """
    Insert a new job row. Returns the new row id.

    Expected keys: title, company, url, source
    Optional keys: jd_text, posted_date, location
    """
    now = datetime.utcnow().isoformat()
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO jobs (title, company, url, jd_text, source, posted_date, location, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.get("title", "").strip(),
                job.get("company", "").strip(),
                job.get("url", "").strip(),
                job.get("jd_text"),
                job.get("source"),
                job.get("posted_date"),
                job.get("location"),
                now,
            ),
        )
        return cursor.lastrowid


def get_unprocessed_jobs(db_path: str = DB_PATH) -> list[dict]:
    """Return all jobs where processed = 0."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE processed = 0 ORDER BY created_at ASC"
        ).fetchall()
    return [dict(row) for row in rows]


def mark_processed(
    job_id: int,
    pdf_path: Optional[str],
    ats_score: Optional[float],
    status: str,
    db_path: str = DB_PATH,
) -> None:
    """Update a job row as processed with outcome data."""
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE jobs
               SET processed = 1,
                   pdf_path  = ?,
                   ats_score = ?,
                   status    = ?
             WHERE id = ?
            """,
            (pdf_path, ats_score, status, job_id),
        )


def set_cover_letter(job_id: int, cover_letter: str, db_path: str = DB_PATH) -> None:
    """Store the generated cover letter for a job."""
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET cover_letter = ? WHERE id = ?",
            (cover_letter, job_id),
        )


def set_approval(job_id: int, approval_status: str, db_path: str = DB_PATH) -> None:
    """Set approval_status: 'pending_review' | 'approved' | 'rejected'."""
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET approval_status = ? WHERE id = ?",
            (approval_status, job_id),
        )


def mark_applied(
    job_id: int,
    application_id: str,
    db_path: str = DB_PATH,
) -> None:
    """Record a successful application submission."""
    now = datetime.utcnow().isoformat()
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE jobs
               SET approval_status = 'applied',
                   applied_at      = ?,
                   application_id  = ?
             WHERE id = ?
            """,
            (now, application_id, job_id),
        )


def get_job(job_id: int, db_path: str = DB_PATH) -> Optional[dict]:
    """Fetch a single job by id."""
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def get_pending_review_jobs(db_path: str = DB_PATH) -> list[dict]:
    """Jobs that have a PDF ready and are awaiting user approval."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM jobs
             WHERE processed = 1
               AND pdf_path IS NOT NULL
               AND approval_status = 'pending_review'
             ORDER BY created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_all_jobs(
    limit: int = 50,
    offset: int = 0,
    approval_status: Optional[str] = None,
    db_path: str = DB_PATH,
) -> list[dict]:
    """Return jobs ordered by newest first, with optional status filter."""
    with _connect(db_path) as conn:
        if approval_status:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE approval_status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (approval_status, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
    return [dict(row) for row in rows]


def get_stats(db_path: str = DB_PATH) -> dict:
    """Return summary counts for the dashboard header."""
    with _connect(db_path) as conn:
        total     = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        pending   = conn.execute("SELECT COUNT(*) FROM jobs WHERE approval_status = 'pending_review' AND processed = 1").fetchone()[0]
        applied   = conn.execute("SELECT COUNT(*) FROM jobs WHERE approval_status = 'applied'").fetchone()[0]
        rejected  = conn.execute("SELECT COUNT(*) FROM jobs WHERE approval_status = 'rejected'").fetchone()[0]
    return {"total": total, "pending": pending, "applied": applied, "rejected": rejected}


def get_todays_processed_jobs(db_path: str = DB_PATH) -> list[dict]:
    """Return all jobs processed today (UTC date)."""
    today = datetime.utcnow().date().isoformat()
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE processed = 1 AND created_at LIKE ?",
            (f"{today}%",),
        ).fetchall()
    return [dict(row) for row in rows]
