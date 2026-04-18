"""
Auto-apply to Greenhouse and Lever jobs via their form POST endpoints.

Flow:
  1. Detect ATS from job URL or source field
  2. Fetch required form fields from the job's question endpoint
  3. Build multipart form data (resume PDF + cover letter + profile fields)
  4. POST the application
  5. Return (success, application_id)

Both Greenhouse and Lever applications only fire AFTER user approves on the dashboard.
"""

import logging
import os
import re
import time
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


# ── Greenhouse ────────────────────────────────────────────────────────────────

def _greenhouse_slug_and_id(url: str) -> tuple[str, str]:
    """
    Extract (slug, job_id) from a Greenhouse job URL.
    Handles formats:
      https://boards.greenhouse.io/stripe/jobs/12345
      https://job-boards.greenhouse.io/stripe/jobs/12345
      https://careers.stripe.com/?gh_jid=12345
    """
    # Standard Greenhouse board URL
    m = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", url)
    if m:
        return m.group(1), m.group(2)
    # Company career page with ?gh_jid= or &gh_jid=
    m2 = re.search(r"gh_jid=(\d+)", url)
    if m2:
        # Need slug too — try to fetch the page and extract it
        # For now return empty slug and rely on caller to handle
        return "", m2.group(1)
    return "", ""


def _greenhouse_get_questions(slug: str, job_id: str) -> list[dict]:
    """Fetch required form fields from Greenhouse questions API."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}?questions=true"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("questions", [])
    except Exception as e:
        logger.warning("Greenhouse questions fetch failed: %s", e)
        return []


def _greenhouse_answer_custom_questions(
    questions: list[dict],
    jd_text: str,
    profile: dict,
) -> list[dict]:
    """
    Answer custom (non-standard) Greenhouse questions using Claude.
    Returns list of {"question_id": ..., "text_value": ...} dicts.
    """
    standard_labels = {
        "first name", "last name", "email", "phone", "resume", "cover letter",
        "linkedin profile", "website", "location", "city", "state", "country",
    }
    custom_qs = []
    for q in questions:
        label = q.get("label", "").lower().strip()
        if label in standard_labels:
            continue
        for field in q.get("fields", []):
            if field.get("type") in ("input_text", "textarea"):
                custom_qs.append({
                    "question_id": field.get("name") or q.get("id"),
                    "label": q.get("label", ""),
                })

    if not custom_qs:
        return []

    try:
        import anthropic
        client = anthropic.Anthropic()
        q_list = "\n".join(f"- {q['label']}" for q in custom_qs)
        prompt = (
            f"Answer these job application questions for the applicant.\n\n"
            f"Applicant: {profile['first_name']} {profile['last_name']}\n"
            f"Job description excerpt:\n{jd_text[:2000]}\n\n"
            f"Questions:\n{q_list}\n\n"
            f"For each question, give a concise 1-2 sentence answer. "
            f"Format: QUESTION: <label>\nANSWER: <answer>\n---"
        )
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text
        answers = {}
        for block in text.split("---"):
            q_match = re.search(r"QUESTION:\s*(.+)", block)
            a_match = re.search(r"ANSWER:\s*(.+)", block, re.DOTALL)
            if q_match and a_match:
                answers[q_match.group(1).strip()] = a_match.group(1).strip()

        return [
            {"question_id": q["question_id"], "text_value": answers.get(q["label"], "")}
            for q in custom_qs
            if answers.get(q["label"])
        ]
    except Exception as e:
        logger.warning("Custom question answering failed: %s", e)
        return []


def apply_greenhouse(job: dict) -> tuple[bool, str]:
    """
    Submit a Greenhouse job application.
    Returns (success, application_id).
    """
    url = job.get("url", "")
    slug, job_id = _greenhouse_slug_and_id(url)
    if not slug or not job_id:
        logger.warning("Could not extract Greenhouse slug/job_id from URL: %s", url)
        return False, ""

    profile    = _profile()
    pdf_path   = job.get("pdf_path", "")
    cover_text = job.get("cover_letter", "")

    if not all([profile["first_name"], profile["email"]]):
        logger.warning("Applicant profile incomplete — set APPLICANT_* env vars")
        return False, ""
    if not pdf_path or not Path(pdf_path).exists():
        logger.warning("Resume PDF not found at: %s", pdf_path)
        return False, ""

    questions      = _greenhouse_get_questions(slug, job_id)
    custom_answers = _greenhouse_answer_custom_questions(questions, job.get("jd_text", ""), profile)

    apply_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}/applications"

    try:
        with open(pdf_path, "rb") as pdf_file:
            files = {
                "job_application[first_name]":    (None, profile["first_name"]),
                "job_application[last_name]":     (None, profile["last_name"]),
                "job_application[email]":         (None, profile["email"]),
                "job_application[phone]":         (None, profile["phone"]),
                "job_application[resume]":        (Path(pdf_path).name, pdf_file, "application/pdf"),
                "job_application[cover_letter_text]": (None, cover_text),
            }
            if profile["linkedin_url"]:
                files["job_application[linkedin_profile_url]"] = (None, profile["linkedin_url"])
            if profile["portfolio_url"]:
                files["job_application[website]"] = (None, profile["portfolio_url"])

            for i, ans in enumerate(custom_answers):
                files[f"job_application[answers_attributes][{i}][question_id]"] = (None, str(ans["question_id"]))
                files[f"job_application[answers_attributes][{i}][text_value]"]  = (None, ans["text_value"])

            resp = requests.post(
                apply_url,
                files=files,
                headers={"User-Agent": "Mozilla/5.0 (compatible; JobAgent/1.0)"},
                timeout=REQUEST_TIMEOUT,
            )

        if resp.status_code in (200, 201):
            data = resp.json() if resp.content else {}
            app_id = str(data.get("id", "submitted"))
            logger.info("Greenhouse application submitted: %s @ %s — ID %s",
                        job.get("title"), job.get("company"), app_id)
            return True, app_id

        logger.warning("Greenhouse apply returned %d: %s", resp.status_code, resp.text[:300])
        return False, ""

    except Exception as e:
        logger.error("Greenhouse apply exception: %s", e)
        return False, ""


# ── Lever ─────────────────────────────────────────────────────────────────────

def _lever_slug_and_id(url: str) -> tuple[str, str]:
    """
    Extract (slug, posting_id) from a Lever job URL.
    Format: https://jobs.lever.co/{slug}/{uuid}
    """
    m = re.search(r"jobs\.lever\.co/([^/]+)/([a-f0-9-]{36})", url)
    if m:
        return m.group(1), m.group(2)
    return "", ""


def apply_lever(job: dict) -> tuple[bool, str]:
    """
    Submit a Lever job application.
    Returns (success, application_id).
    """
    url = job.get("url", "")
    slug, posting_id = _lever_slug_and_id(url)
    if not slug or not posting_id:
        logger.warning("Could not extract Lever slug/posting_id from URL: %s", url)
        return False, ""

    profile    = _profile()
    pdf_path   = job.get("pdf_path", "")
    cover_text = job.get("cover_letter", "")

    if not all([profile["first_name"], profile["email"]]):
        logger.warning("Applicant profile incomplete — set APPLICANT_* env vars")
        return False, ""
    if not pdf_path or not Path(pdf_path).exists():
        logger.warning("Resume PDF not found at: %s", pdf_path)
        return False, ""

    apply_url = f"https://jobs.lever.co/{slug}/{posting_id}/apply"

    try:
        with open(pdf_path, "rb") as pdf_file:
            full_name = f"{profile['first_name']} {profile['last_name']}".strip()
            files = {
                "name":     (None, full_name),
                "email":    (None, profile["email"]),
                "phone":    (None, profile["phone"]),
                "comments": (None, cover_text),
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

        # Lever returns a redirect to a "thank you" page on success
        if resp.status_code in (200, 201, 302) and "thank" in resp.url.lower():
            logger.info("Lever application submitted: %s @ %s",
                        job.get("title"), job.get("company"))
            return True, "lever-submitted"

        if resp.status_code in (200, 201):
            logger.info("Lever application likely submitted (status %d): %s",
                        resp.status_code, job.get("company"))
            return True, "lever-submitted"

        logger.warning("Lever apply returned %d: %s", resp.status_code, resp.text[:300])
        return False, ""

    except Exception as e:
        logger.error("Lever apply exception: %s", e)
        return False, ""


# ── Dispatcher ────────────────────────────────────────────────────────────────

def apply_job(job: dict) -> tuple[bool, str]:
    """
    Detect ATS from job source or URL and dispatch to the right apply function.
    Returns (success, application_id).

    Falls back to (False, "") for unsupported sources — the dashboard
    marks those as 'approved' so the user can apply manually.
    """
    source = (job.get("source") or "").lower()
    url    = (job.get("url") or "").lower()

    if source == "greenhouse" or "greenhouse.io" in url or "gh_jid" in url:
        return apply_greenhouse(job)

    if source == "lever" or "lever.co" in url:
        return apply_lever(job)

    logger.info("No auto-apply support for source '%s' — requires manual submission", source)
    return False, ""
