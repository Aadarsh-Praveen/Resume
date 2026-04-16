"""
Tests for sources/workday_api.py — mocks HTTP to avoid network calls.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sources.workday_api import _fetch_company_jobs, fetch_workday_jobs


SAMPLE_RESPONSE = {
    "jobPostings": [
        {
            "title": "Senior Data Scientist",
            "externalPath": "/jobs/senior-data-scientist-R12345",
            "locationsText": "Santa Clara, CA",
            "postedOn": "2024-04-01",
        },
        {
            "title": "Machine Learning Engineer",
            "externalPath": "/jobs/mle-R22222",
            "locationsText": "Remote",
            "postedOn": "2024-04-02",
        },
        {
            "title": "VP of Engineering",
            "externalPath": "/jobs/vp-eng-R99999",
            "locationsText": "Santa Clara, CA",
            "postedOn": "2024-04-01",
        },
    ]
}


class TestFetchCompanyJobs(unittest.TestCase):

    @patch("sources.workday_api.requests.post")
    def test_returns_only_relevant_jobs(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        jobs = _fetch_company_jobs("nvidia", "NVIDIAExternalCareerSite", "NVIDIA", "data scientist")
        titles = [j["title"] for j in jobs]
        self.assertIn("Senior Data Scientist", titles)
        self.assertIn("Machine Learning Engineer", titles)
        self.assertNotIn("VP of Engineering", titles)

    @patch("sources.workday_api.requests.post")
    def test_sets_correct_company_name(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        jobs = _fetch_company_jobs("nvidia", "NVIDIAExternalCareerSite", "NVIDIA", "data scientist")
        for j in jobs:
            self.assertEqual(j["company"], "NVIDIA")

    @patch("sources.workday_api.requests.post")
    def test_constructs_correct_job_url(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "jobPostings": [{
                "title": "Data Scientist",
                "externalPath": "/jobs/ds-R11111",
                "locationsText": "Remote",
                "postedOn": "2024-04-01",
            }]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        jobs = _fetch_company_jobs("tesla", "TeslaCareerSite", "Tesla", "data scientist")
        self.assertEqual(len(jobs), 1)
        expected = "https://tesla.wd5.myworkdayjobs.com/en-US/TeslaCareerSite/job/jobs/ds-R11111"
        self.assertEqual(jobs[0]["url"], expected)

    @patch("sources.workday_api.requests.post")
    def test_source_is_workday(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        jobs = _fetch_company_jobs("nvidia", "NVIDIAExternalCareerSite", "NVIDIA", "data scientist")
        for j in jobs:
            self.assertEqual(j["source"], "workday")

    @patch("sources.workday_api.requests.post")
    def test_handles_404_board_not_found(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_post.return_value = mock_resp

        jobs = _fetch_company_jobs("badtenant", "badboard", "BadCo", "data scientist")
        self.assertEqual(jobs, [])

    @patch("sources.workday_api.requests.post")
    def test_handles_403_blocked(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_post.return_value = mock_resp

        jobs = _fetch_company_jobs("nvidia", "NVIDIAExternalCareerSite", "NVIDIA", "data scientist")
        self.assertEqual(jobs, [])

    @patch("sources.workday_api.requests.post")
    def test_handles_429_rate_limited(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_post.return_value = mock_resp

        jobs = _fetch_company_jobs("nvidia", "NVIDIAExternalCareerSite", "NVIDIA", "data scientist")
        self.assertEqual(jobs, [])

    @patch("sources.workday_api.requests.post")
    def test_empty_postings_returns_empty_list(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"jobPostings": []}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        jobs = _fetch_company_jobs("nvidia", "NVIDIAExternalCareerSite", "NVIDIA", "data scientist")
        self.assertEqual(jobs, [])

    @patch("sources.workday_api.time.sleep")
    @patch("sources.workday_api.requests.post")
    def test_retries_three_times_on_network_error(self, mock_post, mock_sleep):
        import requests as req_lib
        mock_post.side_effect = req_lib.ConnectionError("timeout")

        jobs = _fetch_company_jobs("nvidia", "NVIDIAExternalCareerSite", "NVIDIA", "data scientist")
        self.assertEqual(jobs, [])
        self.assertEqual(mock_post.call_count, 3)

    @patch("sources.workday_api.requests.post")
    def test_extracts_location_and_posted_date(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "jobPostings": [{
                "title": "Applied Scientist",
                "externalPath": "/jobs/applied-scientist-R33333",
                "locationsText": "Austin, TX",
                "postedOn": "2024-05-01",
            }]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        jobs = _fetch_company_jobs("salesforce", "External_Career_Site", "Salesforce", "data scientist")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["location"], "Austin, TX")
        self.assertEqual(jobs[0]["posted_date"], "2024-05-01")

    @patch("sources.workday_api.requests.post")
    def test_n_locations_falls_back_to_external_path(self, mock_post):
        """When locationsText is 'N Locations', location is parsed from externalPath."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "jobPostings": [
                {
                    "title": "Data Scientist",
                    "externalPath": "job/US-CA-Santa-Clara/Data-Scientist-R12345",
                    "locationsText": "3 Locations",
                    "postedOn": "2024-04-01",
                },
                {
                    "title": "Machine Learning Engineer",
                    "externalPath": "job/China-Shanghai/MLE-R99999",
                    "locationsText": "2 Locations",
                    "postedOn": "2024-04-01",
                },
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        jobs = _fetch_company_jobs("nvidia", "NVIDIAExternalCareerSite", "NVIDIA", "data scientist")
        # US job: externalPath segment → "US, CA, Santa Clara"
        us_job = next((j for j in jobs if "Data Scientist" in j["title"]), None)
        self.assertIsNotNone(us_job)
        self.assertEqual(us_job["location"], "US, CA, Santa Clara")
        # China job: location parsed as "China, Shanghai"
        china_job = next((j for j in jobs if "Machine Learning" in j["title"]), None)
        self.assertIsNotNone(china_job)
        self.assertEqual(china_job["location"], "China, Shanghai")

    @patch("sources.workday_api.requests.post")
    def test_skips_posting_with_missing_external_path(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "jobPostings": [
                {"title": "Data Scientist", "externalPath": "", "locationsText": "Remote"},
                {"title": "ML Engineer", "externalPath": "/jobs/mle-R44444", "locationsText": "Remote"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        jobs = _fetch_company_jobs("nvidia", "NVIDIAExternalCareerSite", "NVIDIA", "data scientist")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "ML Engineer")


class TestFetchWorkdayJobs(unittest.TestCase):

    @patch("sources.workday_api._fetch_company_jobs")
    def test_aggregates_all_companies(self, mock_fetch):
        mock_fetch.return_value = [{
            "title": "Data Scientist", "company": "NVIDIA",
            "url": "https://example.com/1", "location": "US",
            "jd_text": "", "source": "workday", "posted_date": "",
        }]
        companies = {
            "nvidia": {"board": "NVIDIAExternalCareerSite", "name": "NVIDIA", "search": "data scientist"},
            "tesla":  {"board": "TeslaCareerSite",          "name": "Tesla",  "search": "data scientist"},
        }
        jobs = fetch_workday_jobs(companies)
        self.assertEqual(len(jobs), 2)  # one result per company
        self.assertEqual(mock_fetch.call_count, 2)

    @patch("sources.workday_api._fetch_company_jobs")
    def test_passes_correct_args_to_fetcher(self, mock_fetch):
        mock_fetch.return_value = []
        companies = {
            "apple": {"board": "Apple", "name": "Apple", "search": "machine learning"},
        }
        fetch_workday_jobs(companies)
        mock_fetch.assert_called_once_with("apple", "Apple", "Apple", "machine learning")

    @patch("sources.workday_api._fetch_company_jobs")
    def test_uses_default_search_when_not_specified(self, mock_fetch):
        mock_fetch.return_value = []
        companies = {
            "nvidia": {"board": "NVIDIAExternalCareerSite", "name": "NVIDIA"},
        }
        fetch_workday_jobs(companies)
        mock_fetch.assert_called_once_with("nvidia", "NVIDIAExternalCareerSite", "NVIDIA", "data scientist")

    @patch("sources.workday_api._fetch_company_jobs")
    def test_continues_on_company_failure(self, mock_fetch):
        mock_fetch.side_effect = [Exception("network error"), []]
        companies = {
            "nvidia": {"board": "NVIDIAExternalCareerSite", "name": "NVIDIA", "search": "data scientist"},
            "tesla":  {"board": "TeslaCareerSite",          "name": "Tesla",  "search": "data scientist"},
        }
        # Should not raise — errors per company are caught
        jobs = fetch_workday_jobs(companies)
        self.assertIsInstance(jobs, list)


if __name__ == "__main__":
    unittest.main()
