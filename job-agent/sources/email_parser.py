"""
Gmail-based LinkedIn job alert parser.

Watches your Gmail inbox for emails from jobs-noreply@linkedin.com,
extracts job cards from the HTML email, and returns job dicts.

Setup (one-time):
    1. Enable Gmail API at console.cloud.google.com
    2. Create OAuth2 credentials (Desktop App) → download as credentials.json
    3. Set GMAIL_CREDENTIALS_PATH and GMAIL_TOKEN_PATH in .env
    4. Run this script once to authorise (browser opens for OAuth flow)
"""

import os
import base64
import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

LINKEDIN_SENDER = "jobs-noreply@linkedin.com"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _get_gmail_service(credentials_path: str, token_path: str):
    """
    Build an authenticated Gmail API service object.

    On first run, opens browser for OAuth consent and saves token to token_path.
    Subsequent runs use the saved token (auto-refreshes when expired).
    """
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        raise ImportError(
            "Google API packages not installed. Run: "
            "pip install google-api-python-client google-auth google-auth-oauthlib"
        )

    creds = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(
                    f"Gmail credentials not found at {credentials_path}. "
                    "Download OAuth2 credentials JSON from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _get_email_body(service, message_id: str) -> str:
    """Fetch and decode the HTML body of a Gmail message."""
    msg = service.users().messages().get(
        userId="me", id=message_id, format="full"
    ).execute()

    payload = msg.get("payload", {})

    def extract_html(part) -> Optional[str]:
        mime_type = part.get("mimeType", "")
        if mime_type == "text/html":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        for sub_part in part.get("parts", []):
            result = extract_html(sub_part)
            if result:
                return result
        return None

    return extract_html(payload) or ""


def _parse_linkedin_alert_html(html: str) -> list[dict]:
    """
    Parse a LinkedIn job alert email HTML and extract job cards.

    LinkedIn alert emails contain structured job cards with:
    - Job title (in <a> tag)
    - Company name (in a sibling element)
    - Location
    - Apply URL
    """
    soup = BeautifulSoup(html, "lxml")
    jobs = []

    # LinkedIn job cards are typically in <table> cells with job-specific class names
    # Strategy: find all links that look like LinkedIn job URLs
    job_links = soup.find_all("a", href=re.compile(r"linkedin\.com/jobs/view/\d+"))

    seen_urls = set()

    for link in job_links:
        job_url = link.get("href", "").split("?")[0]  # strip tracking params
        if not job_url or job_url in seen_urls:
            continue
        seen_urls.add(job_url)

        # Job title is usually the link text or nearest heading
        title = link.get_text(strip=True)
        if not title or len(title) < 3:
            # Try parent element text
            parent = link.find_parent(["td", "div", "li"])
            if parent:
                title = parent.get_text(separator=" ", strip=True)[:100]

        # Company and location — usually in sibling/parent elements
        company = ""
        location = ""
        parent_cell = link.find_parent(["td", "tr", "div"])
        if parent_cell:
            spans = parent_cell.find_all(["span", "p", "td"])
            text_parts = [s.get_text(strip=True) for s in spans if s.get_text(strip=True)]
            # Heuristic: 2nd non-title text is company, 3rd is location
            non_title = [t for t in text_parts if t != title and len(t) > 2]
            if non_title:
                company = non_title[0][:80]
            if len(non_title) > 1:
                location = non_title[1][:80]

        if not title or not job_url:
            continue

        jobs.append({
            "title": title,
            "company": company or "Unknown",
            "url": job_url,
            "jd_text": "",  # Full JD extracted later by jd_extractor
            "source": "linkedin_email",
            "posted_date": "",
            "location": location,
        })

    logger.info("Parsed %d job cards from LinkedIn alert email", len(jobs))
    return jobs


def watch_linkedin_alerts(
    credentials_path: Optional[str] = None,
    token_path: Optional[str] = None,
    max_messages: int = 20,
) -> list[dict]:
    """
    Check Gmail inbox for unread LinkedIn job alert emails and extract job cards.

    Args:
        credentials_path: Path to Gmail OAuth2 credentials JSON.
        token_path:       Path to store/read the OAuth2 token JSON.
        max_messages:     Maximum number of alert emails to process per call.

    Returns:
        List of job dicts extracted from all found alert emails.
    """
    credentials_path = credentials_path or os.getenv("GMAIL_CREDENTIALS_PATH", "gmail-credentials.json")
    token_path = token_path or os.getenv("GMAIL_TOKEN_PATH", "gmail-token.json")

    try:
        service = _get_gmail_service(credentials_path, token_path)
    except FileNotFoundError as e:
        logger.warning("Gmail not configured: %s", e)
        return []

    # Search for unread LinkedIn alert emails
    query = f"from:{LINKEDIN_SENDER} is:unread subject:\"job alert\""
    logger.info("Searching Gmail: %s", query)

    try:
        results = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=max_messages,
        ).execute()
    except Exception as e:
        logger.error("Gmail API search failed: %s", e)
        return []

    messages = results.get("messages", [])
    logger.info("Found %d LinkedIn alert emails", len(messages))

    all_jobs: list[dict] = []

    for msg_info in messages:
        msg_id = msg_info["id"]
        try:
            html = _get_email_body(service, msg_id)
            jobs = _parse_linkedin_alert_html(html)
            all_jobs.extend(jobs)

            # Mark as read
            service.users().messages().modify(
                userId="me",
                id=msg_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()

        except Exception as e:
            logger.error("Failed to process Gmail message %s: %s", msg_id, e)

    logger.info("LinkedIn email parser: %d jobs total from %d emails", len(all_jobs), len(messages))
    return all_jobs
