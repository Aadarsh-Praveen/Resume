"""
Tests for outputs/tracker.py — mocks Notion API calls.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from outputs.tracker import log_application, _build_page_properties, _rich_text

SAMPLE_JOB = {
    "title": "Senior Data Scientist",
    "company": "Stripe",
    "url": "https://boards.greenhouse.io/stripe/jobs/12345",
}


class TestRichText(unittest.TestCase):

    def test_string_is_wrapped(self):
        result = _rich_text("hello")
        self.assertEqual(result[0]["text"]["content"], "hello")

    def test_long_string_truncated_to_2000(self):
        long_str = "x" * 3000
        result = _rich_text(long_str)
        self.assertEqual(len(result[0]["text"]["content"]), 2000)


class TestBuildPageProperties(unittest.TestCase):

    def test_name_field_uses_title_type(self):
        props = _build_page_properties(SAMPLE_JOB, "/resumes/r.pdf", 91.0, "ready", "")
        self.assertIn("title", props["Name"])
        self.assertEqual(props["Name"]["title"][0]["text"]["content"], "Senior Data Scientist")

    def test_company_is_rich_text(self):
        props = _build_page_properties(SAMPLE_JOB, None, None, "failed", "")
        self.assertEqual(props["Company"]["rich_text"][0]["text"]["content"], "Stripe")

    def test_ats_score_as_number(self):
        props = _build_page_properties(SAMPLE_JOB, "/resumes/r.pdf", 91.5, "ready", "")
        self.assertEqual(props["ATS Score"]["number"], 91.5)

    def test_ats_score_omitted_when_none(self):
        props = _build_page_properties(SAMPLE_JOB, None, None, "failed", "")
        self.assertNotIn("ATS Score", props)

    def test_status_select(self):
        props = _build_page_properties(SAMPLE_JOB, None, 90.0, "low_ats", "")
        self.assertEqual(props["Status"]["select"]["name"], "low_ats")

    def test_jd_url_included_for_http_url(self):
        props = _build_page_properties(SAMPLE_JOB, None, None, "ready", "")
        self.assertEqual(props["JD URL"]["url"], SAMPLE_JOB["url"])

    def test_jd_url_omitted_when_empty(self):
        job = {**SAMPLE_JOB, "url": ""}
        props = _build_page_properties(job, None, None, "ready", "")
        self.assertNotIn("JD URL", props)

    def test_date_is_present(self):
        props = _build_page_properties(SAMPLE_JOB, None, None, "ready", "")
        self.assertIn("date", props["Date"])
        self.assertIn("start", props["Date"]["date"])

    def test_resume_filename_extracted(self):
        props = _build_page_properties(SAMPLE_JOB, "/resumes/stripe_ds.pdf", 91.0, "ready", "")
        self.assertEqual(
            props["Resume File"]["rich_text"][0]["text"]["content"], "stripe_ds.pdf"
        )

    def test_notes_included(self):
        props = _build_page_properties(SAMPLE_JOB, None, None, "ready", "stretch role")
        self.assertEqual(props["Notes"]["rich_text"][0]["text"]["content"], "stretch role")

    @patch.dict(os.environ, {"APPLICANT_EMAIL": "test@example.com"})
    def test_email_included_when_set(self):
        props = _build_page_properties(SAMPLE_JOB, None, None, "ready", "")
        self.assertEqual(props["Email"]["email"], "test@example.com")

    @patch.dict(os.environ, {"APPLICANT_EMAIL": ""})
    def test_email_omitted_when_empty(self):
        props = _build_page_properties(SAMPLE_JOB, None, None, "ready", "")
        self.assertNotIn("Email", props)


class TestLogApplication(unittest.TestCase):

    def test_returns_false_when_not_configured(self):
        result = log_application(SAMPLE_JOB, None, None, "ready",
                                 api_key="", database_id="")
        self.assertFalse(result)

    @patch("outputs.tracker.requests.post")
    def test_returns_true_on_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        result = log_application(
            SAMPLE_JOB, "/resumes/r.pdf", 91.0, "ready",
            api_key="secret_test", database_id="db-abc123",
        )
        self.assertTrue(result)
        mock_post.assert_called_once()

    @patch("outputs.tracker.requests.post")
    def test_posts_to_notion_pages_endpoint(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        log_application(
            SAMPLE_JOB, None, None, "failed",
            api_key="secret_test", database_id="db-xyz",
        )
        url_called = mock_post.call_args[0][0]
        self.assertIn("notion.com/v1/pages", url_called)

    @patch("outputs.tracker.requests.post")
    def test_database_id_in_payload(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        log_application(
            SAMPLE_JOB, None, None, "ready",
            api_key="secret_test", database_id="my-db-id",
        )
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["parent"]["database_id"], "my-db-id")

    @patch("outputs.tracker.requests.post")
    def test_returns_false_on_http_error(self, mock_post):
        import requests as req_lib
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"code": "validation_error", "message": "bad property"}
        mock_post.return_value = mock_resp
        mock_resp.raise_for_status.side_effect = req_lib.HTTPError(response=mock_resp)

        result = log_application(
            SAMPLE_JOB, None, None, "ready",
            api_key="secret_test", database_id="db-abc",
        )
        self.assertFalse(result)

    @patch("outputs.tracker.requests.post")
    def test_returns_false_on_network_error(self, mock_post):
        import requests as req_lib
        mock_post.side_effect = req_lib.ConnectionError("timeout")

        result = log_application(
            SAMPLE_JOB, None, None, "ready",
            api_key="secret_test", database_id="db-abc",
        )
        self.assertFalse(result)

    @patch.dict(os.environ, {"NOTION_API_KEY": "secret_env", "NOTION_DATABASE_ID": "db-env"})
    @patch("outputs.tracker.requests.post")
    def test_reads_credentials_from_env(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        # No explicit api_key/database_id — should read from env
        result = log_application(SAMPLE_JOB, None, None, "ready")
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
