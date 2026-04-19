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


def _make_mock_session(status_code=200, text=SAMPLE_HTML, side_effect=None):
    """Return a mock requests.Session whose .get() returns the configured response."""
    mock_session = MagicMock()
    if side_effect:
        mock_session.get.side_effect = side_effect
    else:
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.text = text
        mock_resp.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_resp
    return mock_session


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

    def test_generic_title_without_ml_keywords_not_relevant(self):
        # "Research Engineer" alone has no ML keyword in the title → filtered
        self.assertFalse(_is_relevant("Research Engineer"))

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

    @patch("sources.linkedin_jobs.requests.Session")
    def test_returns_jobs_on_success(self, mock_session_cls):
        mock_session_cls.return_value = _make_mock_session(200, SAMPLE_HTML)
        jobs = fetch_linkedin_jobs([{"keywords": "data scientist", "location": "United States"}])
        self.assertGreater(len(jobs), 0)

    @patch("sources.linkedin_jobs.requests.Session")
    def test_deduplicates_across_queries(self, mock_session_cls):
        mock_session_cls.return_value = _make_mock_session(200, SAMPLE_HTML)
        queries = [
            {"keywords": "data scientist", "location": "United States"},
            {"keywords": "data scientist", "location": "United States"},
        ]
        jobs = fetch_linkedin_jobs(queries)
        urls = [j["url"] for j in jobs]
        self.assertEqual(len(urls), len(set(urls)))

    @patch("sources.linkedin_jobs.time.sleep")
    @patch("sources.linkedin_jobs.requests.Session")
    def test_handles_429_rate_limit(self, mock_session_cls, mock_sleep):
        # All calls return 429 — all retries exhausted → 0 jobs
        mock_session_cls.return_value = _make_mock_session(429)
        jobs = fetch_linkedin_jobs([{"keywords": "data scientist", "location": "United States"}])
        self.assertEqual(jobs, [])

    @patch("sources.linkedin_jobs.requests.Session")
    def test_handles_403_blocked(self, mock_session_cls):
        mock_session_cls.return_value = _make_mock_session(403)
        jobs = fetch_linkedin_jobs([{"keywords": "data scientist", "location": "United States"}])
        self.assertEqual(jobs, [])

    @patch("sources.linkedin_jobs.requests.Session")
    def test_handles_network_error(self, mock_session_cls):
        import requests as req_lib
        mock_session_cls.return_value = _make_mock_session(side_effect=req_lib.ConnectionError("refused"))
        jobs = fetch_linkedin_jobs([{"keywords": "data scientist", "location": "United States"}])
        self.assertEqual(jobs, [])

    @patch("sources.linkedin_jobs.requests.Session")
    def test_uses_default_queries_when_none_provided(self, mock_session_cls):
        mock_session_cls.return_value = _make_mock_session(200, "<ul></ul>")
        jobs = fetch_linkedin_jobs()
        self.assertIsInstance(jobs, list)

    @patch("sources.linkedin_jobs.time.sleep")
    @patch("sources.linkedin_jobs.requests.Session")
    def test_stop_early_on_empty_page(self, mock_session_cls, mock_sleep):
        # Call order: warmup, page0 (jobs), page1 (empty → stop)
        mock_session = MagicMock()
        warmup_resp = MagicMock(status_code=200, text="")
        warmup_resp.raise_for_status = MagicMock()
        full_resp   = MagicMock(status_code=200, text=SAMPLE_HTML)
        full_resp.raise_for_status = MagicMock()
        empty_resp  = MagicMock(status_code=200, text="<ul></ul>")
        empty_resp.raise_for_status = MagicMock()
        mock_session.get.side_effect = [warmup_resp, full_resp, empty_resp]
        mock_session_cls.return_value = mock_session

        jobs = fetch_linkedin_jobs(
            [{"keywords": "data scientist", "location": "United States"}],
            max_pages=3,
        )
        # page0 had results, page1 empty → stop-early; calls = warmup + page0 + page1 = 3
        self.assertGreater(len(jobs), 0)
        self.assertLessEqual(mock_session.get.call_count, 3)


if __name__ == "__main__":
    unittest.main()
