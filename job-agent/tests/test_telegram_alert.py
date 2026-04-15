"""
Tests for outputs/telegram_alert.py — all Telegram API calls mocked.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from outputs.telegram_alert import (
    _format_message,
    send_alert,
    send_error_alert,
    send_daily_digest,
    _send_message,
)

SAMPLE_JOB = {
    "title": "Senior Data Scientist",
    "company": "Louis Vuitton",
    "url": "https://careers.louisvuitton.com/job/12345",
    "posted_date": "2026-04-07",
}

SAMPLE_RECRUITER = {
    "name": "Sarah Chen",
    "title": "Talent Acquisition Manager",
    "email": "sarah.chen@lv.com",
    "linkedin_url": "https://linkedin.com/in/sarahchen-lv",
}


class TestFormatMessage(unittest.TestCase):

    def test_contains_job_title_and_company(self):
        msg = _format_message(SAMPLE_JOB, "/resumes/LV_DS.pdf", 91.0)
        self.assertIn("Senior Data Scientist", msg)
        self.assertIn("Louis Vuitton", msg)

    def test_contains_ats_score(self):
        msg = _format_message(SAMPLE_JOB, "/resumes/LV_DS.pdf", 91.0)
        self.assertIn("91.0%", msg)

    def test_ats_pass_shows_checkmark(self):
        msg = _format_message(SAMPLE_JOB, "/resumes/LV_DS.pdf", 91.0)
        self.assertIn("✓", msg)

    def test_ats_low_shows_x(self):
        msg = _format_message(SAMPLE_JOB, "/resumes/LV_DS.pdf", 75.0)
        self.assertIn("✗", msg)

    def test_ats_high_shows_warning(self):
        msg = _format_message(SAMPLE_JOB, "/resumes/LV_DS.pdf", 95.0)
        self.assertIn("⚠️", msg)

    def test_recruiter_info_included(self):
        msg = _format_message(SAMPLE_JOB, "/resumes/LV_DS.pdf", 91.0,
                              recruiter_info=SAMPLE_RECRUITER)
        self.assertIn("Sarah Chen", msg)
        self.assertIn("sarah.chen@lv.com", msg)

    def test_cold_email_included(self):
        cold_email = "Hi Sarah — I wanted to reach out about the Data Scientist role."
        msg = _format_message(SAMPLE_JOB, "/resumes/LV_DS.pdf", 91.0,
                              cold_email=cold_email)
        self.assertIn("Cold email draft", msg)
        self.assertIn("Hi Sarah", msg)

    def test_apply_link_included(self):
        msg = _format_message(SAMPLE_JOB, "/resumes/LV_DS.pdf", 91.0)
        self.assertIn("careers.louisvuitton.com", msg)

    def test_pdf_filename_in_message(self):
        msg = _format_message(SAMPLE_JOB, "/resumes/LV_DS.pdf", 91.0)
        self.assertIn("LV_DS.pdf", msg)

    def test_no_recruiter_no_crash(self):
        msg = _format_message(SAMPLE_JOB, "/resumes/LV_DS.pdf", 91.0,
                              recruiter_info=None, cold_email=None)
        self.assertIn("Senior Data Scientist", msg)


class TestSendAlert(unittest.TestCase):

    @patch("outputs.telegram_alert._send_message")
    @patch("outputs.telegram_alert._send_photo", return_value=False)
    def test_falls_back_to_text_when_photo_fails(self, mock_photo, mock_msg):
        mock_msg.return_value = True
        result = send_alert(SAMPLE_JOB, "", 91.0,
                           bot_token="test_token", chat_id="12345")
        mock_msg.assert_called_once()
        self.assertTrue(result)

    def test_returns_false_when_not_configured(self):
        result = send_alert(SAMPLE_JOB, "", 91.0,
                           bot_token="", chat_id="")
        self.assertFalse(result)

    @patch("outputs.telegram_alert._send_message", return_value=True)
    def test_sends_without_recruiter_info(self, mock_msg):
        result = send_alert(SAMPLE_JOB, "", 91.0,
                           bot_token="tok", chat_id="999")
        self.assertTrue(result)


class TestSendErrorAlert(unittest.TestCase):

    @patch("outputs.telegram_alert._send_message", return_value=True)
    def test_sends_error_message(self, mock_msg):
        result = send_error_alert("Something broke", bot_token="tok", chat_id="999")
        self.assertTrue(result)
        call_args = mock_msg.call_args[0]
        self.assertIn("Error", call_args[2])

    def test_returns_false_when_not_configured(self):
        result = send_error_alert("error", bot_token="", chat_id="")
        self.assertFalse(result)


class TestSendDailyDigest(unittest.TestCase):

    @patch("outputs.telegram_alert._send_message", return_value=True)
    def test_digest_with_jobs(self, mock_msg):
        jobs = [
            {"title": "Data Scientist", "company": "Stripe", "status": "ready"},
            {"title": "ML Engineer", "company": "Airbnb", "status": "low_ats"},
        ]
        result = send_daily_digest(jobs, bot_token="tok", chat_id="999")
        self.assertTrue(result)
        call_text = mock_msg.call_args[0][2]
        self.assertIn("2 jobs processed", call_text)
        self.assertIn("Stripe", call_text)

    @patch("outputs.telegram_alert._send_message", return_value=True)
    def test_digest_with_no_jobs(self, mock_msg):
        result = send_daily_digest([], bot_token="tok", chat_id="999")
        self.assertTrue(result)
        call_text = mock_msg.call_args[0][2]
        self.assertIn("No new resumes", call_text)

    def test_returns_false_when_not_configured(self):
        result = send_daily_digest([], bot_token="", chat_id="")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
