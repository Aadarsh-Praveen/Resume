"""
Tests for sources/lever_api.py — all HTTP calls mocked.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sources.lever_api import fetch_lever_jobs, _fetch_company_jobs, _is_relevant, _extract_text

SAMPLE_LEVER_RESPONSE = [
    {
        "id": "abc-123",
        "text": "Senior Data Scientist",
        "hostedUrl": "https://jobs.lever.co/netflix/abc-123",
        "applyUrl": "https://jobs.lever.co/netflix/abc-123/apply",
        "categories": {"team": "Data Science", "location": "Los Angeles, CA"},
        "descriptionPlain": "We need Python, machine learning, and SQL skills.",
        "createdAt": 1712448000000,
    },
    {
        "id": "def-456",
        "text": "ML Infrastructure Engineer",
        "hostedUrl": "https://jobs.lever.co/netflix/def-456",
        "applyUrl": "",
        "categories": {"team": "Platform", "location": "Remote"},
        "descriptionPlain": "Build ML pipelines with PyTorch and Kubernetes.",
        "createdAt": 1712448001000,
    },
    {
        "id": "ghi-789",
        "text": "Accountant",  # Should be filtered out
        "hostedUrl": "https://jobs.lever.co/netflix/ghi-789",
        "applyUrl": "",
        "categories": {"team": "Finance", "location": "Remote"},
        "descriptionPlain": "Financial reporting and accounting.",
        "createdAt": 1712448002000,
    },
]


class TestIsRelevant(unittest.TestCase):

    def test_data_scientist_relevant(self):
        self.assertTrue(_is_relevant("Senior Data Scientist"))

    def test_ml_engineer_relevant(self):
        self.assertTrue(_is_relevant("ML Infrastructure Engineer"))

    def test_accountant_not_relevant(self):
        self.assertFalse(_is_relevant("Accountant"))

    def test_title_only_matching(self):
        # Description is no longer used — only the title is checked
        self.assertFalse(_is_relevant("Research Engineer"))


class TestExtractText(unittest.TestCase):

    def test_string_content(self):
        lists = [{"content": "Hello world"}, {"content": "Python skills"}]
        result = _extract_text(lists)
        self.assertIn("Hello world", result)
        self.assertIn("Python skills", result)

    def test_list_content(self):
        lists = [{"content": ["Python", "SQL", "PyTorch"]}]
        result = _extract_text(lists)
        self.assertIn("Python", result)

    def test_empty_lists(self):
        result = _extract_text([])
        self.assertEqual(result, "")

    def test_none_lists(self):
        result = _extract_text(None)
        self.assertEqual(result, "")


class TestFetchCompanyJobs(unittest.TestCase):

    @patch("sources.lever_api.requests.get")
    def test_fetches_and_filters_jobs(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_LEVER_RESPONSE
        mock_get.return_value = mock_resp

        jobs = _fetch_company_jobs("netflix", "Netflix")
        titles = [j["title"] for j in jobs]
        self.assertIn("Senior Data Scientist", titles)
        self.assertIn("ML Infrastructure Engineer", titles)
        self.assertNotIn("Accountant", titles)

    @patch("sources.lever_api.requests.get")
    def test_404_returns_empty(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        jobs = _fetch_company_jobs("ghost", "Ghost Company")
        self.assertEqual(jobs, [])

    @patch("sources.lever_api.requests.get")
    def test_job_fields_populated(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_LEVER_RESPONSE
        mock_get.return_value = mock_resp

        jobs = _fetch_company_jobs("netflix", "Netflix")
        for job in jobs:
            self.assertIn("title", job)
            self.assertIn("company", job)
            self.assertIn("url", job)
            self.assertEqual(job["source"], "lever")

    @patch("sources.lever_api.requests.get")
    def test_uses_hosted_url_when_apply_url_empty(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Entry with empty applyUrl — uses hostedUrl instead
        entry = {
            "id": "def-456",
            "text": "ML Infrastructure Engineer",
            "hostedUrl": "https://jobs.lever.co/netflix/def-456",
            "applyUrl": "",  # empty — should fall back to hostedUrl
            "categories": {"team": "Platform", "location": "Remote"},
            "descriptionPlain": "Build ML pipelines with PyTorch and Kubernetes.",
            "createdAt": 1712448001000,
        }
        mock_resp.json.return_value = [entry]
        mock_get.return_value = mock_resp

        jobs = _fetch_company_jobs("netflix", "Netflix")
        self.assertEqual(len(jobs), 1)
        self.assertIn("lever.co", jobs[0]["url"])

    @patch("sources.lever_api.requests.get")
    def test_network_error_returns_empty(self, mock_get):
        import requests as req_lib
        mock_get.side_effect = req_lib.ConnectionError("timeout")
        jobs = _fetch_company_jobs("netflix", "Netflix")
        self.assertEqual(jobs, [])


class TestFetchLeverJobs(unittest.TestCase):

    @patch("sources.lever_api._fetch_company_jobs")
    def test_aggregates_all_companies(self, mock_fetch):
        mock_fetch.return_value = [
            {"title": "Data Scientist", "company": "Netflix", "url": "https://x.com",
             "source": "lever", "jd_text": "", "posted_date": ""},
        ]
        jobs = fetch_lever_jobs({"netflix": "Netflix", "reddit": "Reddit"})
        self.assertEqual(len(jobs), 2)


if __name__ == "__main__":
    unittest.main()
