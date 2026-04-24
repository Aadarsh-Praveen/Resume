"""
Job Application Agent — Main Entry Point

Runs the complete automated pipeline:
    1. Collect jobs from all configured sources
    2. Deduplicate against the SQLite database
    3. Extract full JD text for each new job
    4. Tailor resume via Claude API
    5. Run quality gates (compile, page count, ATS score)
    6. Log to Google Sheets
    7. Find recruiter via Apollo.io
    8. Draft cold email via Claude
    9. Send Telegram alert with PDF preview

Usage:
    python agent.py              # run one full cycle
    python agent.py --daemon     # run on schedule (every 4h + Gmail every 15min)
    python agent.py --collect    # collect jobs only (no tailoring)
    python agent.py --process    # process existing unprocessed jobs only
    python agent.py --digest     # send daily Telegram digest now
    python agent.py --test-job   # tailor a single test job (uses test JD)
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Logging setup ─────────────────────────────────────────────────────────────
LOG_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("agent.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("agent")

# ── Imports after dotenv loaded ───────────────────────────────────────────────
from pipeline.dedup import (
    init_db, is_duplicate, insert_job,
    get_unprocessed_jobs, mark_processed, get_todays_processed_jobs,
    set_cover_letter, set_fit_reason, insert_recruiter,
)
from pipeline.fit_filter import assess_fit
from pipeline.jd_extractor import extract_jd_text, extract_min_years
from pipeline.tailor_resume import tailor_resume
from pipeline.ats_scorer import score_resume
from sources.indeed_rss import fetch_indeed_jobs
from sources.greenhouse_api import fetch_greenhouse_jobs
from sources.lever_api import fetch_lever_jobs
from sources.ashby_api import fetch_ashby_jobs
from sources.email_parser import watch_linkedin_alerts
from sources.linkedin_jobs import fetch_linkedin_jobs
from sources.workday_api import fetch_workday_jobs
from sources.custom_careers import fetch_custom_career_jobs
from sources.yc_jobs import fetch_yc_jobs
from sources.wellfound import fetch_wellfound_jobs
from sources.mass_general import fetch_mass_general_jobs
from sources.mayo_clinic import fetch_mayo_clinic_jobs
from outputs.tracker import log_application
from outputs.telegram_alert import send_alert, send_error_alert, send_daily_digest
from outputs.recruiter_finder import find_recruiter, draft_cold_email
from pipeline.location_filter import is_us_or_remote
from config import POLL_INTERVAL_HOURS, GMAIL_POLL_MINUTES, DAILY_DIGEST_HOUR, YOE_MAX_FILTER, LOCATION_FILTER, ROLE_KEYWORDS, EXCLUDE_KEYWORDS

DB_PATH = os.getenv("DB_PATH", "db/jobs.db")
RESUMES_DIR = os.getenv("RESUMES_DIR", "resumes")
FAILED_LOG = "failed_jobs.log"



# ── Job collection ─────────────────────────────────────────────────────────────

def run_collection_cycle() -> int:
    """
    Poll all job sources, deduplicate, and insert new jobs into the DB.

    Returns:
        Number of new jobs inserted.
    """
    logger.info("=" * 60)
    logger.info("COLLECTION CYCLE — %s", datetime.utcnow().isoformat())
    logger.info("=" * 60)

    all_new_jobs: list[dict] = []

    # Source 1: LinkedIn direct search (guest API — no login required)
    try:
        jobs = fetch_linkedin_jobs()
        all_new_jobs.extend(jobs)
    except Exception as e:
        logger.error("LinkedIn direct search failed: %s", e)

    # Source 2: LinkedIn email alerts (Gmail)
    try:
        jobs = watch_linkedin_alerts()
        all_new_jobs.extend(jobs)
    except Exception as e:
        logger.warning("Gmail/LinkedIn alerts failed (check credentials): %s", e)

    # Source 3: Indeed RSS
    try:
        jobs = fetch_indeed_jobs()
        all_new_jobs.extend(jobs)
    except Exception as e:
        logger.error("Indeed RSS failed: %s", e)

    # Source 4: Greenhouse
    try:
        jobs = fetch_greenhouse_jobs()
        all_new_jobs.extend(jobs)
    except Exception as e:
        logger.error("Greenhouse API failed: %s", e)

    # Source 5: Lever
    try:
        jobs = fetch_lever_jobs()
        all_new_jobs.extend(jobs)
    except Exception as e:
        logger.error("Lever API failed: %s", e)

    # Source 6: Ashby
    try:
        jobs = fetch_ashby_jobs()
        all_new_jobs.extend(jobs)
    except Exception as e:
        logger.error("Ashby API failed: %s", e)

    # Source 7: Workday JSON API (NVIDIA, Tesla, Apple, Salesforce, AMD)
    try:
        jobs = fetch_workday_jobs()
        all_new_jobs.extend(jobs)
    except Exception as e:
        logger.error("Workday API failed: %s", e)

    # Source 8: Custom career pages (Google, Meta, Microsoft, Amazon)
    try:
        jobs = fetch_custom_career_jobs()
        all_new_jobs.extend(jobs)
    except Exception as e:
        logger.error("Custom career pages failed: %s", e)

    # Source 9: YC Work at a Startup
    try:
        jobs = fetch_yc_jobs()
        all_new_jobs.extend(jobs)
        logger.info("YC: %d jobs collected", len(jobs))
    except Exception as e:
        logger.error("YC jobs failed: %s", e)

    # Source 10: Wellfound
    try:
        jobs = fetch_wellfound_jobs()
        all_new_jobs.extend(jobs)
        logger.info("Wellfound: %d jobs collected", len(jobs))
    except Exception as e:
        logger.error("Wellfound jobs failed: %s", e)

    # Source 11: Mass General Brigham
    try:
        jobs = fetch_mass_general_jobs()
        all_new_jobs.extend(jobs)
        logger.info("Mass General Brigham: %d jobs collected", len(jobs))
    except Exception as e:
        logger.error("Mass General Brigham failed: %s", e)

    # Source 12: Mayo Clinic
    try:
        jobs = fetch_mayo_clinic_jobs()
        all_new_jobs.extend(jobs)
        logger.info("Mayo Clinic: %d jobs collected", len(jobs))
    except Exception as e:
        logger.error("Mayo Clinic failed: %s", e)

    # Deduplicate and insert
    inserted = 0
    for job in all_new_jobs:
        company = job.get("company", "")
        title = job.get("title", "")

        if not company or not title or not job.get("url"):
            continue

        if is_duplicate(company, title, DB_PATH):
            logger.debug("Duplicate: %s at %s — skipping", title, company)
            continue

        # ── Location filter ───────────────────────────────────────────────
        if LOCATION_FILTER:
            if not is_us_or_remote(job.get("location", "")):
                logger.info(
                    "Skipping %s at %s — location '%s' outside filter",
                    title, company, job.get("location"),
                )
                continue

        # Extract full JD text if not already present
        if not job.get("jd_text"):
            try:
                job["jd_text"] = extract_jd_text(job["url"])
            except Exception as e:
                logger.warning("JD extraction failed for %s: %s", job["url"], e)
                job["jd_text"] = ""

        # ── Years-of-experience filter ────────────────────────────────────
        if YOE_MAX_FILTER > 0 and job.get("jd_text"):
            min_yoe = extract_min_years(job["jd_text"])
            if min_yoe is not None and min_yoe > YOE_MAX_FILTER:
                logger.info(
                    "Skipping %s at %s — requires %d+ yrs (limit: %d)",
                    title, company, min_yoe, YOE_MAX_FILTER,
                )
                continue

        job_id = insert_job(job, DB_PATH)
        logger.info("New job #%d: %s at %s (source: %s)", job_id, title, company, job.get("source"))
        inserted += 1

    logger.info("Collection cycle complete — %d new jobs inserted", inserted)
    return inserted


# ── Job processing ────────────────────────────────────────────────────────────

def process_job(job: dict) -> bool:
    """
    Run the full tailoring + alerting pipeline for a single job.

    Returns:
        True if the job was processed successfully (PDF saved and alert sent).
    """
    job_id = job["id"]
    company = job.get("company", "Unknown")
    title = job.get("title", "Unknown")
    jd_text = job.get("jd_text", "")

    # Title-relevance guard — catches legacy DB entries inserted before the
    # title-only filter was enforced. Skips without calling Claude.
    title_lower = title.lower()
    if not any(kw in title_lower for kw in ROLE_KEYWORDS) or any(kw in title_lower for kw in EXCLUDE_KEYWORDS):
        logger.info("Skipping job #%d: '%s' at %s — not a DS/ML role", job_id, title, company)
        mark_processed(job_id, None, None, "skipped_irrelevant", DB_PATH)
        return False

    logger.info("Processing job #%d: %s at %s", job_id, title, company)

    if not jd_text:
        # Try to fetch JD text if it wasn't captured at collection time
        try:
            jd_text = extract_jd_text(job["url"])
        except Exception as e:
            logger.error("Cannot extract JD for job #%d: %s", job_id, e)
            mark_processed(job_id, None, None, "jd_failed", DB_PATH)
            return False

    # ── LLM fit filter (runs before expensive tailoring) ──────────────────────
    try:
        fit = assess_fit(jd_text)
        if fit["skip"]:
            logger.info(
                "Fit filter skipping job #%d (%s @ %s): %s",
                job_id, title, company, fit["reason"],
            )
            set_fit_reason(job_id, fit["reason"], DB_PATH)
            mark_processed(job_id, None, None, "skipped_unqualified", DB_PATH)
            return False
    except Exception as e:
        logger.warning("Fit filter raised unexpectedly for job #%d: %s — continuing", job_id, e)

    # ── Tailor resume ─────────────────────────────────────────────────────────
    try:
        pdf_path, ats_score, cover_letter = tailor_resume(job_id, job, jd_text)
        if cover_letter:
            set_cover_letter(job_id, cover_letter, DB_PATH)
    except RuntimeError as e:
        error_msg = str(e)
        logger.error("Tailoring failed for job #%d: %s", job_id, error_msg)

        # Log failure
        with open(FAILED_LOG, "a") as f:
            f.write(f"{datetime.utcnow().isoformat()} | Job #{job_id} | {company} | {title} | {error_msg}\n")

        mark_processed(job_id, None, None, "failed", DB_PATH)
        send_error_alert(f"Job #{job_id} failed: {company} — {title}\n{error_msg[:500]}")
        return False

    # ── Get final ATS score from the saved PDF ────────────────────────────────
    try:
        ats_score = score_resume(pdf_path, jd_text)
    except Exception as e:
        logger.warning("ATS score check failed: %s", e)
        ats_score = 0.0

    # Determine status
    from config import ATS_SCORE_MIN, ATS_SCORE_MAX
    if ats_score < ATS_SCORE_MIN:
        status = "low_ats"
    elif ats_score > ATS_SCORE_MAX:
        status = "high_ats"
    else:
        status = "ready"

    # Read PDF bytes for cloud storage (stored as BYTEA in PostgreSQL)
    pdf_bytes = None
    if pdf_path:
        try:
            with open(pdf_path, "rb") as _f:
                pdf_bytes = _f.read()
        except OSError as e:
            logger.warning("Could not read PDF bytes: %s", e)

    mark_processed(job_id, pdf_path, ats_score, status, DB_PATH, pdf_bytes=pdf_bytes)

    # ── Find recruiter ────────────────────────────────────────────────────────
    recruiter_info = None
    cold_email = None
    try:
        recruiter_info = find_recruiter(company, title, job.get("url", ""))
        if recruiter_info and recruiter_info.get("name"):
            cold_email = draft_cold_email(recruiter_info, job)
            insert_recruiter(job_id, recruiter_info, cold_email, DB_PATH)
    except Exception as e:
        logger.warning("Recruiter finder failed for job #%d: %s", job_id, e)

    # ── Log to Google Sheets ──────────────────────────────────────────────────
    try:
        log_application(job, pdf_path, ats_score, status)
    except Exception as e:
        logger.warning("Google Sheets logging failed for job #%d: %s", job_id, e)

    # ── Send Telegram alert ───────────────────────────────────────────────────
    try:
        send_alert(job, pdf_path, ats_score, recruiter_info, cold_email)
    except Exception as e:
        logger.warning("Telegram alert failed for job #%d: %s", job_id, e)

    logger.info(
        "Job #%d complete — %s | %s | ATS: %.1f%% | Status: %s",
        job_id, company, title, ats_score, status,
    )
    return True


def run_processing_cycle() -> tuple[int, int]:
    """
    Process all unprocessed jobs in the database.

    Returns:
        (success_count, failure_count)
    """
    logger.info("=" * 60)
    logger.info("PROCESSING CYCLE — %s", datetime.utcnow().isoformat())
    logger.info("=" * 60)

    jobs = get_unprocessed_jobs(DB_PATH)
    logger.info("Found %d unprocessed jobs", len(jobs))

    success = 0
    failure = 0

    for job in jobs:
        try:
            if process_job(job):
                success += 1
            else:
                failure += 1
        except Exception as e:
            logger.error("Unexpected error processing job #%d: %s", job["id"], e)
            failure += 1
        time.sleep(2)  # brief pause between jobs

    logger.info("Processing cycle complete — %d success, %d failure", success, failure)
    return success, failure


# ── Test mode ─────────────────────────────────────────────────────────────────

TEST_JD = """
We are looking for a Senior Data Scientist to join our team.

Required Qualifications:
- 5+ years of experience in data science or machine learning
- Strong proficiency in Python and SQL
- Experience with PyTorch or TensorFlow for deep learning
- Hands-on experience with A/B testing and statistical analysis
- Experience deploying ML models to production (AWS, GCP, or Azure)
- Strong communication skills and ability to present technical results

Preferred Qualifications:
- Experience with LLMs, RAG, or other NLP techniques
- Familiarity with Spark or distributed computing
- PhD in Statistics, Computer Science, or related field
- Experience with MLflow or similar experiment tracking tools

Responsibilities:
- Build and maintain machine learning models for recommendation and personalisation
- Partner with product and engineering teams to define ML problem formulations
- Analyse large datasets using Python and SQL to drive insights
- Develop evaluation frameworks and A/B testing methodology
"""


def run_test_job() -> None:
    """Process a single synthetic test job to verify the pipeline end-to-end."""
    logger.info("Running test job with synthetic JD...")

    test_job = {
        "id": 0,
        "title": "Senior Data Scientist",
        "company": "TestCompany",
        "url": "https://example.com/job/test",
        "jd_text": TEST_JD,
        "source": "test",
        "posted_date": datetime.utcnow().isoformat(),
    }

    try:
        from pipeline.tailor_resume import tailor_resume
        pdf_path, _score, _cover = tailor_resume(0, test_job, TEST_JD)
        logger.info("Test job SUCCESS — PDF: %s", pdf_path)
        print(f"\n✓ Test complete! PDF saved to: {pdf_path}")
    except FileNotFoundError as e:
        logger.error("Test failed — base_resume.tex missing: %s", e)
        print(f"\n✗ Test failed: {e}")
        print("  Place your base_resume.tex in the job-agent/ directory to run tests.")
    except Exception as e:
        logger.error("Test job failed: %s", e)
        print(f"\n✗ Test failed: {e}")


# ── Scheduler ─────────────────────────────────────────────────────────────────

def run_daemon() -> None:
    """Run the agent continuously on a schedule."""
    try:
        import schedule
    except ImportError:
        logger.error("schedule package not installed. Run: pip install schedule")
        sys.exit(1)

    logger.info("Starting daemon mode...")
    logger.info("  Collection cycle: every %d hours", POLL_INTERVAL_HOURS)
    logger.info("  Gmail check:      every %d minutes", GMAIL_POLL_MINUTES)
    logger.info("  Daily digest:     %02d:00 UTC", DAILY_DIGEST_HOUR)

    def collection_and_processing():
        run_collection_cycle()
        run_processing_cycle()

    def gmail_check():
        """Quick Gmail-only check with immediate processing."""
        try:
            from sources.email_parser import watch_linkedin_alerts
            jobs = watch_linkedin_alerts()
            inserted = 0
            for job in jobs:
                if not is_duplicate(job["company"], job["title"], DB_PATH):
                    if not job.get("jd_text"):
                        try:
                            job["jd_text"] = extract_jd_text(job["url"])
                        except Exception:
                            pass
                    insert_job(job, DB_PATH)
                    inserted += 1
            if inserted:
                logger.info("Gmail check: %d new LinkedIn jobs — processing now", inserted)
                run_processing_cycle()
        except Exception as e:
            logger.error("Gmail check failed: %s", e)

    def daily_digest():
        jobs_today = get_todays_processed_jobs(DB_PATH)
        send_daily_digest(jobs_today)

    # Schedule jobs
    schedule.every(POLL_INTERVAL_HOURS).hours.do(collection_and_processing)
    schedule.every(GMAIL_POLL_MINUTES).minutes.do(gmail_check)
    schedule.every().day.at(f"{DAILY_DIGEST_HOUR:02d}:00").do(daily_digest)

    # Run immediately on startup
    collection_and_processing()

    logger.info("Scheduler running — press Ctrl+C to stop")
    while True:
        schedule.run_pending()
        time.sleep(30)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Job Application Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--daemon",    action="store_true", help="Run on schedule")
    parser.add_argument("--collect",   action="store_true", help="Collection cycle only")
    parser.add_argument("--process",   action="store_true", help="Processing cycle only")
    parser.add_argument("--digest",    action="store_true", help="Send daily digest now")
    parser.add_argument("--test-job",  action="store_true", help="Run single test job")
    args = parser.parse_args()

    # Ensure directories exist
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)
    os.makedirs(RESUMES_DIR, exist_ok=True)

    # Log which database is active so it's visible in GitHub Actions logs
    _db_url = os.getenv("DATABASE_URL", "")
    if _db_url:
        _masked = _db_url[:30] + "..." if len(_db_url) > 30 else _db_url
        logger.info("Database: PostgreSQL (%s)", _masked)
    else:
        logger.info("Database: SQLite (%s) — set DATABASE_URL to use PostgreSQL", DB_PATH)

    # Initialise database
    init_db(DB_PATH)

    if args.daemon:
        run_daemon()
    elif args.collect:
        run_collection_cycle()
    elif args.process:
        run_processing_cycle()
    elif args.digest:
        jobs_today = get_todays_processed_jobs(DB_PATH)
        send_daily_digest(jobs_today)
    elif args.test_job:
        run_test_job()
    else:
        # Default: one full cycle
        run_collection_cycle()
        run_processing_cycle()


if __name__ == "__main__":
    main()
