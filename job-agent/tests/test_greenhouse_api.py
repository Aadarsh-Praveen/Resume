"""
Tests for sources/greenhouse_api.py — all HTTP calls mocked.
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sources.greenhouse_api import fetch_greenhouse_jobs, _fetch_company_jobs, _is_relevant

SAMPLE_GREENHOUSE_RESPONSE = {
    "jobs": [
        {
            "id": 1001,
            "title": "Senior Data Scientist",
            "absolute_url": "https://boards.greenhouse.io/stripe/jobs/1001",
            "content": "<p>We need Python, SQL, and machine learning expertise.</p>",
            "offices": [{"name": "San Francisco, CA"}],
            "updated_at": "2026-04-07T10:00:00Z",
        },
        {
            "id": 1002,
            "title": "ML Engineer",
            "absolute_url": "https://boards.greenhouse.io/stripe/jobs/1002",
            "content": "<p>Build ML infrastructure with PyTorch and AWS.</p>",
            "offices": [{"name": "Remote"}],
            "updated_at": "2026-04-08T10:00:00Z",
        },
        {
            "id": 1003,
            "title": "Director of Sales",  # Should be filtered out
            "absolute_url": "https://boards.greenhouse.io/stripe/jobs/1003",
            "content": "<p>Lead the sales team.</p>",
            "offices": [{"name": "New York"}],
            "updated_at": "2026-04-06T10:00:00Z",
        },
    ]
}


class TestIsRelevant(unittest.TestCase):

    def test_data_scientist_is_relevant(self):
        self.assertTrue(_is_relevant("Senior Data Scientist"))

    def test_ml_engineer_is_relevant(self):
        self.assertTrue(_is_relevant("ML Engineer", "machine learning models"))

    def test_sales_director_not_relevant(self):
        self.assertFalse(_is_relevant("Director of Sales"))

    def test_data_analyst_excluded(self):
        self.assertFalse(_is_relevant("Data Analyst"))

    def test_ai_engineer_relevant(self):
        self.assertTrue(_is_relevant("AI Engineer"))


class TestFetchCompanyJobs(unittest.TestCase):

    @patch("sources.greenhouse_api.requests.get")
    def test_fetches_and_filters_jobs(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_GREENHOUSE_RESPONSE
        mock_get.return_value = mock_resp

        jobs = _fetch_company_jobs("stripe", "Stripe")

        # Director of Sales should be filtered
        titles = [j["title"] for j in jobs]
        self.assertIn("Senior Data Scientist", titles)
        self.assertIn("ML Engineer", titles)
        self.assertNotIn("Director of Sales", titles)

    @patch("sources.greenhouse_api.requests.get")
    def test_404_returns_empty(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        jobs = _fetch_company_jobs("nonexistent", "No Company")
        self.assertEqual(jobs, [])

    @patch("sources.greenhouse_api.requests.get")
    def test_job_has_required_fields(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_GREENHOUSE_RESPONSE
        mock_get.return_value = mock_resp

        jobs = _fetch_company_jobs("stripe", "Stripe")
        for job in jobs:
            self.assertIn("title", job)
            self.assertIn("company", job)
            self.assertIn("url", job)
            self.assertIn("source", job)
            self.assertEqual(job["source"], "greenhouse")

    @patch("sources.greenhouse_api.requests.get")
    def test_network_error_returns_empty(self, mock_get):
        import requests as req_lib
        mock_get.side_effect = req_lib.ConnectionError("network error")

        jobs = _fetch_company_jobs("stripe", "Stripe")
        self.assertEqual(jobs, [])


class TestFetchGreenhouseJobs(unittest.TestCase):

    @patch("sources.greenhouse_api._fetch_company_jobs")
    def test_aggregates_all_companies(self, mock_fetch):
        mock_fetch.return_value = [
            {"title": "Data Scientist", "company": "Test Co", "url": "https://a.com",
             "source": "greenhouse", "jd_text": "", "posted_date": ""},
        ]
        test_companies = {"co1": "Company 1", "co2": "Company 2"}
        jobs = fetch_greenhouse_jobs(test_companies)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(mock_fetch.call_count, 2)

    @patch("sources.greenhouse_api._fetch_company_jobs")
    def test_handles_empty_company_list(self, mock_fetch):
        jobs = fetch_greenhouse_jobs({})
        self.assertEqual(jobs, [])
        mock_fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
