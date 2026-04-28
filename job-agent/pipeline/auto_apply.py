"""
Auto-apply to Greenhouse and Lever jobs via their form POST endpoints.

Flow (Greenhouse):
  1. User clicks Approve in dashboard  →  api_approve fires
  2. Fetch Greenhouse form questions
  3. Classify every question (profile.yaml / Claude / EEO / pending)
  4. Save all classifications to pending_answers DB table
  5a. If every required question has an answer → POST the application now
  5b. If any required question is unanswered   → return status "pending_questions"
       Dashboard shows the unanswered questions; user fills them in + clicks Submit
  6. submit_pending_answers() is called from the dashboard endpoint — loads all
     answers from DB and POSTs the final application

Lever: no public question API; standard fields only. Always submits directly.
Other sources: no auto-apply support; returns status "no_autoapply".
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30


# ── Applicant profile from .env ───────────────────────────────────────────────

def _profile() -> dict:
    return {
        "first_name":    os.getenv("APPLICANT_FIRST_NAME", ""),
        "last_name":     os.getenv("APPLICANT_LAST_NAME", ""),
        "email":         os.getenv("APPLICANT_EMAIL", ""),
        "phone":         os.getenv("APPLICANT_PHONE", ""),
        "linkedin_url":  os.getenv("APPLICANT_LINKEDIN_URL", ""),
        "portfolio_url": os.getenv("APPLICANT_PORTFOLIO_URL", ""),
    }


# ── Greenhouse URL parsing ────────────────────────────────────────────────────

def _greenhouse_slug_and_id(url: str) -> tuple[str, str]:
    """
    Extract (slug, job_id) from a Greenhouse job URL.
    Handles:
      https://boards.greenhouse.io/stripe/jobs/12345
      https://job-boards.greenhouse.io/stripe/jobs/12345
      https://careers.stripe.com/?gh_jid=12345
    """
    m = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", url)
    if m:
        return m.group(1), m.group(2)
    m2 = re.search(r"gh_jid=(\d+)", url)
    if m2:
        return "", m2.group(1)
    return "", ""


def _greenhouse_get_questions(slug: str, job_id: str) -> list[dict]:
    """Fetch form questions from Greenhouse Job Board API."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}?questions=true"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("questions", [])
    except Exception as e:
        logger.warning("Greenhouse questions fetch failed: %s", e)
        return []


# ── Form POST builder ─────────────────────────────────────────────────────────

def _build_form_fields(
    profile: dict,
    pdf_path: str,
    cover_text: str,
    answered_questions: list[dict],
) -> dict:
    """
    Build the multipart form fields dict for a Greenhouse application POST.
    answered_questions: rows from pending_answers with non-null answer.
    """
    files = {
        "job_application[first_name]":        (None, profile["first_name"]),
        "job_application[last_name]":         (None, profile["last_name"]),
        "job_application[email]":             (None, profile["email"]),
        "job_application[phone]":             (None, profile["phone"]),
        "job_application[cover_letter_text]": (None, cover_text or ""),
    }
    if profile["linkedin_url"]:
        files["job_application[linkedin_profile_url]"] = (None, profile["linkedin_url"])
    if profile["portfolio_url"]:
        files["job_application[website]"] = (None, profile["portfolio_url"])

    # Attach resume PDF separately (caller opens the file)
    # (handled by caller so the file handle stays valid during POST)

    for i, q in enumerate(answered_questions):
        qid = q["field_name"]
        ans = q["answer"]
        files[f"job_application[answers_attributes][{i}][question_id]"] = (None, str(qid))
        files[f"job_application[answers_attributes][{i}][text_value]"]  = (None, str(ans))

    return files


# ── Greenhouse apply ──────────────────────────────────────────────────────────

def apply_greenhouse(job: dict, client=None) -> dict:
    """
    Classify Greenhouse form questions and submit if all answerable.

    Returns dict with keys:
      status          "applied" | "pending_questions" | "failed" | "no_autoapply"
      application_id  str (on success)
      pending_count   int (number of unanswered questions)
      total_count     int
    """
    from pipeline.question_classifier import classify_and_answer
    from pipeline.dedup import save_pending_questions, count_unanswered

    url = job.get("url", "")
    slug, job_id = _greenhouse_slug_and_id(url)
    if not slug or not job_id:
        logger.warning("Could not extract Greenhouse slug/job_id from: %s", url)
        return {"status": "no_autoapply", "application_id": "", "pending_count": 0, "total_count": 0}

    profile    = _profile()
    pdf_path   = job.get("pdf_path", "")
    cover_text = job.get("cover_letter", "")

    if not all([profile["first_name"], profile["email"]]):
        logger.warning("Applicant profile incomplete — set APPLICANT_* env vars")
        return {"status": "failed", "application_id": "", "pending_count": 0, "total_count": 0}
    if not pdf_path or not Path(pdf_path).exists():
        logger.warning("Resume PDF not found at: %s", pdf_path)
        return {"status": "failed", "application_id": "", "pending_count": 0, "total_count": 0}

    questions = _greenhouse_get_questions(slug, job_id)
    if not questions:
        logger.info("No questions returned for %s — submitting standard fields only", job.get("company"))

    classified = classify_and_answer(
        questions,
        jd_text=job.get("jd_text", ""),
        resume_text=_load_resume_text(pdf_path),
        client=client,
    )

    # Persist all classifications (answered + pending) to DB
    db_id = job.get("id") or job.get("db_id")
    if db_id:
        save_pending_questions(int(db_id), classified)

    unanswered = [q for q in classified if q["answer"] is None]
    required_unanswered = [q for q in unanswered if q["required"]]

    if required_unanswered:
        logger.info(
            "%s — %d required question(s) need user input before applying",
            job.get("company"), len(required_unanswered),
        )
        return {
            "status":       "pending_questions",
            "application_id": "",
            "pending_count": len(unanswered),
            "total_count":   len(classified),
        }

    # All required questions answered — submit now
    answered = [q for q in classified if q["answer"] is not None]
    return _post_greenhouse(job, slug, job_id, profile, pdf_path, cover_text, answered)


def _post_greenhouse(
    job: dict,
    slug: str,
    job_id: str,
    profile: dict,
    pdf_path: str,
    cover_text: str,
    answered_questions: list[dict],
) -> dict:
    """POST the Greenhouse application form. Returns result dict."""
    from pipeline.dedup import delete_pending_questions

    apply_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}/applications"
    files     = _build_form_fields(profile, pdf_path, cover_text, answered_questions)

    try:
        with open(pdf_path, "rb") as pdf_file:
            files["job_application[resume]"] = (Path(pdf_path).name, pdf_file, "application/pdf")
            resp = requests.post(
                apply_url,
                files=files,
                headers={"User-Agent": "Mozilla/5.0 (compatible; JobAgent/1.0)"},
                timeout=REQUEST_TIMEOUT,
            )

        if resp.status_code in (200, 201):
            data   = resp.json() if resp.content else {}
            app_id = str(data.get("id", "submitted"))
            logger.info("Greenhouse applied: %s @ %s — ID %s",
                        job.get("title"), job.get("company"), app_id)
            db_id = job.get("id") or job.get("db_id")
            if db_id:
                delete_pending_questions(int(db_id))
            return {"status": "applied", "application_id": app_id,
                    "pending_count": 0, "total_count": len(answered_questions)}

        logger.warning("Greenhouse POST returned %d: %s", resp.status_code, resp.text[:300])
        return {"status": "failed", "application_id": "", "pending_count": 0,
                "total_count": len(answered_questions)}

    except Exception as e:
        logger.error("Greenhouse apply exception: %s", e)
        return {"status": "failed", "application_id": "", "pending_count": 0,
                "total_count": len(answered_questions)}


def submit_pending_answers(job: dict) -> dict:
    """
    Called from the dashboard after the user has filled in pending questions.
    Loads all answers from DB and re-submits the Greenhouse form.
    """
    from pipeline.dedup import get_pending_questions

    url  = job.get("url", "")
    slug, job_id = _greenhouse_slug_and_id(url)
    if not slug or not job_id:
        return {"status": "no_autoapply", "application_id": "", "pending_count": 0, "total_count": 0}

    profile    = _profile()
    pdf_path   = job.get("pdf_path", "")
    cover_text = job.get("cover_letter", "")

    if not all([profile["first_name"], profile["email"]]):
        return {"status": "failed", "application_id": "", "pending_count": 0, "total_count": 0}
    if not pdf_path or not Path(pdf_path).exists():
        return {"status": "failed", "application_id": "", "pending_count": 0, "total_count": 0}

    db_id = job.get("id") or job.get("db_id")
    all_qs = get_pending_questions(int(db_id)) if db_id else []
    answered = [q for q in all_qs if q["answer"] is not None]

    return _post_greenhouse(job, slug, job_id, profile, pdf_path, cover_text, answered)


# ── Lever ─────────────────────────────────────────────────────────────────────

def _lever_slug_and_id(url: str) -> tuple[str, str]:
    m = re.search(r"jobs\.lever\.co/([^/]+)/([a-f0-9-]{36})", url)
    if m:
        return m.group(1), m.group(2)
    return "", ""


def apply_lever(job: dict) -> dict:
    """Submit a Lever job application (standard fields only). Returns result dict."""
    url = job.get("url", "")
    slug, posting_id = _lever_slug_and_id(url)
    if not slug or not posting_id:
        logger.warning("Could not extract Lever slug/posting_id from: %s", url)
        return {"status": "no_autoapply", "application_id": "", "pending_count": 0, "total_count": 0}

    profile    = _profile()
    pdf_path   = job.get("pdf_path", "")
    cover_text = job.get("cover_letter", "")

    if not all([profile["first_name"], profile["email"]]):
        return {"status": "failed", "application_id": "", "pending_count": 0, "total_count": 0}
    if not pdf_path or not Path(pdf_path).exists():
        return {"status": "failed", "application_id": "", "pending_count": 0, "total_count": 0}

    apply_url = f"https://jobs.lever.co/{slug}/{posting_id}/apply"

    try:
        with open(pdf_path, "rb") as pdf_file:
            full_name = f"{profile['first_name']} {profile['last_name']}".strip()
            files = {
                "name":     (None, full_name),
                "email":    (None, profile["email"]),
                "phone":    (None, profile["phone"]),
                "comments": (None, cover_text or ""),
                "resume":   (Path(pdf_path).name, pdf_file, "application/pdf"),
            }
            if profile["linkedin_url"]:
                files["urls[LinkedIn]"] = (None, profile["linkedin_url"])
            if profile["portfolio_url"]:
                files["urls[Portfolio]"] = (None, profile["portfolio_url"])

            resp = requests.post(
                apply_url,
                files=files,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; JobAgent/1.0)",
                    "Referer": f"https://jobs.lever.co/{slug}/{posting_id}",
                    "Origin":  "https://jobs.lever.co",
                },
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )

        if resp.status_code in (200, 201, 302) and "thank" in resp.url.lower():
            logger.info("Lever applied: %s @ %s", job.get("title"), job.get("company"))
            return {"status": "applied", "application_id": "lever-submitted",
                    "pending_count": 0, "total_count": 0}

        if resp.status_code in (200, 201):
            logger.info("Lever applied (status %d): %s", resp.status_code, job.get("company"))
            return {"status": "applied", "application_id": "lever-submitted",
                    "pending_count": 0, "total_count": 0}

        logger.warning("Lever POST returned %d: %s", resp.status_code, resp.text[:300])
        return {"status": "failed", "application_id": "", "pending_count": 0, "total_count": 0}

    except Exception as e:
        logger.error("Lever apply exception: %s", e)
        return {"status": "failed", "application_id": "", "pending_count": 0, "total_count": 0}


# ── Dispatcher ────────────────────────────────────────────────────────────────

def apply_job(job: dict, client=None) -> dict:
    """
    Detect ATS and dispatch to the right apply function.

    Returns dict:
      status          "applied" | "pending_questions" | "failed" | "no_autoapply"
      application_id  str
      pending_count   int
      total_count     int
    """
    source = (job.get("source") or "").lower()
    url    = (job.get("url") or "").lower()

    if source == "greenhouse" or "greenhouse.io" in url or "gh_jid" in url:
        return apply_greenhouse(job, client=client)

    if source == "lever" or "lever.co" in url:
        return apply_lever(job)

    logger.info("No auto-apply for source '%s' — manual submission required", source)
    return {"status": "no_autoapply", "application_id": "", "pending_count": 0, "total_count": 0}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_resume_text(pdf_path: str) -> str:
    """Extract text from resume PDF for Claude context (best-effort)."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        return "\n".join(p.extract_text() or "" for p in reader.pages)[:3000]
    except Exception:
        return ""
