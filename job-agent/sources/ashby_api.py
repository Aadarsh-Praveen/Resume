"""
Ashby ATS open API poller.

Ashby is used by many fast-growing AI startups (Ramp, Brex, Linear, Vercel).
The API is public and requires no authentication.

Endpoint: https://api.ashbyhq.com/posting-api/job-board/{slug}
"""

import logging
import time
from typing import Optional

import requests

from config import ASHBY_COMPANIES, ROLE_KEYWORDS, EXCLUDE_KEYWORDS

logger = logging.getLogger(__name__)

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"
REQUEST_TIMEOUT = 15


def _is_relevant(title: str, description: str = "") -> bool:
    combined = (title + " " + description).lower()
    if not any(kw in combined for kw in ROLE_KEYWORDS):
        return False
    if any(kw in combined for kw in EXCLUDE_KEYWORDS):
        return False
    return True


def _clean_html(html: str) -> str:
    import re
    from html import unescape
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch_company_jobs(slug: str, company_name: str) -> list[dict]:
    """Fetch all jobs for a single Ashby company."""
    url = BASE_URL.format(slug=slug)
    jobs = []

    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 404:
                logger.info("Ashby: no board found for %s", slug)
                return []
            resp.raise_for_status()
            data = resp.json()
            break
        except requests.RequestException as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
                logger.warning("Ashby fetch attempt %d for %s failed: %s", attempt + 1, slug, e)
            else:
                logger.error("Ashby: all retries failed for %s: %s", slug, e)
                return []

    for posting in data.get("jobPostings", []):
        title = posting.get("title", "").strip()
        job_url = posting.get("jobUrl") or posting.get("applyUrl", "")
        description_html = posting.get("descriptionHtml") or posting.get("description", "")
        description = _clean_html(description_html)

        if not title or not job_url:
            continue
        if not _is_relevant(title, description):
            continue

        location = posting.get("locationName") or posting.get("location", "")
        team = posting.get("departmentName") or posting.get("team", "")

        jobs.append({
            "title": title,
            "company": company_name,
            "url": job_url,
            "jd_text": description[:3000],
            "source": "ashby",
            "posted_date": posting.get("publishedAt", ""),
            "location": location,
            "team": team,
        })

    return jobs


def fetch_ashby_jobs(companies: Optional[dict] = None) -> list[dict]:
    """
    Fetch jobs from all configured Ashby company boards.

    Args:
        companies: Dict mapping slug → display name.
                   Defaults to config.ASHBY_COMPANIES.

    Returns:
        List of job dicts.
    """
    if companies is None:
        companies = ASHBY_COMPANIES

    all_jobs: list[dict] = []

    for slug, name in companies.items():
        logger.info("Polling Ashby: %s (%s)", name, slug)
        jobs = _fetch_company_jobs(slug, name)
        logger.info("Ashby %s: %d relevant jobs", name, len(jobs))
        all_jobs.extend(jobs)
        time.sleep(0.5)

    logger.info("Ashby total: %d jobs", len(all_jobs))
    return all_jobs
