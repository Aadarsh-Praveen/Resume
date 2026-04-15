"""
Custom career page scrapers for companies that don't use a standard ATS.

Google, Meta, Microsoft, and Amazon each expose their own public job search
JSON endpoints — no authentication required.

Each fetcher returns the standard job dict format:
    {title, company, url, location, jd_text, source, posted_date}
"""

import logging
import time
from typing import Optional

import requests

from config import ROLE_KEYWORDS, EXCLUDE_KEYWORDS, CUSTOM_CAREER_COMPANIES

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def _is_relevant(title: str, description: str = "") -> bool:
    combined = (title + " " + description).lower()
    if not any(kw in combined for kw in ROLE_KEYWORDS):
        return False
    if any(kw in combined for kw in EXCLUDE_KEYWORDS):
        return False
    return True


# ── Google ────────────────────────────────────────────────────────────────────

def _fetch_google(search_terms: list[str]) -> list[dict]:
    """
    Google Careers public search API.
    Endpoint: https://careers.google.com/api/jobs/jobs-v1/search/
    """
    jobs = []
    seen: set[str] = set()

    for term in search_terms:
        url = "https://careers.google.com/api/jobs/jobs-v1/search/"
        params = {
            "q": term,
            "location": "United States",
            "employment_type": "FULL_TIME",
            "page_size": 20,
        }
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code in (403, 429):
                logger.warning("Google Careers: blocked (%d) — skipping '%s'", resp.status_code, term)
                continue
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.warning("Google Careers fetch failed for '%s': %s", term, e)
            continue

        for job in data.get("jobs", []):
            title = job.get("title", "").strip()
            apply_url = job.get("apply_url") or job.get("job_id", "")
            locations = [loc.get("display", "") for loc in job.get("locations", [])]
            location = ", ".join(filter(None, locations))
            description = job.get("description", "")

            if not title or not apply_url or apply_url in seen:
                continue
            if not _is_relevant(title, description):
                continue

            seen.add(apply_url)
            jobs.append({
                "title": title,
                "company": "Google",
                "url": apply_url if apply_url.startswith("http") else f"https://careers.google.com{apply_url}",
                "location": location,
                "jd_text": description[:3000],
                "source": "google_careers",
                "posted_date": "",
            })

        time.sleep(0.5)

    logger.info("Google Careers: %d relevant jobs", len(jobs))
    return jobs


# ── Meta ──────────────────────────────────────────────────────────────────────

def _fetch_meta(search_terms: list[str]) -> list[dict]:
    """
    Meta Careers GraphQL API.
    Endpoint: https://www.metacareers.com/graphql
    """
    jobs = []
    seen: set[str] = set()

    graphql_url = "https://www.metacareers.com/graphql"
    # Meta's public GraphQL query for job search
    query = """
    query JobsBoardSearchJobPostingsQuery(
        $search_input: JobPostingsSearchInput!
    ) {
        job_postings: job_postings_search(search_input: $search_input) {
            count
            edges {
                node {
                    id
                    title
                    sub_teams { name }
                    locations { name }
                    url: job_url
                }
            }
        }
    }
    """

    for term in search_terms:
        payload = {
            "query": query,
            "variables": {
                "search_input": {
                    "q": term,
                    "divisions": [],
                    "offices": [],
                    "roles": [],
                    "leadership_levels": [],
                    "results_per_page": 20,
                    "is_leadership": False,
                    "remote": False,
                }
            },
        }
        try:
            resp = requests.post(graphql_url, json=payload, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code in (403, 429):
                logger.warning("Meta Careers: blocked (%d) — skipping '%s'", resp.status_code, term)
                continue
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.warning("Meta Careers fetch failed for '%s': %s", term, e)
            continue

        edges = (
            data.get("data", {})
                .get("job_postings", {})
                .get("edges", [])
        )
        for edge in edges:
            node = edge.get("node", {})
            title = node.get("title", "").strip()
            job_url = node.get("url") or node.get("id", "")
            locations = [loc.get("name", "") for loc in node.get("locations", [])]
            location = ", ".join(filter(None, locations))

            if not title or not job_url or job_url in seen:
                continue
            if not _is_relevant(title):
                continue

            seen.add(job_url)
            jobs.append({
                "title": title,
                "company": "Meta",
                "url": job_url if job_url.startswith("http") else f"https://www.metacareers.com{job_url}",
                "location": location,
                "jd_text": "",
                "source": "meta_careers",
                "posted_date": "",
            })

        time.sleep(0.5)

    logger.info("Meta Careers: %d relevant jobs", len(jobs))
    return jobs


# ── Microsoft ─────────────────────────────────────────────────────────────────

def _fetch_microsoft(search_terms: list[str]) -> list[dict]:
    """
    Microsoft Careers public search API.
    Endpoint: https://gcsapi.microsoft.com/api/jobs/search
    """
    jobs = []
    seen: set[str] = set()

    for term in search_terms:
        url = "https://gcsapi.microsoft.com/api/jobs/search"
        params = {
            "keyword": term,
            "location": "United States",
            "pg": 1,
            "pgSz": 20,
            "o": "Relevance",
            "flt": True,
        }
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code in (403, 429):
                logger.warning("Microsoft Careers: blocked (%d) — skipping '%s'", resp.status_code, term)
                continue
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.warning("Microsoft Careers fetch failed for '%s': %s", term, e)
            continue

        result_jobs = (
            data.get("operationResult", {})
                .get("result", {})
                .get("jobs", [])
        )
        for job in result_jobs:
            title = job.get("title", "").strip()
            job_id = job.get("jobId", "")
            location = job.get("primaryWorkLocation", "")
            description = job.get("descriptionTeaser", "")

            job_url = f"https://careers.microsoft.com/global/en/job/{job_id}" if job_id else ""

            if not title or not job_url or job_url in seen:
                continue
            if not _is_relevant(title, description):
                continue

            seen.add(job_url)
            jobs.append({
                "title": title,
                "company": "Microsoft",
                "url": job_url,
                "location": location,
                "jd_text": description[:3000],
                "source": "microsoft_careers",
                "posted_date": job.get("postingDate", ""),
            })

        time.sleep(0.5)

    logger.info("Microsoft Careers: %d relevant jobs", len(jobs))
    return jobs


# ── Amazon ────────────────────────────────────────────────────────────────────

def _fetch_amazon(search_terms: list[str]) -> list[dict]:
    """
    Amazon Jobs public search JSON API.
    Endpoint: https://www.amazon.jobs/en/search.json
    """
    jobs = []
    seen: set[str] = set()

    for term in search_terms:
        url = "https://www.amazon.jobs/en/search.json"
        params = {
            "query": term,
            "normalized_country_code[]": "US",
            "result_limit": 20,
            "offset": 0,
        }
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code in (403, 429):
                logger.warning("Amazon Jobs: blocked (%d) — skipping '%s'", resp.status_code, term)
                continue
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.warning("Amazon Jobs fetch failed for '%s': %s", term, e)
            continue

        for job in data.get("jobs", []):
            title = job.get("title", "").strip()
            job_path = job.get("job_path", "")
            location = job.get("location", "")
            description = job.get("description", "")

            job_url = f"https://www.amazon.jobs{job_path}" if job_path else ""

            if not title or not job_url or job_url in seen:
                continue
            if not _is_relevant(title, description):
                continue

            seen.add(job_url)
            jobs.append({
                "title": title,
                "company": "Amazon",
                "url": job_url,
                "location": location,
                "jd_text": description[:3000],
                "source": "amazon_jobs",
                "posted_date": job.get("updated_time", ""),
            })

        time.sleep(0.5)

    logger.info("Amazon Jobs: %d relevant jobs", len(jobs))
    return jobs


# ── Dispatcher ────────────────────────────────────────────────────────────────

_FETCHERS = {
    "google":    _fetch_google,
    "meta":      _fetch_meta,
    "microsoft": _fetch_microsoft,
    "amazon":    _fetch_amazon,
}

_SEARCH_TERMS = [
    "data scientist",
    "machine learning engineer",
]


def fetch_custom_career_jobs(companies: Optional[list] = None) -> list[dict]:
    """
    Fetch jobs from all configured custom career pages.

    Args:
        companies: List of company keys to poll (e.g. ["google", "meta"]).
                   Defaults to config.CUSTOM_CAREER_COMPANIES.

    Returns:
        Combined list of job dicts from all companies.
    """
    if companies is None:
        companies = CUSTOM_CAREER_COMPANIES

    all_jobs: list[dict] = []

    for company_key in companies:
        fetcher = _FETCHERS.get(company_key.lower())
        if not fetcher:
            logger.warning("custom_careers: no fetcher for '%s' — skipping", company_key)
            continue

        logger.info("custom_careers: polling %s", company_key)
        try:
            jobs = fetcher(_SEARCH_TERMS)
            all_jobs.extend(jobs)
        except Exception as e:
            logger.error("custom_careers: %s failed: %s", company_key, e)

    logger.info("custom_careers total: %d jobs", len(all_jobs))
    return all_jobs
