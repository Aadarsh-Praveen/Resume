"""
Lever ATS open API poller.

Lever provides a public, unauthenticated API for job listings.
No API key required.

Endpoint: https://api.lever.co/v0/postings/{company}?mode=json
"""

import logging
import time
from typing import Optional

import requests

from config import LEVER_COMPANIES, ROLE_KEYWORDS, EXCLUDE_KEYWORDS

logger = logging.getLogger(__name__)

BASE_URL = "https://api.lever.co/v0/postings/{slug}?mode=json"
REQUEST_TIMEOUT = 30


def _is_relevant(title: str, team: str = "", description: str = "") -> bool:
    combined = (title + " " + team + " " + description[:500]).lower()
    if not any(kw in combined for kw in ROLE_KEYWORDS):
        return False
    if any(kw in title.lower() for kw in EXCLUDE_KEYWORDS):
        return False
    return True


def _extract_text(lists: list) -> str:
    """Flatten Lever's content list structure into plain text."""
    parts = []
    for item in lists or []:
        content = item.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(str(c) for c in content)
    return " ".join(parts)


def _fetch_company_jobs(slug: str, company_name: str) -> list[dict]:
    """Fetch all jobs for a single Lever company."""
    url = BASE_URL.format(slug=slug)
    jobs = []

    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 404:
                logger.info("Lever: no postings found for %s", slug)
                return []
            resp.raise_for_status()
            postings = resp.json()
            break
        except requests.RequestException as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
                logger.warning("Lever fetch attempt %d for %s failed: %s", attempt + 1, slug, e)
            else:
                logger.error("Lever: all retries failed for %s: %s", slug, e)
                return []

    if not isinstance(postings, list):
        logger.warning("Unexpected Lever API response for %s", slug)
        return []

    for posting in postings:
        title = posting.get("text", "").strip()
        apply_url = posting.get("applyUrl") or posting.get("hostedUrl", "")
        hosted_url = posting.get("hostedUrl", "")
        job_url = apply_url or hosted_url

        # Extract JD text from Lever's nested content structure
        description_text = ""
        for key in ("descriptionPlain", "description"):
            val = posting.get(key, "")
            if val:
                import re
                description_text = re.sub(r"<[^>]+>", " ", val)
                break
        if not description_text:
            lists_content = posting.get("lists", [])
            description_text = _extract_text(lists_content)

        location = posting.get("categories", {}).get("location", "")
        team = posting.get("categories", {}).get("team", "")

        if not title or not job_url:
            continue
        if not _is_relevant(title, team, description_text):
            continue

        jobs.append({
            "title": title,
            "company": company_name,
            "url": job_url,
            "jd_text": description_text[:3000],
            "source": "lever",
            "posted_date": str(posting.get("createdAt", "")),
            "location": location,
            "team": team,
        })

    return jobs


def fetch_lever_jobs(companies: Optional[dict] = None) -> list[dict]:
    """
    Fetch jobs from all configured Lever company boards.

    Args:
        companies: Dict mapping slug → display name.
                   Defaults to config.LEVER_COMPANIES.

    Returns:
        List of job dicts.
    """
    if companies is None:
        companies = LEVER_COMPANIES

    all_jobs: list[dict] = []

    for slug, name in companies.items():
        logger.info("Polling Lever: %s (%s)", name, slug)
        jobs = _fetch_company_jobs(slug, name)
        logger.info("Lever %s: %d relevant jobs", name, len(jobs))
        all_jobs.extend(jobs)
        time.sleep(0.5)

    logger.info("Lever total: %d jobs", len(all_jobs))
    return all_jobs
