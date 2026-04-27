"""
Recruiter finder using Hunter.io API + Claude cold email generation.

Looks up the hiring manager / recruiter email and LinkedIn URL for a given
company and role, then generates a personalised cold email draft.

Hunter.io free tier: 25 domain searches/month — sufficient for personal use.
API docs: https://hunter.io/api-documentation/v2
"""

import os
import re
import logging
from typing import Optional
from urllib.parse import urlparse

import requests
import anthropic

from config import COLD_EMAIL_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

HUNTER_API_BASE = "https://api.hunter.io/v2"
REQUEST_TIMEOUT = 15

# Domains that Hunter.io will return junk results for — skip lookup entirely
_SKIP_DOMAINS = {
    "jobs.com", "lever.co", "greenhouse.io", "ashbyhq.com", "ashby.com",
    "workday.com", "myworkdayjobs.com", "taleo.net", "icims.com",
    "indeed.com", "linkedin.com", "glassdoor.com", "ziprecruiter.com",
    "monster.com", "careerbuilder.com", "simplyhired.com",
    "smartrecruiters.com", "jobvite.com", "bamboohr.com",
    "recruiting.ultipro.com", "hire.trakstar.com",
}


# ── Domain extraction ─────────────────────────────────────────────────────────

def _extract_domain(job_url: str, company_name: str) -> str:
    """
    Derive the company's primary domain from the job URL or company name.

    Priority:
    1. Extract from job URL (for direct company career sites)
    2. Fall back to a sanitised company name guess
    """
    parsed = urlparse(job_url)
    hostname = parsed.netloc.lower()

    # ATS platforms — the hostname tells us nothing about the company
    ats_domains = {
        "boards.greenhouse.io", "jobs.lever.co", "jobs.ashby.com",
        "app.ashbyhq.com", "www.indeed.com", "www.linkedin.com",
        "www.glassdoor.com",
    }

    # Path segments that are NOT company slugs (e.g. LinkedIn /jobs/view/12345)
    _generic_slugs = {
        "jobs", "job", "view", "careers", "career", "apply",
        "position", "posting", "search", "collections",
    }

    for ats in ats_domains:
        if ats in hostname:
            # For Lever/Ashby/Greenhouse the first path segment IS the company slug
            # e.g. jobs.lever.co/stripe/abc → stripe.com
            # For LinkedIn/Indeed the first segment is a generic word — skip it
            path_parts = parsed.path.strip("/").split("/")
            if path_parts and path_parts[0]:
                slug = path_parts[0].lower()
                if slug not in _generic_slugs:
                    return f"{slug}.com"
            break  # fall through to company-name guess

    # Use the actual hostname if it looks like a company career site
    # e.g., careers.stripe.com → stripe.com
    if hostname and hostname not in ats_domains:
        for prefix in ("careers.", "jobs.", "work.", "apply."):
            if hostname.startswith(prefix):
                hostname = hostname[len(prefix):]
                break
        return hostname

    # Fallback: sanitise company name to guess domain
    clean = re.sub(r"[^\w]", "", company_name.lower())
    return f"{clean}.com"


# ── Hunter.io API ─────────────────────────────────────────────────────────────

def _hunter_domain_search(domain: str, api_key: str, company_name: str = "") -> Optional[dict]:
    """
    Search Hunter.io for recruiter/talent emails at a domain.

    Returns the best matching contact dict or None.
    """
    url = f"{HUNTER_API_BASE}/domain-search"
    params = {
        "domain": domain,
        "limit": 5,
        "api_key": api_key,
    }

    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 401:
            logger.error("Hunter.io: invalid API key")
            return None
        if resp.status_code == 429:
            logger.warning("Hunter.io: rate limit hit")
            return None
        if resp.status_code == 400:
            logger.error("Hunter.io: bad request — %s", resp.text[:200])
            return None
        resp.raise_for_status()

        data = resp.json().get("data", {})
        emails = data.get("emails", [])

        if not emails:
            logger.info("Hunter.io: no results for domain %s", domain)
            return None

        # Prefer entries whose position matches recruiter/talent/hiring/hr
        recruiter_kws = ["recruit", "talent", "hiring", "hr"]
        for entry in emails:
            position = (entry.get("position") or "").lower()
            if any(kw in position for kw in recruiter_kws):
                return _extract_hunter_contact(entry, domain, company_name)

        # Fall back to highest confidence score
        best = max(emails, key=lambda e: e.get("confidence", 0))
        return _extract_hunter_contact(best, domain, company_name)

    except requests.RequestException as e:
        logger.error("Hunter.io search failed: %s", e)
        return None


def _extract_hunter_contact(entry: dict, domain: str, company_name: str = "") -> dict:
    """Extract relevant contact fields from a Hunter.io email entry."""
    first = entry.get("first_name", "") or ""
    last = entry.get("last_name", "") or ""
    return {
        "name": f"{first} {last}".strip(),
        "title": entry.get("position", ""),
        "email": entry.get("value", ""),
        "linkedin_url": entry.get("linkedin", "") or "",
        "company": company_name or domain,
    }


def find_recruiter(
    company: str,
    job_title: str,
    job_url: str = "",
    api_key: Optional[str] = None,
) -> Optional[dict]:
    """
    Find a recruiter/hiring manager for the given company.

    Args:
        company:   Company display name.
        job_title: Job title (used for logging context only).
        job_url:   Job URL (used to infer company domain).
        api_key:   Hunter.io API key. Falls back to HUNTER_API_KEY env var.

    Returns:
        Dict with name, title, email, linkedin_url — or None if not found.
    """
    api_key = api_key or os.getenv("HUNTER_API_KEY", "")

    if not api_key:
        logger.warning("Hunter.io API key not configured — skipping recruiter lookup")
        return None

    domain = _extract_domain(job_url, company)

    # Skip generic/ATS domains — Hunter.io returns the same junk contact for these
    if domain in _SKIP_DOMAINS or any(domain.endswith("." + d) for d in _SKIP_DOMAINS):
        logger.info("Skipping Hunter.io for generic domain '%s'", domain)
        return None

    logger.info("Looking up recruiter for %s (domain: %s)", company, domain)

    contact = _hunter_domain_search(domain, api_key, company_name=company)

    if contact:
        logger.info("Found recruiter: %s (%s)", contact.get("name"), contact.get("email"))
    else:
        logger.info("No recruiter found for %s — sending fallback alert", company)

    return contact


# ── Cold email generation ─────────────────────────────────────────────────────

def draft_cold_email(
    recruiter: dict,
    job_dict: dict,
    client: Optional[anthropic.Anthropic] = None,
) -> str:
    """
    Generate a personalised 3-sentence cold email using Claude.

    Args:
        recruiter: Dict with recruiter name, title, company.
        job_dict:  Job metadata dict.
        client:    Optional Anthropic client.

    Returns:
        Cold email body text (plain text, no subject line).
    """
    if client is None:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    applicant_name = os.getenv("APPLICANT_NAME", "Aadarsh")

    prompt = (
        f"Write a cold email from {applicant_name} to {recruiter.get('name', 'the recruiter')} "
        f"at {job_dict.get('company', 'the company')} "
        f"about the {job_dict.get('title', 'open')} role.\n\n"
        f"Recruiter title: {recruiter.get('title', 'Recruiter')}\n"
        f"Applicant background: Data scientist / ML engineer with 3+ years of experience, "
        f"specialising in production ML systems, RAG pipelines, and LLMs.\n\n"
        f"Rules: 3 sentences max, no subject line, sign off with {applicant_name}."
    )

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=COLD_EMAIL_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception as e:
        logger.error("Cold email generation failed: %s", e)
        first_name = recruiter.get("name", "").split()[0] if recruiter.get("name") else "there"
        return (
            f"Hi {first_name} — I saw the {job_dict.get('title')} role at "
            f"{job_dict.get('company')} and wanted to connect directly. "
            f"I'm a data scientist with 3+ years building production ML systems. "
            f"Would love to chat. Best, {applicant_name}"
        )
