"""
Telegram bot alert sender.

Sends a formatted message with resume preview, apply link, and recruiter info
to your Telegram chat when a resume is processed.

Setup:
    1. Message @BotFather on Telegram → /newbot
    2. Get your bot token
    3. Start a chat with your bot, then visit:
       https://api.telegram.org/bot<TOKEN>/getUpdates
       to find your chat_id
    4. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env
"""

import os
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"
REQUEST_TIMEOUT = 30


def _bot_url(token: str, method: str) -> str:
    return f"{TELEGRAM_API_BASE.format(token=token)}/{method}"


def _format_message(
    job_dict: dict,
    pdf_path: str,
    ats_score: float,
    recruiter_info: Optional[dict] = None,
    cold_email: Optional[str] = None,
) -> str:
    """Build the formatted Telegram alert message."""
    company = job_dict.get("company", "Unknown")
    title = job_dict.get("title", "Unknown Role")
    apply_url = job_dict.get("url", "")
    posted_date = job_dict.get("posted_date", "")
    from datetime import datetime
    processed_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"🎯 <b>{title} — {company}</b>",
        "",
    ]

    if posted_date:
        lines.append(f"📅 Posted: {posted_date}   |   Processed: {processed_at}")
    else:
        lines.append(f"📅 Processed: {processed_at}")

    if apply_url:
        lines.append(f"🔗 <a href=\"{apply_url}\">Apply here</a>")

    lines.append("")

    if recruiter_info:
        name = recruiter_info.get("name", "")
        rec_title = recruiter_info.get("title", "")
        email = recruiter_info.get("email", "")
        linkedin = recruiter_info.get("linkedin_url", "")

        if name:
            lines.append(f"👤 Recruiter: <b>{name}</b>{f', {rec_title}' if rec_title else ''}")
        if email:
            lines.append(f"📧 {email}")
        if linkedin:
            lines.append(f"🔗 <a href=\"{linkedin}\">{linkedin}</a>")
        lines.append("")

    if cold_email:
        lines.append("✉️ <b>Cold email draft (copy &amp; paste):</b>")
        lines.append(f"<i>{cold_email}</i>")
        lines.append("")

    pdf_filename = os.path.basename(pdf_path) if pdf_path else "N/A"
    lines.append(f"📁 Resume: <code>{pdf_filename}</code>")

    if ats_score:
        score_emoji = "✓" if 89 <= ats_score <= 93 else ("⚠️" if ats_score > 93 else "✗")
        lines.append(f"📊 ATS score: <b>{ats_score:.1f}%</b> {score_emoji} (target: 89–93%)")

    return "\n".join(lines)


def send_alert(
    job_dict: dict,
    pdf_path: str,
    ats_score: float,
    recruiter_info: Optional[dict] = None,
    cold_email: Optional[str] = None,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> bool:
    """
    Send a Telegram alert with the resume preview image and job details.

    Args:
        job_dict:      Job metadata dict.
        pdf_path:      Path to the compiled PDF.
        ats_score:     ATS keyword match score.
        recruiter_info: Optional dict with recruiter details.
        cold_email:    Optional cold email draft text.
        bot_token:     Telegram bot token. Falls back to env var.
        chat_id:       Telegram chat ID. Falls back to env var.

    Returns:
        True on success, False on failure.
    """
    bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")

    if not bot_token or not chat_id:
        logger.warning("Telegram not configured — skipping alert")
        return False

    caption = _format_message(job_dict, pdf_path, ats_score, recruiter_info, cold_email)

    # Try to render and send preview image, then clean up the temp JPEG
    preview_sent = False
    if pdf_path and os.path.exists(pdf_path):
        preview_path = ""
        try:
            from pipeline.latex_compiler import render_preview
            preview_path = render_preview(pdf_path)
            if preview_path and os.path.exists(preview_path):
                preview_sent = _send_photo(bot_token, chat_id, preview_path, caption)
        except Exception as e:
            logger.warning("Preview render failed: %s", e)
        finally:
            # Always remove the temp JPEG — only PDFs belong in resumes/
            if preview_path and os.path.exists(preview_path):
                try:
                    os.remove(preview_path)
                except OSError:
                    pass

    # If preview failed, send text-only message
    if not preview_sent:
        return _send_message(bot_token, chat_id, caption)

    return preview_sent


def _send_photo(bot_token: str, chat_id: str, photo_path: str, caption: str) -> bool:
    """Send a photo with caption to Telegram."""
    url = _bot_url(bot_token, "sendPhoto")
    try:
        with open(photo_path, "rb") as photo_file:
            resp = requests.post(
                url,
                data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                files={"photo": photo_file},
                timeout=REQUEST_TIMEOUT,
            )
        resp.raise_for_status()
        logger.info("Telegram photo sent successfully")
        return True
    except Exception as e:
        logger.error("Telegram sendPhoto failed: %s", e)
        return False


def _send_message(bot_token: str, chat_id: str, text: str) -> bool:
    """Send a text message to Telegram."""
    url = _bot_url(bot_token, "sendMessage")
    try:
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        logger.info("Telegram message sent successfully")
        return True
    except Exception as e:
        logger.error("Telegram sendMessage failed: %s", e)
        return False


def send_error_alert(
    error_msg: str,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> bool:
    """Send an error notification to Telegram."""
    bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")

    if not bot_token or not chat_id:
        return False

    message = f"🚨 <b>Job Agent Error</b>\n\n<code>{error_msg[:2000]}</code>"
    return _send_message(bot_token, chat_id, message)


def send_daily_digest(
    jobs_today: list[dict],
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> bool:
    """
    Send a daily morning digest summarising today's processed jobs.

    Args:
        jobs_today: List of job dicts processed today (from dedup.get_todays_processed_jobs).
    """
    bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")

    if not bot_token or not chat_id:
        return False

    if not jobs_today:
        message = "☀️ <b>Daily Digest</b>\n\nNo new resumes processed today."
    else:
        ready = [j for j in jobs_today if j.get("status") == "ready"]
        failed = [j for j in jobs_today if j.get("status") not in ("ready", "high_ats")]

        lines = [
            f"☀️ <b>Daily Digest — {len(jobs_today)} jobs processed</b>",
            "",
            f"✅ Ready to apply: <b>{len(ready)}</b>",
        ]
        for job in ready:
            lines.append(f"  • {job.get('company')} — {job.get('title')}")

        if failed:
            lines.append(f"\n❌ Failed / needs review: <b>{len(failed)}</b>")
            for job in failed:
                lines.append(f"  • {job.get('company')} — {job.get('title')} ({job.get('status')})")

        message = "\n".join(lines)

    return _send_message(bot_token, chat_id, message)
