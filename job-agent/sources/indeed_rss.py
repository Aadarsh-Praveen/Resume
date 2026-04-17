"""
Indeed RSS job feed parser.

Indeed provides native RSS feeds for any search query. No authentication needed.
Feed URL format: https://www.indeed.com/rss?q={query}&l={location}
"""

import logging
import re
import time
from html import unescape
from typing import Optional
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

import requests

from config import INDEED_QUERIES, INDEED_MAX_RESULTS, ROLE_KEYWORDS, EXCLUDE_KEYWORDS

logger = logging.getLogger(__name__)

INDEED_RSS_BASE = "https://www.indeed.com/rss"
HIMALAYAS_API = "https://himalayas.app/jobs/api"
REQUEST_TIMEOUT = 15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
}


def _build_feed_url(query: str, location: str) -> str:
    params = {"q": query, "l": location, "limit": str(INDEED_MAX_RESULTS), "sort": "date"}
    return f"{INDEED_RSS_BASE}?{urlencode(params)}"


def _strip_html(html_text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", " ", html_text or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_rss_xml(xml_text: str) -> list[dict]:
    """
    Parse RSS/Atom XML and return a list of entry dicts with
    keys: title, link, summary, author, published.
    """
    entries = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning("RSS XML parse error: %s", e)
        return entries

    # Handle both RSS 2.0 (<channel><item>) and Atom (<entry>)
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    # RSS 2.0
    for item in root.iter("item"):
        entry = {
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "summary": (item.findtext("description") or "").strip(),
            "author": (item.findtext("author") or "").strip(),
            "published": (item.findtext("pubDate") or "").strip(),
        }
        entries.append(entry)

    # Atom 1.0 fallback
    if not entries:
        for entry_el in root.findall("atom:entry", ns):
            link_el = entry_el.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            entry = {
                "title": (entry_el.findtext("atom:title", namespaces=ns) or "").strip(),
                "link": link,
                "summary": (entry_el.findtext("atom:summary", namespaces=ns) or "").strip(),
                "author": "",
                "published": (entry_el.findtext("atom:published", namespaces=ns) or "").strip(),
            }
            entries.append(entry)

    return entries


def _is_relevant(title: str, description: str) -> bool:
    """Check if a job matches role keywords and doesn't hit exclusion list."""
    combined = (title + " " + description).lower()
    if not any(kw in combined for kw in ROLE_KEYWORDS):
        return False
    if any(kw in combined for kw in EXCLUDE_KEYWORDS):
        return False
    return True


def _parse_entry(entry: dict) -> Optional[dict]:
    """Parse a raw RSS entry dict into a standardised job dict."""
    try:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        description = _strip_html(entry.get("summary", ""))
        published = entry.get("published", "")

        # Indeed often puts "Job Title - Company - Location" in the title
        # Try to extract company from title
        company = ""
        parts = title.split(" - ")
        if len(parts) >= 2:
            title = parts[0].strip()
            company = parts[1].strip()

        if not title or not link:
            return None

        if not _is_relevant(title, description):
            return None

        return {
            "title": title,
            "company": company or entry.get("author") or "Unknown",
            "url": link,
            "jd_text": description[:3000],
            "source": "indeed_rss",
            "posted_date": published,
        }
    except Exception as e:
        logger.warning("Failed to parse Indeed entry: %s", e)
        return None


def _fetch_himalayas() -> list[dict]:
    """
    Himalayas.app free job API — no key required.
    Returns remote DS/ML/AI jobs posted recently.
    """
    jobs = []
    seen: set[str] = set()
    try:
        resp = requests.get(
            HIMALAYAS_API,
            params={"limit": 100},
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("Himalayas API: HTTP %d — skipping", resp.status_code)
            return []
        data = resp.json()
        for job in data.get("jobs", []):
            title = (job.get("title") or "").strip()
            url = job.get("applicationLink") or job.get("url", "")
            company = (job.get("companyName") or job.get("company", {}).get("name", "")).strip()
            description = job.get("description", "") or ""
            location = job.get("locationRestrictions") or "Remote"
            posted = job.get("publishedAt", "")

            if not title or not url or url in seen:
                continue
            if not _is_relevant(title, description):
                continue

            seen.add(url)
            jobs.append({
                "title": title,
                "company": company or "Unknown",
                "url": url,
                "jd_text": _strip_html(description)[:3000],
                "source": "himalayas",
                "posted_date": posted,
                "location": str(location),
            })
    except Exception as e:
        logger.warning("Himalayas fetch failed: %s", e)
    logger.info("Himalayas: %d relevant jobs", len(jobs))
    return jobs


def fetch_indeed_jobs(queries: Optional[list] = None) -> list[dict]:
    """
    Fetch jobs from Indeed RSS feeds + Himalayas fallback.

    Uses a persistent session with cookies to reduce Indeed's 403 rate.
    Falls back to Himalayas free API for additional coverage when Indeed blocks.
    """
    if queries is None:
        queries = INDEED_QUERIES

    seen_urls: set[str] = set()
    jobs: list[dict] = []
    indeed_blocked_count = 0

    session = requests.Session()
    session.headers.update(HEADERS)
    # Warm up the session with a browser-like visit to set cookies
    try:
        session.get("https://www.indeed.com", timeout=REQUEST_TIMEOUT)
    except Exception:
        pass

    for query_params in queries:
        q = query_params.get("q", "data scientist")
        l = query_params.get("l", "United States")
        url = _build_feed_url(q, l)

        logger.info("Polling Indeed RSS: %s", url)
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 403:
                logger.warning(
                    "Indeed RSS blocked (403) for query '%s' — skipping", q
                )
                indeed_blocked_count += 1
                continue
            resp.raise_for_status()
            entries = _parse_rss_xml(resp.text)
            logger.info("Got %d entries from Indeed for query '%s'", len(entries), q)

            for entry in entries:
                job = _parse_entry(entry)
                if job and job["url"] not in seen_urls:
                    seen_urls.add(job["url"])
                    jobs.append(job)

        except requests.HTTPError as e:
            logger.warning("Indeed RSS HTTP error for query '%s': %s — skipping", q, e)
            indeed_blocked_count += 1
        except Exception as e:
            logger.warning("Indeed RSS fetch failed for query '%s': %s — skipping", q, e)

        time.sleep(1)

    logger.info("Indeed RSS: %d relevant jobs collected", len(jobs))

    # If Indeed is fully blocked, pull from Himalayas for broad remote coverage
    if indeed_blocked_count == len(queries):
        logger.info("Indeed fully blocked — trying Himalayas as fallback")
        himalayas_jobs = _fetch_himalayas()
        for job in himalayas_jobs:
            if job["url"] not in seen_urls:
                seen_urls.add(job["url"])
                jobs.append(job)

    return jobs
