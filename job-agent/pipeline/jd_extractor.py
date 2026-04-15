"""
Job Description text extractor.

Fetches the full HTML from a job posting URL and extracts clean plain text.
Handles common ATS URL patterns: Greenhouse, Lever, Ashby, BambooHR, Indeed.
"""

import re
import logging
import time
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

REQUEST_TIMEOUT = 15  # seconds
MAX_RETRIES = 3
RETRY_BACKOFF = 2     # seconds


# ── URL → extraction strategy mapping ────────────────────────────────────────

def _detect_source(url: str) -> str:
    """Identify the ATS / job board from the URL."""
    host = urlparse(url).netloc.lower()
    if "greenhouse.io" in host or "boards.greenhouse.io" in host:
        return "greenhouse"
    if "lever.co" in host:
        return "lever"
    if "ashby.com" in host or "jobs.ashby.com" in host:
        return "ashby"
    if "bamboohr.com" in host:
        return "bamboohr"
    if "indeed.com" in host:
        return "indeed"
    if "linkedin.com" in host:
        return "linkedin"
    if "workday.com" in host or "myworkdayjobs.com" in host:
        return "workday"
    return "generic"


def _fetch_html(url: str) -> str:
    """Fetch raw HTML from URL with retry logic."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF ** attempt
                logger.warning("Fetch attempt %d failed for %s: %s — retrying in %ds",
                               attempt + 1, url, e, wait)
                time.sleep(wait)
            else:
                logger.error("All fetch attempts failed for %s: %s", url, e)
                raise


def _clean_text(html: str, container_selector: Optional[str] = None) -> str:
    """
    Strip HTML tags and return clean plain text.

    Args:
        html:               Raw HTML string.
        container_selector: CSS selector for the JD container element.
                            If None, uses <body>.
    """
    soup = BeautifulSoup(html, "lxml")

    # Remove boilerplate elements
    for tag in soup(["script", "style", "nav", "header", "footer",
                     "aside", "noscript", "meta", "link"]):
        tag.decompose()

    if container_selector:
        container = soup.select_one(container_selector)
        if container:
            text = container.get_text(separator="\n")
        else:
            text = soup.get_text(separator="\n")
    else:
        text = soup.get_text(separator="\n")

    # Normalise whitespace
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    text = "\n".join(lines)

    # Collapse runs of 3+ blank lines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ── Source-specific selectors ─────────────────────────────────────────────────

_SELECTORS = {
    "greenhouse":  "#content",
    "lever":       ".content",
    "ashby":       "main",
    "bamboohr":    "#BambooHR",
    "indeed":      "#jobDescriptionText",
    "linkedin":    ".description__text",
    "generic":     "main",
}


def extract_jd_text(url: str) -> str:
    """
    Fetch a job posting URL and return the cleaned JD text.

    Raises:
        requests.RequestException: if the URL cannot be fetched after retries.
        ValueError: if the extracted text is suspiciously short (< 100 chars).
    """
    source = _detect_source(url)
    logger.info("Extracting JD from %s (detected: %s)", url, source)

    html = _fetch_html(url)
    selector = _SELECTORS.get(source)
    text = _clean_text(html, selector)

    if len(text) < 100:
        # Fallback: try without a selector
        text = _clean_text(html, None)

    if len(text) < 100:
        raise ValueError(f"JD text too short ({len(text)} chars) for URL: {url}")

    logger.info("Extracted %d chars of JD text from %s", len(text), url)
    return text
