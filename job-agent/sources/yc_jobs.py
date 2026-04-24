"""
Y Combinator job scraper — workatastartup.com

Fetches Data Science / ML / AI jobs from YC-backed startups using the
public search endpoint. Returns jobs in the standard agent dict format.
"""

import logging
import time
import requests

logger = logging.getLogger(__name__)

_BASE = "https://www.workatastartup.com"
_SEARCH_URL = f"{_BASE}/jobs"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.workatastartup.com/jobs",
}

_QUERIES = [
    "data scientist",
    "machine learning engineer",
    "AI engineer",
    "ML engineer",
    "applied scientist",
]


def fetch_yc_jobs(queries=None, max_per_query=50) -> list[dict]:
    """Fetch jobs from YC's Work at a Startup board."""
    queries = queries or _QUERIES
    seen_urls: set[str] = set()
    all_jobs: list[dict] = []

    for query in queries:
        try:
            params = {
                "q": query,
                "remote": "true",
                "jobType": "fulltime",
            }
            resp = requests.get(
                _SEARCH_URL,
                params=params,
                headers=_HEADERS,
                timeout=15,
            )
            if resp.status_code != 200:
                logger.warning("YC jobs: HTTP %d for query '%s'", resp.status_code, query)
                time.sleep(2)
                continue

            # Try JSON first (API response), fall back to HTML scraping
            content_type = resp.headers.get("Content-Type", "")
            if "json" in content_type:
                data = resp.json()
                jobs_raw = data.get("jobs", data.get("results", []))
                for j in jobs_raw[:max_per_query]:
                    job = _map_json_job(j)
                    if job and job["url"] not in seen_urls:
                        seen_urls.add(job["url"])
                        all_jobs.append(job)
            else:
                # HTML — extract job cards
                jobs_raw = _parse_html(resp.text, max_per_query)
                for job in jobs_raw:
                    if job["url"] not in seen_urls:
                        seen_urls.add(job["url"])
                        all_jobs.append(job)

            logger.info("YC '%s': %d jobs collected so far", query, len(all_jobs))
            time.sleep(2)

        except Exception as e:
            logger.warning("YC jobs fetch error for '%s': %s", query, e)
            time.sleep(2)

    logger.info("YC total: %d unique jobs", len(all_jobs))
    return all_jobs


def _map_json_job(j: dict) -> dict | None:
    title = j.get("title") or j.get("role", "")
    company = (j.get("company") or {}).get("name") or j.get("company_name", "")
    job_id = j.get("id", "")
    url = j.get("url") or (f"{_BASE}/jobs/{job_id}" if job_id else "")
    location = j.get("location") or j.get("remote_ok", "")
    if isinstance(location, bool):
        location = "Remote" if location else ""

    if not title or not company or not url:
        return None

    return {
        "title": title,
        "company": company,
        "url": url,
        "location": location if location else "Remote",
        "source": "yc",
    }


def _parse_html(html: str, limit: int) -> list[dict]:
    """Minimal HTML scraper for workatastartup job cards."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("BeautifulSoup not installed — YC HTML parsing skipped")
        return []

    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    for card in soup.select("a[href*='/jobs/']")[:limit]:
        href = card.get("href", "")
        if not href.startswith("http"):
            href = _BASE + href

        title_el = card.select_one("h2, h3, .job-title, [class*='title']")
        company_el = card.select_one(".company-name, [class*='company']")

        title = title_el.get_text(strip=True) if title_el else ""
        company = company_el.get_text(strip=True) if company_el else ""

        if title and href:
            jobs.append({
                "title": title,
                "company": company or "YC Company",
                "url": href,
                "location": "Remote",
                "source": "yc",
            })

    return jobs
