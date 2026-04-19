"""
SQLite-backed job deduplication and storage.
All job pipeline state lives here.
"""

import sqlite3
import os
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "db/jobs.db")

# Base schema — only columns that existed from day 1 (safe for any DB age)
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
CREATE INDEX IF NOT EXISTS idx_processed     ON jobs (processed);
"""

_RECRUITER_SCHEMA = """
CREATE TABLE IF NOT EXISTS recruiters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER NOT NULL,
    name            TEXT,
    title           TEXT,
    company         TEXT    NOT NULL,
    email           TEXT,
    linkedin_url    TEXT,
    cold_email_text TEXT,
    email_sent      INTEGER NOT NULL DEFAULT 0,
    linkedin_sent   INTEGER NOT NULL DEFAULT 0,
    replied         INTEGER NOT NULL DEFAULT 0,
    replied_via     TEXT,
    created_at      TEXT    NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_recruiter_job     ON recruiters (job_id);
CREATE INDEX IF NOT EXISTS idx_recruiter_company ON recruiters (company);
"""

# Each entry is run once; errors (column already exists) are silently ignored.
# Indexes that depend on migrated columns must come AFTER their ADD COLUMN.
_MIGRATIONS = [
    "ALTER TABLE jobs ADD COLUMN location TEXT",
    "ALTER TABLE jobs ADD COLUMN cover_letter TEXT",
    "ALTER TABLE jobs ADD COLUMN approval_status TEXT DEFAULT 'pending_review'",
    "ALTER TABLE jobs ADD COLUMN applied_at TEXT",
    "ALTER TABLE jobs ADD COLUMN application_id TEXT",
    "CREATE INDEX IF NOT EXISTS idx_approval_status ON jobs (approval_status)",
    "ALTER TABLE jobs ADD COLUMN fit_reason TEXT",
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
    """Create the jobs and recruiters tables if new, then apply column migrations."""
    with _connect(db_path) as conn:
        conn.executescript(_SCHEMA)
        conn.executescript(_RECRUITER_SCHEMA)
        for migration in _MIGRATIONS:
            try:
                conn.execute(migration)
            except sqlite3.OperationalError:
                pass  # column/index already exists — skip
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


def set_fit_reason(job_id: int, reason: str, db_path: str = DB_PATH) -> None:
    """Store the LLM fit-filter reason for a skipped job."""
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET fit_reason = ? WHERE id = ?",
            (reason, job_id),
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
        total    = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        pending  = conn.execute("SELECT COUNT(*) FROM jobs WHERE approval_status = 'pending_review' AND processed = 1").fetchone()[0]
        applied  = conn.execute("SELECT COUNT(*) FROM jobs WHERE approval_status = 'applied'").fetchone()[0]
        rejected = conn.execute("SELECT COUNT(*) FROM jobs WHERE approval_status = 'rejected'").fetchone()[0]
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


# ── Recruiter functions ────────────────────────────────────────────────────────

def insert_recruiter(
    job_id: int,
    recruiter: dict,
    cold_email: Optional[str],
    db_path: str = DB_PATH,
) -> int:
    """Insert a recruiter row. Returns the new row id."""
    now = datetime.utcnow().isoformat()
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO recruiters
                (job_id, name, title, company, email, linkedin_url, cold_email_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                recruiter.get("name"),
                recruiter.get("title"),
                recruiter.get("company", ""),
                recruiter.get("email"),
                recruiter.get("linkedin_url"),
                cold_email,
                now,
            ),
        )
        return cursor.lastrowid


def get_all_recruiters(
    limit: int = 50,
    offset: int = 0,
    company: Optional[str] = None,
    db_path: str = DB_PATH,
) -> list[dict]:
    """Return recruiters ordered by newest first, with optional company filter."""
    with _connect(db_path) as conn:
        if company:
            rows = conn.execute(
                "SELECT * FROM recruiters WHERE company = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (company, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM recruiters ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
    return [dict(row) for row in rows]


def update_recruiter(
    recruiter_id: int,
    field: str,
    value,
    db_path: str = DB_PATH,
) -> None:
    """Update a single field on a recruiter row. Only whitelisted fields accepted."""
    allowed = {"email_sent", "linkedin_sent", "replied", "replied_via"}
    if field not in allowed:
        raise ValueError(f"Field '{field}' is not updatable")
    with _connect(db_path) as conn:
        conn.execute(
            f"UPDATE recruiters SET {field} = ? WHERE id = ?",
            (value, recruiter_id),
        )


def get_recruiter_stats(db_path: str = DB_PATH) -> dict:
    """Return summary counts for the recruiters dashboard."""
    with _connect(db_path) as conn:
        tracked       = conn.execute("SELECT COUNT(*) FROM recruiters").fetchone()[0]
        emails_sent   = conn.execute("SELECT COUNT(*) FROM recruiters WHERE email_sent = 1").fetchone()[0]
        linkedin_sent = conn.execute("SELECT COUNT(*) FROM recruiters WHERE linkedin_sent = 1").fetchone()[0]
        replied       = conn.execute("SELECT COUNT(*) FROM recruiters WHERE replied = 1").fetchone()[0]
        companies     = conn.execute("SELECT COUNT(DISTINCT company) FROM recruiters").fetchone()[0]
    return {
        "tracked": tracked,
        "companies": companies,
        "emails_sent": emails_sent,
        "linkedin_sent": linkedin_sent,
        "replied": replied,
    }


# ── Analytics query functions ──────────────────────────────────────────────────

def get_weekly_submissions(weeks: int = 8, db_path: str = DB_PATH) -> list[dict]:
    """
    Return per-week counts of resumes prepared and applications submitted
    for the last `weeks` calendar weeks (most recent last).
    """
    results = []
    now = datetime.utcnow()
    with _connect(db_path) as conn:
        for i in range(weeks - 1, -1, -1):
            week_start = (now - timedelta(weeks=i)).date()
            # Align to Monday
            week_start = week_start - timedelta(days=week_start.weekday())
            week_end   = week_start + timedelta(days=7)
            ws, we = week_start.isoformat(), week_end.isoformat()

            prepared = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE processed = 1 AND created_at >= ? AND created_at < ?",
                (ws, we),
            ).fetchone()[0]

            applied = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE approval_status = 'applied' AND applied_at >= ? AND applied_at < ?",
                (ws, we),
            ).fetchone()[0]

            results.append({
                "week":  f"Wk {week_start.strftime('%d %b')}",
                "start": ws,
                "prepared": prepared,
                "applied":  applied,
            })
    return results


def get_ats_distribution(db_path: str = DB_PATH) -> list[dict]:
    """Return ATS score counts in 5 buckets: <60, 60-69, 70-79, 80-89, 90+."""
    buckets = [
        ("<60",   "SELECT COUNT(*) FROM jobs WHERE ats_score IS NOT NULL AND ats_score < 60"),
        ("60-69", "SELECT COUNT(*) FROM jobs WHERE ats_score >= 60 AND ats_score < 70"),
        ("70-79", "SELECT COUNT(*) FROM jobs WHERE ats_score >= 70 AND ats_score < 80"),
        ("80-89", "SELECT COUNT(*) FROM jobs WHERE ats_score >= 80 AND ats_score < 90"),
        ("90+",   "SELECT COUNT(*) FROM jobs WHERE ats_score >= 90"),
    ]
    with _connect(db_path) as conn:
        return [{"bucket": label, "count": conn.execute(q).fetchone()[0]} for label, q in buckets]


def get_funnel_data(db_path: str = DB_PATH) -> dict:
    """Return application funnel counts: discovered → prepared → applied."""
    with _connect(db_path) as conn:
        discovered = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        prepared   = conn.execute("SELECT COUNT(*) FROM jobs WHERE processed = 1 AND pdf_path IS NOT NULL").fetchone()[0]
        applied    = conn.execute("SELECT COUNT(*) FROM jobs WHERE approval_status = 'applied'").fetchone()[0]
    return {"discovered": discovered, "prepared": prepared, "applied": applied}


def get_portal_mix(db_path: str = DB_PATH) -> list[dict]:
    """Return application counts grouped by source, sorted by count descending."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT source, COUNT(*) as count
              FROM jobs
             WHERE source IS NOT NULL
             GROUP BY source
             ORDER BY count DESC
            """
        ).fetchall()
    total = sum(r["count"] for r in rows) or 1
    return [
        {"source": r["source"], "count": r["count"], "pct": round(r["count"] / total * 100)}
        for r in rows
    ]
