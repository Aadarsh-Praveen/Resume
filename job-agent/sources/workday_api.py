"""
Workday JSON API job poller.

Many large companies (NVIDIA, Tesla, Apple, Salesforce, etc.) use Workday
as their ATS. Workday exposes a stable, unauthenticated JSON endpoint on
every tenant:

    POST https://{tenant}.wd5.myworkdayjobs.com/wday/cxs/{tenant}/{board}/jobs
    Body: {"limit": 20, "offset": 0, "searchText": "data scientist"}

This is far more reliable than Playwright scraping — returns structured JSON,
no browser automation, no HTML parsing.

Job URL format:
    https://{tenant}.wd5.myworkdayjobs.com/en-US/{board}/job/{externalPath}
"""

import logging
import re
import time
from typing import Optional

import requests

from config import ROLE_KEYWORDS, EXCLUDE_KEYWORDS, WORKDAY_API_COMPANIES

logger = logging.getLogger(__name__)

API_URL_TEMPLATE = (
    "https://{tenant}.wd5.myworkdayjobs.com/wday/cxs/{tenant}/{board}/jobs"
)
JOB_URL_TEMPLATE = (
    "https://{tenant}.wd5.myworkdayjobs.com/en-US/{board}/job/{path}"
)

REQUEST_TIMEOUT = 20
RESULTS_PER_COMPANY = 20

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def _is_relevant(title: str) -> bool:
    t = title.lower()
    if not any(kw in t for kw in ROLE_KEYWORDS):
        return False
    if any(kw in t for kw in EXCLUDE_KEYWORDS):
        return False
    return True


def _fetch_company_jobs(
    tenant: str,
    board: str,
    company_name: str,
    search_text: str,
) -> list[dict]:
    """Fetch jobs for one Workday company via the JSON API."""
    url = API_URL_TEMPLATE.format(tenant=tenant, board=board)
    payload = {
        "limit": RESULTS_PER_COMPANY,
        "offset": 0,
        "searchText": search_text,
    }

    for attempt in range(3):
        try:
            resp = requests.post(
                url,
                json=payload,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 404:
                logger.warning("Workday: board not found for %s (%s/%s)", company_name, tenant, board)
                return []
            if resp.status_code in (403, 429):
                logger.warning("Workday: blocked (%d) for %s — skipping", resp.status_code, company_name)
                return []
            resp.raise_for_status()
            data = resp.json()
            break
        except requests.RequestException as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
                logger.warning("Workday attempt %d failed for %s: %s", attempt + 1, company_name, e)
            else:
                logger.error("Workday: all retries failed for %s: %s", company_name, e)
                return []

    postings = data.get("jobPostings", [])
    if not postings:
        logger.info("Workday %s: no postings for '%s'", company_name, search_text)
        return []

    jobs = []
    for posting in postings:
        title = (posting.get("title") or "").strip()
        external_path = (posting.get("externalPath") or "").strip("/")
        location = posting.get("locationsText") or posting.get("primaryLocation", "")
        posted = posting.get("postedOn", "")

        # When locationsText is "N Locations", extract country/region from externalPath.
        # externalPath format: "job/{LocationCode}/{Title_JR#}"
        # LocationCode: {Country}-{State}-{City...} or {Country}-{City...}
        # e.g. "job/US-CA-Santa-Clara/..." → "US, CA, Santa Clara"
        #      "job/China-Shanghai/..."    → "China, Shanghai"
        if re.match(r"^\d+\s+location", (location or "").lower()):
            path_parts = external_path.split("/")
            if len(path_parts) >= 2:
                segs = path_parts[1].split("-")
                if len(segs) >= 3:
                    # Country-State-City (city may be multi-word)
                    location = f"{segs[0]}, {segs[1]}, {' '.join(segs[2:])}"
                elif len(segs) == 2:
                    location = f"{segs[0]}, {segs[1]}"
                else:
                    location = segs[0]
        bullet_fields = posting.get("jobDescription", {})
        description = (bullet_fields.get("items") or [{}])[0].get("text", "") if bullet_fields else ""

        if not title or not external_path:
            continue

        if not _is_relevant(title):
            continue

        job_url = JOB_URL_TEMPLATE.format(tenant=tenant, board=board, path=external_path)

        jobs.append({
            "title": title,
            "company": company_name,
            "url": job_url,
            "location": location,
            "jd_text": description[:3000] if description else "",
            "source": "workday",
            "posted_date": posted,
        })

    return jobs


def fetch_workday_jobs(companies: Optional[dict] = None) -> list[dict]:
    """
    Fetch jobs from all configured Workday companies.

    Args:
        companies: Dict of tenant → {board, name, search}
                   Defaults to config.WORKDAY_API_COMPANIES.

    Returns:
        List of job dicts.
    """
    if companies is None:
        companies = WORKDAY_API_COMPANIES

    all_jobs: list[dict] = []

    for tenant, cfg in companies.items():
        board = cfg["board"]
        name = cfg["name"]
        search = cfg.get("search", "data scientist")

        logger.info("Workday: polling %s (tenant: %s)", name, tenant)
        try:
            jobs = _fetch_company_jobs(tenant, board, name, search)
            logger.info("Workday %s: %d relevant jobs", name, len(jobs))
            all_jobs.extend(jobs)
        except Exception as e:
            logger.error("Workday: %s failed: %s", name, e)
        time.sleep(0.5)

    logger.info("Workday total: %d jobs", len(all_jobs))
    return all_jobs
