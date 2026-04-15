"""
LinkedIn job search via the public guest API.

LinkedIn renders job listings server-side for unauthenticated visitors at:
    https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search

This endpoint returns raw HTML job cards — no login, no API key required.
It is the same data shown to logged-out users on linkedin.com/jobs.

Rate limits: 1 s delay between queries, max 25 results per request.
"""

import logging
import time
from typing import Optional
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from config import ROLE_KEYWORDS, EXCLUDE_KEYWORDS, LINKEDIN_QUERIES

logger = logging.getLogger(__name__)

BASE_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
REQUEST_TIMEOUT = 20
RESULTS_PER_QUERY = 25

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _build_url(keywords: str, location: str, start: int = 0) -> str:
    params = {
        "keywords": keywords,
        "location": location,
        "start": start,
        "count": RESULTS_PER_QUERY,
        "f_TPR": "r86400",   # past 24 hours
    }
    return f"{BASE_URL}?{urlencode(params)}"


def _is_relevant(title: str, description: str = "") -> bool:
    combined = (title + " " + description).lower()
    if not any(kw in combined for kw in ROLE_KEYWORDS):
        return False
    if any(kw in combined for kw in EXCLUDE_KEYWORDS):
        return False
    return True


def _parse_job_cards(html: str) -> list[dict]:
    """
    Parse LinkedIn job-card HTML and return a list of raw job dicts.

    LinkedIn guest search returns a list of <li> elements, each containing:
      - .base-search-card__title          → job title
      - .base-search-card__subtitle a     → company name
      - .job-search-card__location        → location
      - a.base-card__full-link            → job URL
      - time.job-search-card__listdate    → posted date (datetime attr)
    """
    soup = BeautifulSoup(html, "lxml")
    cards = soup.find_all("li")
    jobs = []

    for card in cards:
        try:
            # Title
            title_el = card.find(class_="base-search-card__title")
            title = title_el.get_text(strip=True) if title_el else ""

            # Company
            company_el = card.find(class_="base-search-card__subtitle")
            company = company_el.get_text(strip=True) if company_el else ""

            # Location
            loc_el = card.find(class_="job-search-card__location")
            location = loc_el.get_text(strip=True) if loc_el else ""

            # URL — prefer the full-link anchor
            link_el = card.find("a", class_="base-card__full-link")
            if not link_el:
                link_el = card.find("a", href=lambda h: h and "linkedin.com/jobs/view" in h)
            job_url = link_el["href"].split("?")[0] if link_el else ""

            # Posted date
            time_el = card.find("time")
            posted = time_el.get("datetime", "") if time_el else ""

            if not title or not job_url:
                continue

            if not _is_relevant(title):
                continue

            jobs.append({
                "title": title,
                "company": company or "Unknown",
                "url": job_url,
                "location": location,
                "jd_text": "",          # full JD fetched later by jd_extractor
                "source": "linkedin",
                "posted_date": posted,
            })

        except Exception as e:
            logger.debug("Failed to parse LinkedIn card: %s", e)
            continue

    return jobs


def _fetch_query(keywords: str, location: str) -> list[dict]:
    """Fetch one page of LinkedIn search results for a single query."""
    url = _build_url(keywords, location)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 429:
            logger.warning("LinkedIn: rate limited (429) for query '%s' — skipping", keywords)
            return []
        if resp.status_code == 403:
            logger.warning("LinkedIn: blocked (403) for query '%s' — skipping", keywords)
            return []
        resp.raise_for_status()
        jobs = _parse_job_cards(resp.text)
        logger.info("LinkedIn guest API: %d relevant jobs for '%s'", len(jobs), keywords)
        return jobs
    except requests.RequestException as e:
        logger.warning("LinkedIn fetch failed for '%s': %s — skipping", keywords, e)
        return []


def fetch_linkedin_jobs(queries: Optional[list] = None) -> list[dict]:
    """
    Search LinkedIn for jobs using the public guest API.

    Args:
        queries: List of dicts with 'keywords' and 'location'.
                 Defaults to config.LINKEDIN_QUERIES.

    Returns:
        Deduplicated list of job dicts.
    """
    if queries is None:
        queries = LINKEDIN_QUERIES

    seen_urls: set[str] = set()
    all_jobs: list[dict] = []

    for q in queries:
        keywords = q.get("keywords", "data scientist")
        location = q.get("location", "United States")

        logger.info("LinkedIn: searching '%s' in '%s'", keywords, location)
        jobs = _fetch_query(keywords, location)

        for job in jobs:
            if job["url"] not in seen_urls:
                seen_urls.add(job["url"])
                all_jobs.append(job)

        time.sleep(1)   # polite delay between queries

    logger.info("LinkedIn total: %d unique jobs", len(all_jobs))
    return all_jobs
