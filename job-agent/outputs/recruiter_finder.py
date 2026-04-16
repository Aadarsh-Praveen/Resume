"""
Recruiter finder using Apollo.io API + Claude cold email generation.

Looks up the hiring manager / recruiter email and LinkedIn URL for a given
company and role, then generates a personalised cold email draft.

Apollo.io free tier: ~250 lookups/day — sufficient for personal use.
API docs: https://apolloio.github.io/apollo-api-docs/
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

APOLLO_API_BASE = "https://api.apollo.io/v1"
REQUEST_TIMEOUT = 15


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

    # Skip ATS domains — these don't tell us the company domain
    ats_domains = {
        "boards.greenhouse.io", "jobs.lever.co", "jobs.ashby.com",
        "app.ashbyhq.com", "www.indeed.com", "www.linkedin.com",
        "www.glassdoor.com",
    }
    for ats in ats_domains:
        if ats in hostname:
            # Try to extract company from ATS subdomain or path
            # e.g., jobs.lever.co/stripe → stripe.com
            path_parts = parsed.path.strip("/").split("/")
            if path_parts and path_parts[0]:
                slug = path_parts[0].lower()
                return f"{slug}.com"
            break

    # Use the actual hostname if it looks like a company career site
    # e.g., careers.stripe.com → stripe.com
    if hostname and hostname not in ats_domains:
        # Remove common career subdomain prefixes
        for prefix in ("careers.", "jobs.", "work.", "apply."):
            if hostname.startswith(prefix):
                hostname = hostname[len(prefix):]
                break
        return hostname

    # Fallback: sanitise company name to guess domain
    clean = re.sub(r"[^\w]", "", company_name.lower())
    return f"{clean}.com"


# ── Apollo.io API ─────────────────────────────────────────────────────────────

def _apollo_people_search(domain: str, role_keywords: list[str], api_key: str) -> Optional[dict]:
    """
    Search Apollo.io for people with recruiting/hiring titles at a domain.

    Returns the first matching contact dict or None.
    """
    url = f"{APOLLO_API_BASE}/mixed_people/search"

    # Apollo requires the API key in the X-Api-Key header (not in the body).
    # Passing it in the body returns 422: "API key must be passed in X-Api-Key header".
    # q_organization_domains must be a plain string, not a list.
    headers = {
        "X-Api-Key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "q_organization_domains": domain,   # string, e.g. "stripe.com"
        "person_titles": [
            "Recruiter",
            "Technical Recruiter",
            "Senior Recruiter",
            "Talent Acquisition",
            "Hiring Manager",
            "Talent Partner",
            "HR Manager",
        ],
        "per_page": 5,
        "page": 1,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 401:
            logger.error("Apollo.io: invalid API key")
            return None
        if resp.status_code == 422:
            logger.error(
                "Apollo.io: 422 Unprocessable Entity — bad request payload: %s",
                resp.text[:300],
            )
            return None
        if resp.status_code == 429:
            logger.warning("Apollo.io: rate limit hit")
            return None
        resp.raise_for_status()

        data = resp.json()
        people = data.get("people", [])

        if not people:
            logger.info("Apollo.io: no results for domain %s", domain)
            return None

        # Prefer people whose title includes "talent", "recruit", or "hiring"
        for person in people:
            title = (person.get("title") or "").lower()
            if any(kw in title for kw in ["recruit", "talent", "hiring", "hr"]):
                return _extract_contact(person)

        # Fall back to first result
        return _extract_contact(people[0])

    except requests.RequestException as e:
        logger.error("Apollo.io search failed: %s", e)
        return None


def _extract_contact(person: dict) -> dict:
    """Extract relevant contact fields from an Apollo person dict."""
    email = person.get("email") or ""
    if not email:
        # Try email_status or revealed_for_current_team
        email = person.get("revealed_for_current_team", {}).get("email", "")

    return {
        "name": f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
        "title": person.get("title", ""),
        "email": email,
        "linkedin_url": person.get("linkedin_url", ""),
        "company": person.get("organization", {}).get("name", ""),
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
        job_title: Job title (used for context, not for Apollo query).
        job_url:   Job URL (used to infer company domain).
        api_key:   Apollo.io API key. Falls back to APOLLO_API_KEY env var.

    Returns:
        Dict with name, title, email, linkedin_url — or None if not found.
    """
    api_key = api_key or os.getenv("APOLLO_API_KEY", "")

    if not api_key:
        logger.warning("Apollo API key not configured — skipping recruiter lookup")
        return None

    domain = _extract_domain(job_url, company)
    logger.info("Looking up recruiter for %s (domain: %s)", company, domain)

    contact = _apollo_people_search(domain, [job_title], api_key)

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
