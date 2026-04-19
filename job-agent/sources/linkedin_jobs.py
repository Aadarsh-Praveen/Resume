"""
LinkedIn job search via the public guest API.

LinkedIn renders job listings server-side for unauthenticated visitors at:
    https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search

This endpoint returns raw HTML job cards — no login, no API key required.
It is the same data shown to logged-out users on linkedin.com/jobs.

Improvements over single-page fetch:
  - Session warmup: hits linkedin.com/jobs first to establish guest cookies
  - Pagination: fetches up to LINKEDIN_MAX_PAGES pages per query (25 jobs each)
  - Retry with exponential backoff on 429 before giving up
  - Stop-early: stops paging a query when a page returns 0 cards
"""

import logging
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

from config import (
    ROLE_KEYWORDS, EXCLUDE_KEYWORDS, LINKEDIN_QUERIES,
    LINKEDIN_MAX_PAGES, LINKEDIN_PAGE_DELAY, LINKEDIN_QUERY_DELAY,
)

logger = logging.getLogger(__name__)

_GUEST_API   = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_WARMUP_URL  = "https://www.linkedin.com/jobs/search/"
_TIMEOUT     = 20
_PAGE_SIZE   = 25

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.6367.119 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.linkedin.com/",
}


def _warmup_session() -> requests.Session:
    """Hit the LinkedIn jobs page to establish guest cookies before scraping."""
    session = requests.Session()
    try:
        session.get(_WARMUP_URL, headers=_HEADERS, timeout=_TIMEOUT)
    except Exception as e:
        logger.debug("LinkedIn session warmup failed (non-fatal): %s", e)
    return session


def _is_relevant(title: str) -> bool:
    t = title.lower()
    if not any(kw in t for kw in ROLE_KEYWORDS):
        return False
    if any(kw in t for kw in EXCLUDE_KEYWORDS):
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
            title_el   = card.find(class_="base-search-card__title")
            company_el = card.find(class_="base-search-card__subtitle")
            loc_el     = card.find(class_="job-search-card__location")
            link_el    = card.find("a", class_="base-card__full-link") or \
                         card.find("a", href=lambda h: h and "linkedin.com/jobs/view" in h)
            time_el    = card.find("time")

            title   = title_el.get_text(strip=True)   if title_el   else ""
            company = company_el.get_text(strip=True)  if company_el else ""
            location = loc_el.get_text(strip=True)    if loc_el     else ""
            job_url  = link_el["href"].split("?")[0]  if link_el    else ""
            posted   = time_el.get("datetime", "")    if time_el    else ""

            if not title or not job_url:
                continue
            if not _is_relevant(title):
                continue

            jobs.append({
                "title":       title,
                "company":     company or "Unknown",
                "url":         job_url,
                "location":    location,
                "jd_text":     "",
                "source":      "linkedin",
                "posted_date": posted,
            })
        except Exception as e:
            logger.debug("Failed to parse LinkedIn card: %s", e)

    return jobs


def _fetch_page(
    session: requests.Session,
    keywords: str,
    location: str,
    start: int,
) -> list[dict]:
    """
    Fetch one page of results. Returns [] on unrecoverable error.
    Retries up to 3 times with exponential backoff on HTTP 429.
    """
    params = {
        "keywords": keywords,
        "location": location,
        "start":    start,
        "count":    _PAGE_SIZE,
        "f_TPR":    "r86400",   # past 24 hours
    }

    for attempt in range(3):
        try:
            resp = session.get(_GUEST_API, params=params, headers=_HEADERS, timeout=_TIMEOUT)

            if resp.status_code == 429:
                wait = 10 * (2 ** attempt)   # 10s, 20s, 40s
                logger.warning(
                    "LinkedIn 429 for '%s' start=%d — waiting %ds (attempt %d/3)",
                    keywords, start, wait, attempt + 1,
                )
                time.sleep(wait)
                continue

            if resp.status_code == 403:
                logger.warning("LinkedIn 403 for '%s' start=%d — skipping page", keywords, start)
                return []

            resp.raise_for_status()
            return _parse_job_cards(resp.text)

        except requests.RequestException as e:
            logger.warning("LinkedIn fetch error for '%s' start=%d: %s", keywords, start, e)
            if attempt < 2:
                time.sleep(5)
            else:
                return []

    return []


def fetch_linkedin_jobs(
    queries: Optional[list] = None,
    max_pages: int = LINKEDIN_MAX_PAGES,
) -> list[dict]:
    """
    Search LinkedIn for jobs using the public guest API.

    Fetches up to `max_pages` pages per query (25 jobs/page), stops early
    if a page returns 0 cards (no more results for that query).

    Args:
        queries:   List of {keywords, location} dicts. Defaults to LINKEDIN_QUERIES.
        max_pages: Max pages to fetch per query. Defaults to LINKEDIN_MAX_PAGES.

    Returns:
        Deduplicated list of job dicts filtered by ROLE_KEYWORDS / EXCLUDE_KEYWORDS.
    """
    if queries is None:
        queries = LINKEDIN_QUERIES

    session   = _warmup_session()
    seen_urls: set[str] = set()
    all_jobs:  list[dict] = []

    for q in queries:
        keywords = q.get("keywords", "data scientist")
        location = q.get("location", "United States")
        query_new = 0

        logger.info("LinkedIn: '%s' in '%s'", keywords, location)

        for page in range(max_pages):
            start = page * _PAGE_SIZE
            cards = _fetch_page(session, keywords, location, start)

            if not cards:
                break   # no more results or blocked — stop paging this query

            for job in cards:
                if job["url"] not in seen_urls:
                    seen_urls.add(job["url"])
                    all_jobs.append(job)
                    query_new += 1

            time.sleep(LINKEDIN_PAGE_DELAY)

        logger.info("  → %d new jobs (pages fetched: %d)", query_new, page + 1)
        time.sleep(LINKEDIN_QUERY_DELAY)

    logger.info("LinkedIn total: %d unique relevant jobs across %d queries", len(all_jobs), len(queries))
    return all_jobs
