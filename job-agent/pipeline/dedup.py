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
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    company     TEXT    NOT NULL,
    url         TEXT    NOT NULL,
    jd_text     TEXT,
    source      TEXT,
    posted_date TEXT,
    processed   INTEGER NOT NULL DEFAULT 0,
    ats_score   REAL,
    pdf_path    TEXT,
    status      TEXT    DEFAULT 'pending',
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_company_title ON jobs (company, title);
CREATE INDEX IF NOT EXISTS idx_processed ON jobs (processed);
"""


def _connect(db_path: str = DB_PATH) -> sqlite3.Connection:
    if db_path != ":memory:":
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    """Create the jobs table (and index) if they don't exist."""
    with _connect(db_path) as conn:
        conn.executescript(_SCHEMA)
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
    Insert a new job row.  Returns the new row id.

    Expected keys in job dict:
        title, company, url, source
    Optional keys:
        jd_text, posted_date
    """
    now = datetime.utcnow().isoformat()
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO jobs (title, company, url, jd_text, source, posted_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.get("title", "").strip(),
                job.get("company", "").strip(),
                job.get("url", "").strip(),
                job.get("jd_text"),
                job.get("source"),
                job.get("posted_date"),
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


def get_job(job_id: int, db_path: str = DB_PATH) -> Optional[dict]:
    """Fetch a single job by id."""
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def get_todays_processed_jobs(db_path: str = DB_PATH) -> list[dict]:
    """Return all jobs processed today (UTC date)."""
    today = datetime.utcnow().date().isoformat()
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE processed = 1 AND created_at LIKE ?",
            (f"{today}%",),
        ).fetchall()
    return [dict(row) for row in rows]
