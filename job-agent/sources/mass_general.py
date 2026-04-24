"""
Mass General Brigham job scraper — iCIMS ATS.

Fetches Data Science / ML / AI jobs from the Mass General Brigham
careers portal (jobs.massgeneralbrigham.org), which runs on iCIMS.
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

_ICIMS_BASE = "https://careers-massgeneralbrigham.icims.com"
_SEARCH_URL = f"{_ICIMS_BASE}/jobs/search"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

_QUERIES = [
    "data scientist",
    "machine learning",
    "AI engineer",
    "data analytics",
    "research scientist",
]


def fetch_mass_general_jobs(queries=None, max_per_query=20) -> list[dict]:
    """Fetch jobs from Mass General Brigham iCIMS careers portal."""
    queries = queries or _QUERIES
    seen_urls: set[str] = set()
    all_jobs: list[dict] = []

    for query in queries:
        try:
            params = {
                "keyword": query,
                "in_iframe": "1",
            }
            resp = requests.get(
                _SEARCH_URL,
                params=params,
                headers=_HEADERS,
                timeout=15,
            )
            if resp.status_code != 200:
                logger.warning("MGB iCIMS: HTTP %d for query '%s'", resp.status_code, query)
                time.sleep(2)
                continue

            jobs = _parse_icims_response(resp, query, max_per_query)
            for job in jobs:
                if job["url"] not in seen_urls:
                    seen_urls.add(job["url"])
                    all_jobs.append(job)

            logger.info("MGB '%s': %d jobs (total %d)", query, len(jobs), len(all_jobs))
            time.sleep(2)

        except Exception as e:
            logger.warning("MGB fetch error for '%s': %s", query, e)
            time.sleep(2)

    logger.info("Mass General Brigham total: %d unique jobs", len(all_jobs))
    return all_jobs


def _parse_icims_response(resp, query: str, limit: int) -> list[dict]:
    content_type = resp.headers.get("Content-Type", "")

    # JSON response
    if "json" in content_type:
        try:
            data = resp.json()
            postings = data.get("postings", data.get("jobs", data.get("results", [])))
            return [_map_icims_job(j) for j in postings[:limit] if _map_icims_job(j)]
        except Exception:
            pass

    # HTML response — scrape with BeautifulSoup
    return _parse_icims_html(resp.text, limit)


def _map_icims_job(j: dict) -> dict | None:
    title = j.get("title") or j.get("job_title", "")
    job_id = j.get("id") or j.get("job_id", "")
    url = j.get("url") or j.get("apply_url") or (
        f"{_ICIMS_BASE}/jobs/{job_id}/job" if job_id else ""
    )
    location = j.get("location") or j.get("city", "Boston, MA")

    if not title or not url:
        return None
    if not _is_relevant(title):
        return None

    return {
        "title": title,
        "company": "Mass General Brigham",
        "url": url,
        "location": location,
        "source": "mass_general",
    }


def _parse_icims_html(html: str, limit: int) -> list[dict]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("BeautifulSoup not installed — MGB HTML parsing skipped")
        return []

    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    for row in soup.select(".iCIMS_JobsTable .iCIMS_JobsTable_Row, [class*='job-listing']")[:limit]:
        title_el = row.select_one(".iCIMS_JobTitle a, a[href*='/jobs/']")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        if not href.startswith("http"):
            href = _ICIMS_BASE + href
        location_el = row.select_one(".iCIMS_JobsTableLocation, [class*='location']")
        location = location_el.get_text(strip=True) if location_el else "Boston, MA"

        if title and href and _is_relevant(title):
            jobs.append({
                "title": title,
                "company": "Mass General Brigham",
                "url": href,
                "location": location,
                "source": "mass_general",
            })

    return jobs
