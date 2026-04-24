"""
Mayo Clinic job scraper — Taleo ATS.

Fetches Data Science / ML / AI jobs from Mayo Clinic's careers portal
(jobs.mayoclinic.org), which runs on Oracle Taleo.
"""

import logging
import time
import requests
from config import ROLE_KEYWORDS, EXCLUDE_KEYWORDS

logger = logging.getLogger(__name__)


def _is_relevant(title: str) -> bool:
    t = title.lower()
    if not any(kw in t for kw in ROLE_KEYWORDS):
        return False
    if any(kw in t for kw in EXCLUDE_KEYWORDS):
        return False
    return True

_BASE = "https://jobs.mayoclinic.org"
_SEARCH_URL = f"{_BASE}/search-jobs"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://jobs.mayoclinic.org/",
}

_QUERIES = [
    "data scientist",
    "machine learning",
    "artificial intelligence",
    "data analytics",
    "research scientist",
]


def fetch_mayo_clinic_jobs(queries=None, max_per_query=20) -> list[dict]:
    """Fetch jobs from Mayo Clinic Taleo careers portal."""
    queries = queries or _QUERIES
    seen_urls: set[str] = set()
    all_jobs: list[dict] = []

    for query in queries:
        try:
            # Taleo URL pattern: /search-jobs/{query}/
            url = f"{_SEARCH_URL}/{requests.utils.quote(query)}/"
            resp = requests.get(url, headers=_HEADERS, timeout=15)

            if resp.status_code != 200:
                # Try alternative param style
                resp = requests.get(
                    _SEARCH_URL,
                    params={"keyword": query},
                    headers=_HEADERS,
                    timeout=15,
                )

            if resp.status_code != 200:
                logger.warning("Mayo Clinic: HTTP %d for query '%s'", resp.status_code, query)
                time.sleep(2)
                continue

            jobs = _parse_taleo_page(resp.text, max_per_query)
            for job in jobs:
                if job["url"] not in seen_urls:
                    seen_urls.add(job["url"])
                    all_jobs.append(job)

            logger.info("Mayo Clinic '%s': %d jobs (total %d)", query, len(jobs), len(all_jobs))
            time.sleep(2)

        except Exception as e:
            logger.warning("Mayo Clinic fetch error for '%s': %s", query, e)
            time.sleep(2)

    logger.info("Mayo Clinic total: %d unique jobs", len(all_jobs))
    return all_jobs


def _parse_taleo_page(html: str, limit: int) -> list[dict]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("BeautifulSoup not installed — Mayo Clinic HTML parsing skipped")
        return []

    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    # Taleo job listing selectors
    selectors = [
        "li.list-item",
        ".job-listing",
        "[class*='job-tile']",
        "article[class*='job']",
        ".search-results-item",
    ]

    cards = []
    for sel in selectors:
        cards = soup.select(sel)
        if cards:
            break

    # Fallback: any link with /job/ in the href
    if not cards:
        cards = soup.select("a[href*='/job/'], a[href*='/jobs/']")

    for card in cards[:limit]:
        if card.name == "a":
            href = card.get("href", "")
            title = card.get_text(strip=True)
            company = "Mayo Clinic"
            location = "Rochester, MN"
        else:
            title_el = card.select_one("a, h2, h3, [class*='title']")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "") if title_el.name == "a" else (
                title_el.select_one("a").get("href", "") if title_el.select_one("a") else ""
            )
            company = "Mayo Clinic"
            location_el = card.select_one("[class*='location'], [class*='city']")
            location = location_el.get_text(strip=True) if location_el else "Rochester, MN"

        if not href.startswith("http"):
            href = _BASE + href

        if title and href and _is_relevant(title):
            jobs.append({
                "title": title,
                "company": company,
                "url": href,
                "location": location,
                "source": "mayo_clinic",
            })

    return jobs
