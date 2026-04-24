"""
Job Description text extractor.

Fetches the full HTML from a job posting URL and extracts clean plain text.
Handles common ATS URL patterns: Greenhouse, Lever, Ashby, BambooHR, Indeed.

Also provides `extract_min_years(jd_text)` which parses years-of-experience
requirements from sections like "Minimum Requirements" or "Qualifications".
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


# ── Years-of-experience extraction ───────────────────────────────────────────

# Section headers that indicate a requirements / qualifications block
_REQ_SECTION_RE = re.compile(
    r"(?:minimum\s+requirements?|required?\s+qualifications?|basic\s+qualifications?"
    r"|what\s+you(?:'ll)?\s+(?:need|bring|have)"
    r"|qualifications?|requirements?"
    r"|you\s+(?:must|should)\s+have"
    r"|experience\s+(?:required|needed|we\s+require))",
    re.IGNORECASE,
)

# All YOE patterns — each group (or first group for ranges) gives the *lower* bound
_YOE_PATTERNS = [
    re.compile(r"(\d+)\s*\+\s*years?",                           re.IGNORECASE),  # 5+ years
    re.compile(r"(\d+)\s*[-–—]\s*(\d+)\s*years?",               re.IGNORECASE),  # 2-5 years
    re.compile(r"at\s+least\s+(\d+)\s*years?",                   re.IGNORECASE),  # at least 3 years
    re.compile(r"minimum\s+(?:of\s+)?(\d+)\s*years?",            re.IGNORECASE),  # minimum 3 years
    re.compile(r"(\d+)\s+or\s+more\s+years?",                    re.IGNORECASE),  # 3 or more years
    re.compile(r"(\d+)\s*years?\s+(?:of\s+)?(?:relevant\s+)?experience", re.IGNORECASE),  # 3 years experience
]

# Section headers that signal the *end* of a requirements block
_NEXT_SECTION_RE = re.compile(
    r"^(?:responsibilities|what\s+you(?:'ll)?\s+do|about\s+(?:us|the\s+role|you)"
    r"|benefits?|perks?|compensation|salary|about\s+this\s+role)",
    re.IGNORECASE,
)


def _years_from_text(text: str) -> list[int]:
    """Return all YOE lower-bounds found in *text* (duplicates allowed)."""
    found: list[int] = []
    for pat in _YOE_PATTERNS:
        for m in pat.finditer(text):
            groups = [int(g) for g in m.groups() if g is not None]
            if groups:
                found.append(min(groups))   # ranges like "2-5 yrs" → 2
    return found


def extract_min_years(jd_text: str) -> Optional[int]:
    """
    Parse the minimum years-of-experience requirement from a JD.

    Searches inside recognised requirement sections first
    (Minimum Requirements, Qualifications, etc.), then falls back to
    scanning the whole text.

    Returns:
        Minimum years required as int, or None if no pattern is found.

    Examples:
        "3+ years"    → 3
        "2-5 years"   → 2   (lower bound of the range)
        "5+ years"    → 5
        no pattern    → None
    """
    if not jd_text:
        return None

    lines = jd_text.splitlines()
    n = lines.__len__()

    # Collect text windows that follow a requirements-style section header.
    req_windows: list[str] = []
    i = 0
    while i < n:
        stripped = lines[i].strip()
        # A section header: matches the regex and is a short line (title, not a bullet)
        if _REQ_SECTION_RE.search(stripped) and len(stripped) < 80:
            # Gather lines until the next major section or 25 lines, whichever first
            window_lines = [stripped]
            j = i + 1
            while j < n and j < i + 25:
                next_line = lines[j].strip()
                if _NEXT_SECTION_RE.match(next_line) and len(next_line) < 60:
                    break
                window_lines.append(next_line)
                j += 1
            req_windows.append("\n".join(window_lines))
        i += 1

    # Search requirement sections first.
    # Use max() — if ANY requirement exceeds the threshold the job is out of range.
    # e.g. "10+ years ML, 5+ years management" → max=10, correctly flags the job.
    if req_windows:
        req_years: list[int] = []
        for window in req_windows:
            req_years.extend(_years_from_text(window))
        if req_years:
            return max(req_years)

    # Fallback: scan whole JD (less precise but better than nothing)
    all_years = _years_from_text(jd_text)
    return max(all_years) if all_years else None


def extract_jd_text(url: str) -> str:
    """
    Fetch a job posting URL and return the cleaned JD text.

    Raises:
        requests.RequestException: if the URL cannot be fetched after retries.
        ValueError: if the extracted text is suspiciously short (< 100 chars),
                    or if the job is no longer accepting applications.
    """
    source = _detect_source(url)
    logger.info("Extracting JD from %s (detected: %s)", url, source)

    html = _fetch_html(url)

    # Detect closed/expired postings before parsing (works for LinkedIn and others)
    if "no longer accepting applications" in html.lower():
        raise ValueError("CLOSED: job is no longer accepting applications")

    selector = _SELECTORS.get(source)
    text = _clean_text(html, selector)

    if len(text) < 100:
        # Fallback: try without a selector
        text = _clean_text(html, None)

    if len(text) < 100:
        raise ValueError(f"JD text too short ({len(text)} chars) for URL: {url}")

    logger.info("Extracted %d chars of JD text from %s", len(text), url)
    return text
