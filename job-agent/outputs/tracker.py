"""
Google Sheets application tracker.

Appends one row per processed job to a Google Sheet.
Uses a service account for authentication (no user OAuth flow needed).

Setup:
    1. Create a service account in Google Cloud Console → IAM → Service Accounts
    2. Enable Google Sheets API for the project
    3. Download the JSON key → set GOOGLE_SERVICE_ACCOUNT_PATH in .env
    4. Share your Google Sheet with the service account email (Editor access)
    5. Set GOOGLE_SHEETS_ID in .env (the ID from the sheet URL)
"""

import os
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Column order in the tracker sheet
COLUMNS = [
    "Job Title",
    "Company",
    "JD URL",
    "Email Used",
    "Date",
    "Resume File",
    "ATS Score",
    "Status",
    "Notes",
]

_HEADER_ROW = COLUMNS


def _get_sheets_service(service_account_path: str):
    """Build an authenticated Google Sheets API service object."""
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        raise ImportError(
            "Google API packages not installed. Run: "
            "pip install google-api-python-client google-auth"
        )

    if not os.path.exists(service_account_path):
        raise FileNotFoundError(
            f"Service account JSON not found at {service_account_path}. "
            "Download it from Google Cloud Console → Service Accounts."
        )

    creds = Credentials.from_service_account_file(service_account_path, scopes=SHEETS_SCOPES)
    return build("sheets", "v4", credentials=creds)


def _ensure_header(service, sheet_id: str, tab_name: str = "Sheet1") -> None:
    """Add header row if the sheet is empty."""
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"{tab_name}!A1:I1",
    ).execute()

    values = result.get("values", [])
    if not values or values[0] != _HEADER_ROW:
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{tab_name}!A1",
            valueInputOption="RAW",
            body={"values": [_HEADER_ROW]},
        ).execute()
        logger.info("Header row written to Google Sheet")


def log_application(
    job_dict: dict,
    pdf_path: str,
    ats_score: float,
    status: str,
    notes: str = "",
    sheet_id: Optional[str] = None,
    service_account_path: Optional[str] = None,
    tab_name: str = "Sheet1",
) -> bool:
    """
    Append a row to the Google Sheets tracker.

    Args:
        job_dict:             Job metadata dict.
        pdf_path:             Path to the compiled PDF.
        ats_score:            ATS keyword match score (0–100).
        status:               Job status string (e.g. 'ready', 'low_ats').
        notes:                Optional notes column text.
        sheet_id:             Google Sheet ID (from URL). Falls back to env var.
        service_account_path: Path to service account JSON. Falls back to env var.
        tab_name:             Sheet tab name (default: 'Sheet1').

    Returns:
        True on success, False on failure.
    """
    sheet_id = sheet_id or os.getenv("GOOGLE_SHEETS_ID", "")
    service_account_path = service_account_path or os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "")

    if not sheet_id or not service_account_path:
        logger.warning("Google Sheets not configured — skipping tracker update")
        return False

    try:
        service = _get_sheets_service(service_account_path)
        _ensure_header(service, sheet_id, tab_name)

        pdf_filename = os.path.basename(pdf_path) if pdf_path else ""
        today = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        applicant_email = os.getenv("APPLICANT_EMAIL", "")

        row = [
            job_dict.get("title", ""),
            job_dict.get("company", ""),
            job_dict.get("url", ""),
            applicant_email,
            today,
            pdf_filename,
            f"{ats_score:.1f}%" if ats_score else "",
            status,
            notes,
        ]

        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=f"{tab_name}!A1",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()

        logger.info(
            "Logged to Google Sheets: %s at %s (status: %s)",
            job_dict.get("title"), job_dict.get("company"), status,
        )
        return True

    except FileNotFoundError as e:
        logger.warning("Google Sheets: %s", e)
        return False
    except Exception as e:
        logger.error("Google Sheets logging failed: %s", e)
        return False
