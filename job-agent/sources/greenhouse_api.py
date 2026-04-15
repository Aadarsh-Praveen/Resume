"""
Greenhouse ATS open API poller.

Greenhouse provides a public, unauthenticated API for fetching job listings.
No API key required.

Endpoint: https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs
"""

import logging
import time
from typing import Optional

import requests

from config import GREENHOUSE_COMPANIES, ROLE_KEYWORDS, EXCLUDE_KEYWORDS

logger = logging.getLogger(__name__)

BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
REQUEST_TIMEOUT = 15
RETRY_BACKOFF = 2


def _is_relevant(title: str, content: str = "") -> bool:
    combined = (title + " " + content).lower()
    if not any(kw in combined for kw in ROLE_KEYWORDS):
        return False
    if any(kw in combined for kw in EXCLUDE_KEYWORDS):
        return False
    return True


def _fetch_company_jobs(slug: str, company_name: str) -> list[dict]:
    """Fetch all jobs for a single Greenhouse company."""
    url = BASE_URL.format(slug=slug)
    jobs = []

    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 404:
                logger.info("Greenhouse: no board found for %s", slug)
                return []
            resp.raise_for_status()
            data = resp.json()
            break
        except requests.RequestException as e:
            if attempt < 2:
                wait = RETRY_BACKOFF ** attempt
                logger.warning("Greenhouse fetch attempt %d for %s failed: %s", attempt + 1, slug, e)
                time.sleep(wait)
            else:
                logger.error("Greenhouse: all retries failed for %s: %s", slug, e)
                return []

    for job in data.get("jobs", []):
        title = job.get("title", "").strip()
        job_url = job.get("absolute_url", "").strip()
        content = job.get("content", "") or ""

        if not title or not job_url:
            continue

        if not _is_relevant(title, content):
            continue

        location = ""
        if job.get("offices"):
            location = job["offices"][0].get("name", "")
        elif job.get("location"):
            location = job["location"].get("name", "")

        jobs.append({
            "title": title,
            "company": company_name,
            "url": job_url,
            "jd_text": _clean_content(content)[:3000],
            "source": "greenhouse",
            "posted_date": job.get("updated_at", ""),
            "location": location,
        })

    return jobs


def _clean_content(html_content: str) -> str:
    """Strip HTML tags from Greenhouse job content."""
    import re
    from html import unescape
    text = re.sub(r"<[^>]+>", " ", html_content or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_greenhouse_jobs(companies: Optional[dict] = None) -> list[dict]:
    """
    Fetch jobs from all configured Greenhouse company boards.

    Args:
        companies: Dict mapping slug → display name.
                   Defaults to config.GREENHOUSE_COMPANIES.

    Returns:
        List of job dicts.
    """
    if companies is None:
        companies = GREENHOUSE_COMPANIES

    all_jobs: list[dict] = []

    for slug, name in companies.items():
        logger.info("Polling Greenhouse: %s (%s)", name, slug)
        jobs = _fetch_company_jobs(slug, name)
        logger.info("Greenhouse %s: %d relevant jobs", name, len(jobs))
        all_jobs.extend(jobs)
        time.sleep(0.5)

    logger.info("Greenhouse total: %d jobs", len(all_jobs))
    return all_jobs
