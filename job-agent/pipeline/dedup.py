"""
Database layer — supports SQLite (local dev) and PostgreSQL (production/cloud).

Set DATABASE_URL for PostgreSQL (Neon, Railway, etc.).
Falls back to DB_PATH / SQLite when DATABASE_URL is not set.
"""

import os
import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_PATH      = os.getenv("DB_PATH", "db/jobs.db")
_USE_PG      = bool(DATABASE_URL)

# ── Schemas ───────────────────────────────────────────────────────────────────

_SCHEMA_SQLITE = """
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
CREATE INDEX IF NOT EXISTS idx_processed     ON jobs (processed)
"""

_SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS jobs (
    id          SERIAL  PRIMARY KEY,
    title       TEXT    NOT NULL,
    company     TEXT    NOT NULL,
    url         TEXT    NOT NULL,
    jd_text     TEXT,
    source      TEXT,
    posted_date TEXT,
    processed   INTEGER NOT NULL DEFAULT 0,
    ats_score   REAL,
    pdf_path    TEXT,
    pdf_bytes   BYTEA,
    status      TEXT    DEFAULT 'pending',
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_company_title ON jobs (company, title);
CREATE INDEX IF NOT EXISTS idx_processed     ON jobs (processed)
"""

_RECRUITER_SCHEMA_SQLITE = """
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
CREATE INDEX IF NOT EXISTS idx_recruiter_company ON recruiters (company)
"""

_RECRUITER_SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS recruiters (
    id              SERIAL  PRIMARY KEY,
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
CREATE INDEX IF NOT EXISTS idx_recruiter_company ON recruiters (company)
"""

_PENDING_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS pending_answers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER NOT NULL,
    field_name  TEXT    NOT NULL,
    label       TEXT    NOT NULL,
    field_type  TEXT    NOT NULL,
    options     TEXT,
    required    INTEGER NOT NULL DEFAULT 0,
    answer      TEXT,
    answered_by TEXT,
    created_at  TEXT    NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);
CREATE INDEX IF NOT EXISTS idx_pending_job ON pending_answers (job_id)
"""

_PENDING_SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS pending_answers (
    id          SERIAL  PRIMARY KEY,
    job_id      INTEGER NOT NULL,
    field_name  TEXT    NOT NULL,
    label       TEXT    NOT NULL,
    field_type  TEXT    NOT NULL,
    options     TEXT,
    required    INTEGER NOT NULL DEFAULT 0,
    answer      TEXT,
    answered_by TEXT,
    created_at  TEXT    NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);
CREATE INDEX IF NOT EXISTS idx_pending_job ON pending_answers (job_id)
"""

# Explicit column list for jobs — excludes pdf_bytes so PDFs are never
# pulled over the network except when explicitly requested via get_job_pdf_bytes().
_JOB_COLS = (
    "id, title, company, url, jd_text, source, posted_date, processed, ats_score, "
    "pdf_path, status, created_at, location, cover_letter, approval_status, applied_at, "
    "application_id, fit_reason, manual_review, application_status"
)

# SQLite migrations: OperationalError on duplicate column is silently ignored
_MIGRATIONS_SQLITE = [
    "ALTER TABLE jobs ADD COLUMN location TEXT",
    "ALTER TABLE jobs ADD COLUMN cover_letter TEXT",
    "ALTER TABLE jobs ADD COLUMN approval_status TEXT DEFAULT 'pending_review'",
    "ALTER TABLE jobs ADD COLUMN applied_at TEXT",
    "ALTER TABLE jobs ADD COLUMN application_id TEXT",
    "CREATE INDEX IF NOT EXISTS idx_approval_status ON jobs (approval_status)",
    "ALTER TABLE jobs ADD COLUMN fit_reason TEXT",
    "ALTER TABLE jobs ADD COLUMN manual_review INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE jobs ADD COLUMN application_status TEXT",
    """CREATE TABLE IF NOT EXISTS location_cache (
        location    TEXT PRIMARY KEY,
        is_us       INTEGER NOT NULL,
        cached_at   TEXT NOT NULL
    )""",
]

# PostgreSQL: ADD COLUMN IF NOT EXISTS is idempotent (PG 9.6+)
_MIGRATIONS_PG = [
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS location TEXT",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS cover_letter TEXT",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS approval_status TEXT DEFAULT 'pending_review'",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS applied_at TEXT",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS application_id TEXT",
    "CREATE INDEX IF NOT EXISTS idx_approval_status ON jobs (approval_status)",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS fit_reason TEXT",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS pdf_bytes BYTEA",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS manual_review INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS application_status TEXT",
    """CREATE TABLE IF NOT EXISTS location_cache (
        location    TEXT PRIMARY KEY,
        is_us       BOOLEAN NOT NULL,
        cached_at   TEXT NOT NULL
    )""",
]


# ── Connection + low-level helpers ────────────────────────────────────────────

@contextmanager
def _conn():
    """Yield an open DB connection; commit on success, rollback + close on error."""
    if _USE_PG:
        from urllib.parse import urlparse
        import ssl
        import pg8000.dbapi
        p = urlparse(DATABASE_URL)
        kwargs = {
            "host":     p.hostname,
            "port":     p.port or 5432,
            "database": p.path.lstrip("/"),
            "user":     p.username,
            "password": p.password,
        }
        # Neon and most cloud PG require SSL
        if "sslmode=require" in DATABASE_URL or (p.hostname and "neon" in p.hostname):
            kwargs["ssl_context"] = ssl.create_default_context()
        c = pg8000.dbapi.connect(**kwargs)
    else:
        if DB_PATH != ":memory:":
            parent = os.path.dirname(DB_PATH)
            if parent:
                os.makedirs(parent, exist_ok=True)
        c = sqlite3.connect(DB_PATH)
        c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def _x(c, sql: str, params=()):
    """Execute SQL, normalising ? → %s for pg8000. Returns the cursor."""
    if _USE_PG:
        sql = sql.replace("?", "%s")
        cur = c.cursor()
        cur.execute(sql, list(params))   # pg8000 requires a list, never None
        return cur
    return c.execute(sql, params)


def _insert(c, sql: str, params) -> int:
    """Execute INSERT and return the new row id."""
    if _USE_PG:
        sql = sql.replace("?", "%s") + " RETURNING id"
        cur = c.cursor()
        cur.execute(sql, list(params))   # pg8000 requires a list
        return cur.fetchone()[0]
    return c.execute(sql, params).lastrowid


def _all(cur) -> list[dict]:
    """Fetch all rows as plain dicts, stripping binary columns."""
    rows = cur.fetchall()
    if not rows:
        return []
    if _USE_PG:
        cols = [d[0] for d in cur.description]
        return [
            {cols[i]: row[i] for i in range(len(cols)) if cols[i] != "pdf_bytes"}
            for row in rows
        ]
    return [{k: v for k, v in dict(r).items() if k != "pdf_bytes"} for r in rows]


def _one(cur) -> Optional[dict]:
    """Fetch one row as a plain dict, stripping binary columns."""
    row = cur.fetchone()
    if row is None:
        return None
    if _USE_PG:
        cols = [d[0] for d in cur.description]
        return {cols[i]: row[i] for i in range(len(cols)) if cols[i] != "pdf_bytes"}
    return {k: v for k, v in dict(row).items() if k != "pdf_bytes"}


def _run_script(c, script: str):
    """Execute a semicolon-delimited SQL script (pg8000 has no executescript)."""
    if _USE_PG:
        cur = c.cursor()
        for stmt in [s.strip() for s in script.split(";") if s.strip()]:
            cur.execute(stmt, [])    # pg8000 requires a list, never bare None
    else:
        c.executescript(script)


# ── Schema init ───────────────────────────────────────────────────────────────

def init_db(db_path: str = DB_PATH) -> None:
    """Create tables if new, then apply column migrations."""
    if _USE_PG:
        _init_pg()
    else:
        _init_sqlite()
    logger.info("Database initialised (%s)", "PostgreSQL" if _USE_PG else db_path)


def _init_sqlite():
    with _conn() as c:
        _run_script(c, _SCHEMA_SQLITE)
        _run_script(c, _RECRUITER_SCHEMA_SQLITE)
        _run_script(c, _PENDING_SCHEMA_SQLITE)
        for migration in _MIGRATIONS_SQLITE:
            try:
                c.execute(migration)
            except sqlite3.OperationalError:
                pass


def _init_pg():
    with _conn() as c:
        _run_script(c, _SCHEMA_PG)
        _run_script(c, _RECRUITER_SCHEMA_PG)
        _run_script(c, _PENDING_SCHEMA_PG)
    # Each migration in its own transaction — PG aborts on any error
    for migration in _MIGRATIONS_PG:
        try:
            with _conn() as c:
                _x(c, migration)
        except Exception:
            pass  # column/index already exists


# ── Location cache functions ──────────────────────────────────────────────────

def get_cached_location(location: str) -> bool | None:
    """Return cached is_us value, or None if not cached."""
    try:
        with _conn() as c:
            row = _x(c, "SELECT is_us FROM location_cache WHERE location = ?",
                     (location,)).fetchone()
            if row is not None:
                return bool(row[0])
    except Exception:
        pass
    return None


def cache_location(location: str, is_us: bool) -> None:
    """Persist a geocoded location result to the cache."""
    now = datetime.utcnow().isoformat()
    try:
        with _conn() as c:
            _x(c,
               "INSERT INTO location_cache (location, is_us, cached_at) VALUES (?, ?, ?)"
               " ON CONFLICT (location) DO UPDATE SET is_us = excluded.is_us, cached_at = excluded.cached_at",
               (location, 1 if is_us else 0, now))
    except Exception as e:
        logger.debug("location_cache write failed (non-fatal): %s", e)


# ── Job functions ─────────────────────────────────────────────────────────────

def is_duplicate(company: str, title: str, db_path: str = DB_PATH) -> bool:
    """Return True if (company, title) already exists."""
    with _conn() as c:
        cur = _x(c, "SELECT id FROM jobs WHERE company = ? AND title = ?",
                 (company.strip(), title.strip()))
        return cur.fetchone() is not None


def insert_job(job: dict, db_path: str = DB_PATH) -> int:
    """Insert a new job row. Returns the new row id."""
    now = datetime.utcnow().isoformat()
    with _conn() as c:
        return _insert(c,
            "INSERT INTO jobs (title, company, url, jd_text, source, posted_date, location, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
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


def get_unprocessed_jobs(db_path: str = DB_PATH) -> list[dict]:
    """Return all jobs where processed = 0."""
    with _conn() as c:
        return _all(_x(c, f"SELECT {_JOB_COLS} FROM jobs WHERE processed = 0 ORDER BY created_at ASC"))


def mark_processed(
    job_id: int,
    pdf_path: Optional[str],
    ats_score: Optional[float],
    status: str,
    db_path: str = DB_PATH,
    pdf_bytes: Optional[bytes] = None,
) -> None:
    """Update a job row as processed with outcome data."""
    with _conn() as c:
        if _USE_PG and pdf_bytes is not None:
            _x(c,
               "UPDATE jobs SET processed=1, pdf_path=?, pdf_bytes=?, ats_score=?, status=? WHERE id=?",
               (pdf_path, pdf_bytes, ats_score, status, job_id))
        else:
            _x(c,
               "UPDATE jobs SET processed=1, pdf_path=?, ats_score=?, status=? WHERE id=?",
               (pdf_path, ats_score, status, job_id))


def set_cover_letter(job_id: int, cover_letter: str, db_path: str = DB_PATH) -> None:
    with _conn() as c:
        _x(c, "UPDATE jobs SET cover_letter = ? WHERE id = ?", (cover_letter, job_id))


def set_fit_reason(job_id: int, reason: str, db_path: str = DB_PATH) -> None:
    with _conn() as c:
        _x(c, "UPDATE jobs SET fit_reason = ? WHERE id = ?", (reason, job_id))


def set_approval(job_id: int, approval_status: str, db_path: str = DB_PATH) -> None:
    with _conn() as c:
        _x(c, "UPDATE jobs SET approval_status = ? WHERE id = ?", (approval_status, job_id))


def mark_applied(job_id: int, application_id: str, db_path: str = DB_PATH) -> None:
    now = datetime.utcnow().isoformat()
    with _conn() as c:
        _x(c,
           "UPDATE jobs SET approval_status='applied', applied_at=?, application_id=? WHERE id=?",
           (now, application_id, job_id))


def get_job(job_id: int, db_path: str = DB_PATH) -> Optional[dict]:
    """Fetch a single job by id (without pdf_bytes)."""
    with _conn() as c:
        return _one(_x(c, f"SELECT {_JOB_COLS} FROM jobs WHERE id = ?", (job_id,)))


def set_manual_review(job_id: int, value: bool, db_path: str = DB_PATH) -> None:
    with _conn() as c:
        _x(c, "UPDATE jobs SET manual_review = ? WHERE id = ?", (1 if value else 0, job_id))


def set_application_status(job_id: int, status: str, db_path: str = DB_PATH) -> None:
    with _conn() as c:
        _x(c, "UPDATE jobs SET application_status = ? WHERE id = ?", (status or None, job_id))


def get_job_pdf_bytes(job_id: int) -> Optional[bytes]:
    """Fetch the raw PDF bytes for a job (PostgreSQL only; returns None for SQLite)."""
    if not _USE_PG:
        return None
    with _conn() as c:
        cur = _x(c, "SELECT pdf_bytes FROM jobs WHERE id = ?", (job_id,))
        row = cur.fetchone()
        return row[0] if row else None


def get_pending_review_jobs(db_path: str = DB_PATH) -> list[dict]:
    with _conn() as c:
        return _all(_x(c,
            f"SELECT {_JOB_COLS} FROM jobs WHERE processed=1 AND pdf_path IS NOT NULL"
            " AND approval_status='pending_review' ORDER BY created_at DESC"))


def get_all_jobs(
    limit: int = 50,
    offset: int = 0,
    approval_status: Optional[str] = None,
    db_path: str = DB_PATH,
) -> list[dict]:
    with _conn() as c:
        if approval_status:
            return _all(_x(c,
                f"SELECT {_JOB_COLS} FROM jobs WHERE approval_status=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (approval_status, limit, offset)))
        return _all(_x(c,
            f"SELECT {_JOB_COLS} FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)))


def get_stats(db_path: str = DB_PATH) -> dict:
    with _conn() as c:
        total    = _x(c, "SELECT COUNT(*) FROM jobs").fetchone()[0]
        pending  = _x(c, "SELECT COUNT(*) FROM jobs WHERE approval_status='pending_review' AND processed=1").fetchone()[0]
        applied  = _x(c, "SELECT COUNT(*) FROM jobs WHERE approval_status IN ('applied', 'approved')").fetchone()[0]
        rejected = _x(c, "SELECT COUNT(*) FROM jobs WHERE approval_status='rejected'").fetchone()[0]
    return {"total": total, "pending": pending, "applied": applied, "rejected": rejected}


def get_todays_processed_jobs(db_path: str = DB_PATH) -> list[dict]:
    today = datetime.utcnow().date().isoformat()
    with _conn() as c:
        return _all(_x(c,
            f"SELECT {_JOB_COLS} FROM jobs WHERE processed=1 AND created_at LIKE ?",
            (f"{today}%",)))


# ── Recruiter functions ───────────────────────────────────────────────────────

def insert_recruiter(
    job_id: int,
    recruiter: dict,
    cold_email: Optional[str],
    db_path: str = DB_PATH,
) -> int:
    now = datetime.utcnow().isoformat()
    with _conn() as c:
        return _insert(c,
            "INSERT INTO recruiters (job_id, name, title, company, email, linkedin_url, cold_email_text, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
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


def get_recruiter(recruiter_id: int, db_path: str = DB_PATH) -> Optional[dict]:
    """Fetch a single recruiter by id."""
    with _conn() as c:
        return _one(_x(c, "SELECT * FROM recruiters WHERE id = ?", (recruiter_id,)))


def get_all_recruiters(
    limit: int = 50,
    offset: int = 0,
    company: Optional[str] = None,
    db_path: str = DB_PATH,
) -> list[dict]:
    _join = (
        "SELECT r.*, j.company AS job_company, j.title AS job_title, j.url AS job_url "
        "FROM recruiters r LEFT JOIN jobs j ON r.job_id = j.id"
    )
    with _conn() as c:
        if company:
            return _all(_x(c,
                f"{_join} WHERE r.company=? ORDER BY r.created_at DESC LIMIT ? OFFSET ?",
                (company, limit, offset)))
        return _all(_x(c,
            f"{_join} ORDER BY r.created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)))


def cleanup_bad_recruiters(db_path: str = DB_PATH) -> int:
    """
    Delete recruiter rows that contain Hunter.io placeholder data.

    The jobs.com domain was being extracted from LinkedIn URLs
    (/jobs/view/...) causing Hunter.io to return a generic demo contact
    ('Andres Creada' / andres@jobs.com) for every LinkedIn job.
    This is a one-time cleanup; the underlying bug is now fixed.
    """
    with _conn() as c:
        cur = _x(c,
            "DELETE FROM recruiters WHERE email LIKE '%@jobs.com' OR name = 'Andres Creada'")
        deleted = cur.rowcount if hasattr(cur, "rowcount") else 0
    if deleted:
        logger.info("Cleaned up %d bad recruiter rows (jobs.com placeholder data)", deleted)
    return deleted or 0


def update_recruiter(
    recruiter_id: int,
    field: str,
    value,
    db_path: str = DB_PATH,
) -> None:
    allowed = {"email_sent", "linkedin_sent", "replied", "replied_via"}
    if field not in allowed:
        raise ValueError(f"Field '{field}' is not updatable")
    with _conn() as c:
        _x(c, f"UPDATE recruiters SET {field} = ? WHERE id = ?", (value, recruiter_id))


def get_recruiter_stats(db_path: str = DB_PATH) -> dict:
    with _conn() as c:
        tracked       = _x(c, "SELECT COUNT(*) FROM recruiters").fetchone()[0]
        emails_sent   = _x(c, "SELECT COUNT(*) FROM recruiters WHERE email_sent=1").fetchone()[0]
        linkedin_sent = _x(c, "SELECT COUNT(*) FROM recruiters WHERE linkedin_sent=1").fetchone()[0]
        replied       = _x(c, "SELECT COUNT(*) FROM recruiters WHERE replied=1").fetchone()[0]
        companies     = _x(c, "SELECT COUNT(DISTINCT company) FROM recruiters").fetchone()[0]
    return {
        "tracked": tracked,
        "companies": companies,
        "emails_sent": emails_sent,
        "linkedin_sent": linkedin_sent,
        "replied": replied,
    }


# ── Analytics ─────────────────────────────────────────────────────────────────

def get_weekly_submissions(weeks: int = 8, db_path: str = DB_PATH) -> list[dict]:
    results = []
    now = datetime.utcnow()
    with _conn() as c:
        for i in range(weeks - 1, -1, -1):
            week_start = (now - timedelta(weeks=i)).date()
            week_start = week_start - timedelta(days=week_start.weekday())
            week_end   = week_start + timedelta(days=7)
            ws, we = week_start.isoformat(), week_end.isoformat()

            prepared = _x(c,
                "SELECT COUNT(*) FROM jobs WHERE processed=1 AND created_at >= ? AND created_at < ?",
                (ws, we)).fetchone()[0]

            applied = _x(c,
                "SELECT COUNT(*) FROM jobs WHERE approval_status IN ('applied', 'approved') AND applied_at >= ? AND applied_at < ?",
                (ws, we)).fetchone()[0]

            results.append({
                "week":     f"Wk {week_start.strftime('%d %b')}",
                "start":    ws,
                "prepared": prepared,
                "applied":  applied,
            })
    return results


def get_ats_distribution(db_path: str = DB_PATH) -> list[dict]:
    buckets = [
        ("<60",   "SELECT COUNT(*) FROM jobs WHERE ats_score IS NOT NULL AND ats_score < 60"),
        ("60-69", "SELECT COUNT(*) FROM jobs WHERE ats_score >= 60 AND ats_score < 70"),
        ("70-79", "SELECT COUNT(*) FROM jobs WHERE ats_score >= 70 AND ats_score < 80"),
        ("80-89", "SELECT COUNT(*) FROM jobs WHERE ats_score >= 80 AND ats_score < 90"),
        ("90+",   "SELECT COUNT(*) FROM jobs WHERE ats_score >= 90"),
    ]
    with _conn() as c:
        return [{"bucket": label, "count": _x(c, q).fetchone()[0]} for label, q in buckets]


def get_funnel_data(db_path: str = DB_PATH) -> dict:
    with _conn() as c:
        discovered = _x(c, "SELECT COUNT(*) FROM jobs").fetchone()[0]
        prepared   = _x(c, "SELECT COUNT(*) FROM jobs WHERE processed=1 AND pdf_path IS NOT NULL").fetchone()[0]
        applied    = _x(c, "SELECT COUNT(*) FROM jobs WHERE approval_status IN ('applied', 'approved')").fetchone()[0]
    return {"discovered": discovered, "prepared": prepared, "applied": applied}


# ── Pending answers functions ─────────────────────────────────────────────────

def save_pending_questions(job_id: int, questions: list[dict], db_path: str = DB_PATH) -> None:
    """
    Persist all classified questions for a job (answered + unanswered).
    Replaces any existing rows for this job so re-approving is idempotent.
    """
    import json as _json
    now = datetime.utcnow().isoformat()
    with _conn() as c:
        _x(c, "DELETE FROM pending_answers WHERE job_id = ?", (job_id,))
        for q in questions:
            options_json = _json.dumps(q["options"]) if q.get("options") else None
            _insert(c,
                "INSERT INTO pending_answers "
                "(job_id, field_name, label, field_type, options, required, answer, answered_by, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    q["field_name"],
                    q["label"],
                    q["field_type"],
                    options_json,
                    1 if q.get("required") else 0,
                    q.get("answer"),
                    q.get("answered_by"),
                    now,
                ),
            )


def get_pending_questions(job_id: int, db_path: str = DB_PATH) -> list[dict]:
    """Return all questions for a job (both answered and unanswered)."""
    import json as _json
    with _conn() as c:
        rows = _all(_x(c,
            "SELECT * FROM pending_answers WHERE job_id = ? ORDER BY id ASC", (job_id,)))
    for r in rows:
        if r.get("options"):
            try:
                r["options"] = _json.loads(r["options"])
            except Exception:
                r["options"] = []
    return rows


def get_unanswered_questions(job_id: int, db_path: str = DB_PATH) -> list[dict]:
    """Return questions that still need a user answer (answer IS NULL)."""
    import json as _json
    with _conn() as c:
        rows = _all(_x(c,
            "SELECT * FROM pending_answers WHERE job_id = ? AND answer IS NULL ORDER BY id ASC",
            (job_id,)))
    for r in rows:
        if r.get("options"):
            try:
                r["options"] = _json.loads(r["options"])
            except Exception:
                r["options"] = []
    return rows


def get_jobs_with_pending_questions(db_path: str = DB_PATH) -> list[dict]:
    """Return jobs that have at least one unanswered question, with question list."""
    import json as _json
    with _conn() as c:
        job_ids = _all(_x(c,
            "SELECT DISTINCT job_id FROM pending_answers WHERE answer IS NULL"))
        if not job_ids:
            return []
        ids = [r["job_id"] for r in job_ids]
        placeholders = ",".join("?" * len(ids))
        jobs = _all(_x(c,
            f"SELECT id, title, company, url, source FROM jobs WHERE id IN ({placeholders})",
            tuple(ids)))
        q_rows = _all(_x(c,
            f"SELECT * FROM pending_answers WHERE job_id IN ({placeholders}) AND answer IS NULL ORDER BY id ASC",
            tuple(ids)))

    q_map: dict[int, list] = {}
    for q in q_rows:
        if q.get("options"):
            try:
                q["options"] = _json.loads(q["options"])
            except Exception:
                q["options"] = []
        q_map.setdefault(q["job_id"], []).append(q)

    result = []
    for job in jobs:
        result.append({**job, "questions": q_map.get(job["id"], [])})
    return result


def answer_question(answer_id: int, answer: str, db_path: str = DB_PATH) -> None:
    """Save a user-provided answer for a pending question."""
    with _conn() as c:
        _x(c,
           "UPDATE pending_answers SET answer = ?, answered_by = 'user' WHERE id = ?",
           (answer, answer_id))


def delete_pending_questions(job_id: int, db_path: str = DB_PATH) -> None:
    """Remove all pending questions for a job after successful submission."""
    with _conn() as c:
        _x(c, "DELETE FROM pending_answers WHERE job_id = ?", (job_id,))


def count_unanswered(job_id: int, db_path: str = DB_PATH) -> int:
    """Return the number of unanswered questions for a job."""
    with _conn() as c:
        return _x(c,
            "SELECT COUNT(*) FROM pending_answers WHERE job_id = ? AND answer IS NULL",
            (job_id,)).fetchone()[0]


def get_portal_mix(db_path: str = DB_PATH) -> list[dict]:
    with _conn() as c:
        rows = _all(_x(c,
            "SELECT source, COUNT(*) as count FROM jobs"
            " WHERE source IS NOT NULL GROUP BY source ORDER BY count DESC"))
    total = sum(r["count"] for r in rows) or 1
    return [
        {"source": r["source"], "count": r["count"], "pct": round(r["count"] / total * 100)}
        for r in rows
    ]
