"""
Tests for sources/linkedin_jobs.py — mocks HTTP to avoid network calls.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sources.linkedin_jobs import _parse_job_cards, _is_relevant, fetch_linkedin_jobs


SAMPLE_HTML = """
<ul>
  <li>
    <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/12345?trk=abc">
    </a>
    <h3 class="base-search-card__title">Senior Data Scientist</h3>
    <h4 class="base-search-card__subtitle">
      <a href="#">Stripe</a>
    </h4>
    <span class="job-search-card__location">San Francisco, CA</span>
    <time class="job-search-card__listdate" datetime="2024-04-01"></time>
  </li>
  <li>
    <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/99999">
    </a>
    <h3 class="base-search-card__title">VP of Engineering</h3>
    <h4 class="base-search-card__subtitle">
      <a href="#">Acme Corp</a>
    </h4>
    <span class="job-search-card__location">New York, NY</span>
  </li>
  <li>
    <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/55555">
    </a>
    <h3 class="base-search-card__title">Machine Learning Engineer</h3>
    <h4 class="base-search-card__subtitle">
      <a href="#">OpenAI</a>
    </h4>
    <span class="job-search-card__location">Remote</span>
  </li>
</ul>
"""


class TestParseJobCards(unittest.TestCase):

    def test_extracts_relevant_jobs(self):
        jobs = _parse_job_cards(SAMPLE_HTML)
        titles = [j["title"] for j in jobs]
        self.assertIn("Senior Data Scientist", titles)
        self.assertIn("Machine Learning Engineer", titles)

    def test_filters_vp_title(self):
        jobs = _parse_job_cards(SAMPLE_HTML)
        titles = [j["title"] for j in jobs]
        self.assertNotIn("VP of Engineering", titles)

    def test_strips_tracking_params_from_url(self):
        jobs = _parse_job_cards(SAMPLE_HTML)
        for j in jobs:
            self.assertNotIn("?", j["url"])
            self.assertNotIn("trk=", j["url"])

    def test_extracts_company(self):
        jobs = _parse_job_cards(SAMPLE_HTML)
        ds_job = next(j for j in jobs if j["title"] == "Senior Data Scientist")
        self.assertEqual(ds_job["company"], "Stripe")

    def test_extracts_location(self):
        jobs = _parse_job_cards(SAMPLE_HTML)
        ds_job = next(j for j in jobs if j["title"] == "Senior Data Scientist")
        self.assertEqual(ds_job["location"], "San Francisco, CA")

    def test_extracts_posted_date(self):
        jobs = _parse_job_cards(SAMPLE_HTML)
        ds_job = next(j for j in jobs if j["title"] == "Senior Data Scientist")
        self.assertEqual(ds_job["posted_date"], "2024-04-01")

    def test_source_is_linkedin(self):
        jobs = _parse_job_cards(SAMPLE_HTML)
        for j in jobs:
            self.assertEqual(j["source"], "linkedin")

    def test_empty_html_returns_empty_list(self):
        jobs = _parse_job_cards("<html><body></body></html>")
        self.assertEqual(jobs, [])

    def test_jd_text_is_empty_string(self):
        jobs = _parse_job_cards(SAMPLE_HTML)
        for j in jobs:
            self.assertEqual(j["jd_text"], "")


class TestIsRelevant(unittest.TestCase):

    def test_data_scientist_is_relevant(self):
        self.assertTrue(_is_relevant("Senior Data Scientist"))

    def test_machine_learning_engineer_is_relevant(self):
        self.assertTrue(_is_relevant("Machine Learning Engineer"))

    def test_ai_engineer_is_relevant(self):
        self.assertTrue(_is_relevant("AI Engineer, Trust & Safety"))

    def test_nlp_in_description_is_relevant(self):
        self.assertTrue(_is_relevant("Research Engineer", "NLP and LLM applications"))

    def test_vp_is_excluded(self):
        self.assertFalse(_is_relevant("VP of Data Science"))

    def test_director_is_excluded(self):
        self.assertFalse(_is_relevant("Director of Machine Learning"))

    def test_data_analyst_is_excluded(self):
        self.assertFalse(_is_relevant("Data Analyst"))

    def test_data_engineer_is_excluded(self):
        self.assertFalse(_is_relevant("Data Engineer"))

    def test_unrelated_role_not_relevant(self):
        self.assertFalse(_is_relevant("Software Engineer, Backend"))

    def test_principal_engineer_excluded(self):
        self.assertFalse(_is_relevant("Principal Engineer"))


class TestFetchLinkedinJobs(unittest.TestCase):

    @patch("sources.linkedin_jobs.requests.get")
    def test_returns_jobs_on_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        jobs = fetch_linkedin_jobs([{"keywords": "data scientist", "location": "United States"}])
        self.assertGreater(len(jobs), 0)

    @patch("sources.linkedin_jobs.requests.get")
    def test_deduplicates_across_queries(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        # Two identical queries → same URLs, should be deduped
        queries = [
            {"keywords": "data scientist", "location": "United States"},
            {"keywords": "data scientist", "location": "United States"},
        ]
        jobs = fetch_linkedin_jobs(queries)
        urls = [j["url"] for j in jobs]
        self.assertEqual(len(urls), len(set(urls)))

    @patch("sources.linkedin_jobs.requests.get")
    def test_handles_429_rate_limit(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_get.return_value = mock_resp

        jobs = fetch_linkedin_jobs([{"keywords": "data scientist", "location": "United States"}])
        self.assertEqual(jobs, [])

    @patch("sources.linkedin_jobs.requests.get")
    def test_handles_403_blocked(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_get.return_value = mock_resp

        jobs = fetch_linkedin_jobs([{"keywords": "data scientist", "location": "United States"}])
        self.assertEqual(jobs, [])

    @patch("sources.linkedin_jobs.requests.get")
    def test_handles_network_error(self, mock_get):
        import requests as req_lib
        mock_get.side_effect = req_lib.ConnectionError("connection refused")

        jobs = fetch_linkedin_jobs([{"keywords": "data scientist", "location": "United States"}])
        self.assertEqual(jobs, [])

    @patch("sources.linkedin_jobs.requests.get")
    def test_uses_default_queries_when_none_provided(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<ul></ul>"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        # Should not raise — uses config.LINKEDIN_QUERIES
        jobs = fetch_linkedin_jobs()
        self.assertIsInstance(jobs, list)


if __name__ == "__main__":
    unittest.main()
