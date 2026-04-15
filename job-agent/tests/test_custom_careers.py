"""
Tests for sources/custom_careers.py — mocks HTTP to avoid network calls.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sources.custom_careers import (
    _fetch_google,
    _fetch_meta,
    _fetch_microsoft,
    _fetch_amazon,
    fetch_custom_career_jobs,
    _is_relevant,
)


# ── Fixture responses ─────────────────────────────────────────────────────────

GOOGLE_RESPONSE = {
    "jobs": [
        {
            "title": "Senior Data Scientist",
            "apply_url": "https://careers.google.com/jobs/results/12345",
            "locations": [{"display": "Mountain View, CA"}],
            "description": "Build ML models to improve Google Search.",
        },
        {
            "title": "VP of Engineering",
            "apply_url": "https://careers.google.com/jobs/results/99999",
            "locations": [{"display": "Mountain View, CA"}],
            "description": "Lead engineering organisation.",
        },
    ]
}

META_RESPONSE = {
    "data": {
        "job_postings": {
            "count": 2,
            "edges": [
                {
                    "node": {
                        "id": "123",
                        "title": "Machine Learning Engineer",
                        "locations": [{"name": "Menlo Park, CA"}],
                        "url": "https://www.metacareers.com/jobs/123",
                    }
                },
                {
                    "node": {
                        "id": "456",
                        "title": "Director of AI",
                        "locations": [{"name": "New York, NY"}],
                        "url": "https://www.metacareers.com/jobs/456",
                    }
                },
            ],
        }
    }
}

MICROSOFT_RESPONSE = {
    "operationResult": {
        "result": {
            "jobs": [
                {
                    "title": "Applied Scientist",
                    "jobId": "MS12345",
                    "primaryWorkLocation": "Redmond, WA",
                    "descriptionTeaser": "Work on Azure ML platform with distributed training.",
                    "postingDate": "2024-04-01",
                },
                {
                    "title": "Data Analyst",
                    "jobId": "MS99999",
                    "primaryWorkLocation": "Redmond, WA",
                    "descriptionTeaser": "Analyse business data for reporting.",
                    "postingDate": "2024-04-01",
                },
            ]
        }
    }
}

AMAZON_RESPONSE = {
    "jobs": [
        {
            "title": "Research Scientist, NLP",
            "job_path": "/en/jobs/2345678",
            "location": "Seattle, WA",
            "description": "NLP research for Alexa language understanding.",
            "updated_time": "2024-04-01",
        },
        {
            "title": "Business Analyst",
            "job_path": "/en/jobs/9999999",
            "location": "Seattle, WA",
            "description": "Analyse retail data for the consumer team.",
            "updated_time": "2024-04-01",
        },
    ]
}


# ── _is_relevant ──────────────────────────────────────────────────────────────

class TestIsRelevant(unittest.TestCase):

    def test_data_scientist_relevant(self):
        self.assertTrue(_is_relevant("Senior Data Scientist"))

    def test_machine_learning_in_title_relevant(self):
        self.assertTrue(_is_relevant("Machine Learning Engineer"))

    def test_nlp_in_description_relevant(self):
        self.assertTrue(_is_relevant("Research Scientist", "NLP and language modelling"))

    def test_vp_excluded(self):
        self.assertFalse(_is_relevant("VP of Engineering"))

    def test_director_excluded(self):
        self.assertFalse(_is_relevant("Director of AI"))

    def test_data_analyst_excluded(self):
        self.assertFalse(_is_relevant("Data Analyst"))

    def test_business_analyst_excluded(self):
        self.assertFalse(_is_relevant("Business Analyst"))

    def test_data_engineer_excluded(self):
        self.assertFalse(_is_relevant("Data Engineer"))

    def test_unrelated_role_not_relevant(self):
        self.assertFalse(_is_relevant("Product Manager"))


# ── Google ────────────────────────────────────────────────────────────────────

class TestFetchGoogle(unittest.TestCase):

    @patch("sources.custom_careers.requests.get")
    def test_returns_relevant_jobs(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = GOOGLE_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        jobs = _fetch_google(["data scientist"])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Data Scientist")
        self.assertEqual(jobs[0]["company"], "Google")
        self.assertEqual(jobs[0]["source"], "google_careers")
        self.assertEqual(jobs[0]["location"], "Mountain View, CA")

    @patch("sources.custom_careers.requests.get")
    def test_filters_vp_title(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = GOOGLE_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        jobs = _fetch_google(["data scientist"])
        titles = [j["title"] for j in jobs]
        self.assertNotIn("VP of Engineering", titles)

    @patch("sources.custom_careers.requests.get")
    def test_handles_403_blocked(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_get.return_value = mock_resp

        jobs = _fetch_google(["data scientist"])
        self.assertEqual(jobs, [])

    @patch("sources.custom_careers.requests.get")
    def test_handles_429_rate_limited(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_get.return_value = mock_resp

        jobs = _fetch_google(["data scientist"])
        self.assertEqual(jobs, [])

    @patch("sources.custom_careers.requests.get")
    def test_deduplicates_across_search_terms(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = GOOGLE_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        # Same response returned for two terms — apply_url is the same
        jobs = _fetch_google(["data scientist", "machine learning"])
        urls = [j["url"] for j in jobs]
        self.assertEqual(len(urls), len(set(urls)))

    @patch("sources.custom_careers.requests.get")
    def test_handles_network_error(self, mock_get):
        import requests as req_lib
        mock_get.side_effect = req_lib.ConnectionError("timeout")

        jobs = _fetch_google(["data scientist"])
        self.assertEqual(jobs, [])


# ── Meta ──────────────────────────────────────────────────────────────────────

class TestFetchMeta(unittest.TestCase):

    @patch("sources.custom_careers.requests.post")
    def test_returns_relevant_jobs(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = META_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        jobs = _fetch_meta(["machine learning"])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Machine Learning Engineer")
        self.assertEqual(jobs[0]["company"], "Meta")
        self.assertEqual(jobs[0]["source"], "meta_careers")

    @patch("sources.custom_careers.requests.post")
    def test_filters_director_title(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = META_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        jobs = _fetch_meta(["machine learning"])
        titles = [j["title"] for j in jobs]
        self.assertNotIn("Director of AI", titles)

    @patch("sources.custom_careers.requests.post")
    def test_handles_429(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_post.return_value = mock_resp

        jobs = _fetch_meta(["machine learning"])
        self.assertEqual(jobs, [])

    @patch("sources.custom_careers.requests.post")
    def test_extracts_location(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = META_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        jobs = _fetch_meta(["machine learning"])
        self.assertEqual(jobs[0]["location"], "Menlo Park, CA")


# ── Microsoft ─────────────────────────────────────────────────────────────────

class TestFetchMicrosoft(unittest.TestCase):

    @patch("sources.custom_careers.requests.get")
    def test_returns_relevant_jobs(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MICROSOFT_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        jobs = _fetch_microsoft(["applied scientist"])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Applied Scientist")
        self.assertEqual(jobs[0]["company"], "Microsoft")
        self.assertEqual(jobs[0]["source"], "microsoft_careers")

    @patch("sources.custom_careers.requests.get")
    def test_filters_data_analyst(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MICROSOFT_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        jobs = _fetch_microsoft(["applied scientist"])
        titles = [j["title"] for j in jobs]
        self.assertNotIn("Data Analyst", titles)

    @patch("sources.custom_careers.requests.get")
    def test_constructs_correct_url(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MICROSOFT_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        jobs = _fetch_microsoft(["applied scientist"])
        self.assertIn("careers.microsoft.com", jobs[0]["url"])
        self.assertIn("MS12345", jobs[0]["url"])

    @patch("sources.custom_careers.requests.get")
    def test_includes_posted_date(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MICROSOFT_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        jobs = _fetch_microsoft(["applied scientist"])
        self.assertEqual(jobs[0]["posted_date"], "2024-04-01")


# ── Amazon ────────────────────────────────────────────────────────────────────

class TestFetchAmazon(unittest.TestCase):

    @patch("sources.custom_careers.requests.get")
    def test_returns_relevant_jobs(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = AMAZON_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        jobs = _fetch_amazon(["research scientist"])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Research Scientist, NLP")
        self.assertEqual(jobs[0]["company"], "Amazon")
        self.assertEqual(jobs[0]["source"], "amazon_jobs")

    @patch("sources.custom_careers.requests.get")
    def test_filters_business_analyst(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = AMAZON_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        jobs = _fetch_amazon(["research scientist"])
        titles = [j["title"] for j in jobs]
        self.assertNotIn("Business Analyst", titles)

    @patch("sources.custom_careers.requests.get")
    def test_constructs_correct_url(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = AMAZON_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        jobs = _fetch_amazon(["research scientist"])
        self.assertEqual(jobs[0]["url"], "https://www.amazon.jobs/en/jobs/2345678")

    @patch("sources.custom_careers.requests.get")
    def test_includes_posted_date(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = AMAZON_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        jobs = _fetch_amazon(["research scientist"])
        self.assertEqual(jobs[0]["posted_date"], "2024-04-01")

    @patch("sources.custom_careers.requests.get")
    def test_handles_network_error(self, mock_get):
        import requests as req_lib
        mock_get.side_effect = req_lib.ConnectionError("timeout")

        jobs = _fetch_amazon(["research scientist"])
        self.assertEqual(jobs, [])


# ── Dispatcher ────────────────────────────────────────────────────────────────

class TestFetchCustomCareerJobs(unittest.TestCase):

    def test_dispatches_to_correct_fetchers(self):
        mock_google = MagicMock(return_value=[{"title": "Data Scientist", "company": "Google"}])
        mock_meta = MagicMock(return_value=[{"title": "ML Engineer", "company": "Meta"}])
        with patch.dict("sources.custom_careers._FETCHERS", {"google": mock_google, "meta": mock_meta}):
            jobs = fetch_custom_career_jobs(["google", "meta"])
        self.assertEqual(len(jobs), 2)
        mock_google.assert_called_once()
        mock_meta.assert_called_once()

    def test_unknown_company_key_skipped(self):
        # Should not raise — just log a warning and skip
        jobs = fetch_custom_career_jobs(["unknown_company_xyz"])
        self.assertEqual(jobs, [])

    def test_case_insensitive_company_key(self):
        mock_ms = MagicMock(return_value=[])
        with patch.dict("sources.custom_careers._FETCHERS", {"microsoft": mock_ms}):
            fetch_custom_career_jobs(["Microsoft"])
        mock_ms.assert_called_once()

    def test_single_company(self):
        mock_amazon = MagicMock(return_value=[
            {"title": "Research Scientist", "company": "Amazon", "url": "https://amazon.jobs/1",
             "location": "Seattle", "jd_text": "", "source": "amazon_jobs", "posted_date": ""}
        ])
        with patch.dict("sources.custom_careers._FETCHERS", {"amazon": mock_amazon}):
            jobs = fetch_custom_career_jobs(["amazon"])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Amazon")

    def test_exception_in_fetcher_does_not_halt_others(self):
        mock_google = MagicMock(side_effect=Exception("API down"))
        with patch.dict("sources.custom_careers._FETCHERS", {"google": mock_google}):
            # Should not raise — error is caught per company
            jobs = fetch_custom_career_jobs(["google"])
        self.assertIsInstance(jobs, list)


if __name__ == "__main__":
    unittest.main()
