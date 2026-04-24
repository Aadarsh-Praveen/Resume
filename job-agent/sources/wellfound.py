"""
Wellfound (formerly AngelList Talent) job scraper.

Fetches Data Science / ML / AI jobs from Wellfound's role-based pages.
Uses the public role search endpoint — no login required for listings.
"""

import logging
import re
import time
import requests

logger = logging.getLogger(__name__)

_BASE = "https://wellfound.com"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://wellfound.com/jobs",
}

# Wellfound role slugs for DS/ML/AI
_ROLE_SLUGS = [
    "data-scientist",
    "machine-learning-engineer",
    "ai-engineer",
    "research-scientist",
    "applied-scientist",
]


def fetch_wellfound_jobs(role_slugs=None, max_per_role=40) -> list[dict]:
    """Fetch jobs from Wellfound role pages."""
    role_slugs = role_slugs or _ROLE_SLUGS
    seen_urls: set[str] = set()
    all_jobs: list[dict] = []

    for slug in role_slugs:
        try:
            url = f"{_BASE}/role/r/{slug}"
            resp = requests.get(url, headers=_HEADERS, timeout=15)
            if resp.status_code != 200:
                logger.warning("Wellfound: HTTP %d for role '%s'", resp.status_code, slug)
                time.sleep(2)
                continue

            jobs = _parse_role_page(resp.text, slug, max_per_role)
            for job in jobs:
                if job["url"] not in seen_urls:
                    seen_urls.add(job["url"])
                    all_jobs.append(job)

            logger.info("Wellfound '%s': %d jobs (total %d)", slug, len(jobs), len(all_jobs))
            time.sleep(2)

        except Exception as e:
            logger.warning("Wellfound fetch error for '%s': %s", slug, e)
            time.sleep(2)

    logger.info("Wellfound total: %d unique jobs", len(all_jobs))
    return all_jobs


def _parse_role_page(html: str, slug: str, limit: int) -> list[dict]:
    """Parse job listings from a Wellfound role page."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("BeautifulSoup not installed — Wellfound parsing skipped")
        return []

    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    # Wellfound job cards use data attributes or specific selectors
    for card in soup.select("div[class*='job'], a[href*='/jobs/']")[:limit * 2]:
        href = card.get("href", "") if card.name == "a" else ""
        if not href:
            link = card.select_one("a[href*='/jobs/']")
            href = link.get("href", "") if link else ""
        if not href:
            continue
        if not href.startswith("http"):
            href = _BASE + href

        title_el = card.select_one("h2, h3, [class*='title'], [class*='role']")
        company_el = card.select_one("[class*='company'], [class*='startup']")
        location_el = card.select_one("[class*='location'], [class*='remote']")

        title = title_el.get_text(strip=True) if title_el else _slug_to_title(slug)
        company = company_el.get_text(strip=True) if company_el else ""
        location = location_el.get_text(strip=True) if location_el else "Remote / US"

        if title and href and href not in {j["url"] for j in jobs}:
            jobs.append({
                "title": title,
                "company": company or "Wellfound Company",
                "url": href,
                "location": location,
                "source": "wellfound",
            })
        if len(jobs) >= limit:
            break

    return jobs


def _slug_to_title(slug: str) -> str:
    return slug.replace("-", " ").title()
