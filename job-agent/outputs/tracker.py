"""
Notion application tracker.

Appends one page (row) per processed job to a Notion database.
Uses the Notion Integration API — no service account or OAuth needed.

Setup (one-time):
    1. Go to https://www.notion.so/profile/integrations → "New integration"
       Give it a name (e.g. "Job Agent"), set content capabilities to
       "Insert content". Copy the generated API key → NOTION_API_KEY in .env
    2. Create a Notion database (full-page or inline) with these properties:
         Name          → Title       (created automatically)
         Company       → Text
         JD URL        → URL
         Email         → Email
         Date          → Date
         Resume File   → Text
         ATS Score     → Number
         Status        → Select   (add options: ready, low_ats, high_ats, failed)
         Notes         → Text
    3. Open the database, click "..." → "Connect to" → select your integration
    4. Copy the database ID from the URL:
         notion.so/<workspace>/<DATABASE_ID>?v=...
       Set NOTION_DATABASE_ID in .env
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_NOTION_API_BASE = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _rich_text(value: str) -> list:
    """Build a Notion rich_text property value."""
    return [{"type": "text", "text": {"content": str(value)[:2000]}}]


def _build_page_properties(
    job_dict: dict,
    pdf_path: Optional[str],
    ats_score: Optional[float],
    status: str,
    notes: str,
) -> dict:
    """
    Convert job metadata into a Notion page properties dict matching the
    expected database schema.
    """
    applicant_email = os.getenv("APPLICANT_EMAIL", "")
    pdf_filename = os.path.basename(pdf_path) if pdf_path else ""
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    props: dict = {
        # Title field — Notion requires exactly one title property
        "Name": {
            "title": _rich_text(job_dict.get("title", "Untitled")),
        },
        "Company": {
            "rich_text": _rich_text(job_dict.get("company", "")),
        },
        "Resume File": {
            "rich_text": _rich_text(pdf_filename),
        },
        "Status": {
            "select": {"name": status},
        },
        "Date": {
            "date": {"start": today_iso},
        },
        "Notes": {
            "rich_text": _rich_text(notes),
        },
    }

    # URL property (Notion validates URL format — skip if empty)
    jd_url = job_dict.get("url", "")
    if jd_url and jd_url.startswith("http"):
        props["JD URL"] = {"url": jd_url}

    # Email property
    if applicant_email and "@" in applicant_email:
        props["Email"] = {"email": applicant_email}

    # ATS Score as a number
    if ats_score is not None:
        props["ATS Score"] = {"number": round(ats_score, 1)}

    return props


def log_application(
    job_dict: dict,
    pdf_path: Optional[str],
    ats_score: Optional[float],
    status: str,
    notes: str = "",
    database_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> bool:
    """
    Append a page to the Notion job tracker database.

    Args:
        job_dict:    Job metadata dict (title, company, url, …).
        pdf_path:    Path to the compiled PDF (basename stored).
        ats_score:   ATS keyword match score 0–100.
        status:      Status string: 'ready', 'low_ats', 'high_ats', 'failed'.
        notes:       Optional notes text.
        database_id: Notion database ID. Falls back to NOTION_DATABASE_ID env var.
        api_key:     Notion API key. Falls back to NOTION_API_KEY env var.

    Returns:
        True on success, False on failure.
    """
    api_key = api_key or os.getenv("NOTION_API_KEY", "")
    database_id = database_id or os.getenv("NOTION_DATABASE_ID", "")

    if not api_key or not database_id:
        logger.warning("Notion not configured — skipping tracker update")
        return False

    properties = _build_page_properties(job_dict, pdf_path, ats_score, status, notes)

    payload = {
        "parent": {"database_id": database_id},
        "properties": properties,
    }

    try:
        resp = requests.post(
            f"{_NOTION_API_BASE}/pages",
            headers=_headers(api_key),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()

        logger.info(
            "Logged to Notion: %s at %s (status: %s)",
            job_dict.get("title"), job_dict.get("company"), status,
        )
        return True

    except requests.HTTPError as e:
        body = {}
        try:
            body = e.response.json()
        except Exception:
            pass
        logger.error(
            "Notion API error %s: %s — %s",
            e.response.status_code,
            body.get("code", ""),
            body.get("message", str(e)),
        )
        return False
    except requests.RequestException as e:
        logger.error("Notion request failed: %s", e)
        return False
