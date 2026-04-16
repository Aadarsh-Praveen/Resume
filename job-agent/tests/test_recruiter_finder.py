"""
Tests for outputs/recruiter_finder.py — all HTTP calls mocked.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from outputs.recruiter_finder import (
    _extract_domain,
    _hunter_domain_search,
    _extract_hunter_contact,
    find_recruiter,
)


# ── _extract_domain ────────────────────────────────────────────────────────────

class TestExtractDomain(unittest.TestCase):

    def test_strips_careers_subdomain(self):
        self.assertEqual(_extract_domain("https://careers.stripe.com/jobs/123", "Stripe"), "stripe.com")

    def test_strips_jobs_subdomain(self):
        self.assertEqual(_extract_domain("https://jobs.example.com/apply", "Example"), "example.com")

    def test_greenhouse_url_extracts_slug(self):
        domain = _extract_domain("https://boards.greenhouse.io/stripe/jobs/123", "Stripe")
        self.assertEqual(domain, "stripe.com")

    def test_lever_url_extracts_slug(self):
        domain = _extract_domain("https://jobs.lever.co/netflix/abc123", "Netflix")
        self.assertEqual(domain, "netflix.com")

    def test_fallback_to_company_name(self):
        domain = _extract_domain("", "OpenAI")
        self.assertEqual(domain, "openai.com")

    def test_company_name_sanitised(self):
        domain = _extract_domain("", "Scale AI")
        self.assertEqual(domain, "scaleai.com")

    def test_direct_company_url(self):
        domain = _extract_domain("https://www.anthropic.com/careers/123", "Anthropic")
        self.assertEqual(domain, "www.anthropic.com")


# ── _extract_hunter_contact ────────────────────────────────────────────────────

class TestExtractHunterContact(unittest.TestCase):

    def test_extracts_all_fields(self):
        entry = {
            "first_name": "Jane",
            "last_name": "Smith",
            "position": "Technical Recruiter",
            "value": "jane.smith@stripe.com",
            "linkedin": "https://linkedin.com/in/janesmith",
            "confidence": 95,
        }
        contact = _extract_hunter_contact(entry, "stripe.com")
        self.assertEqual(contact["name"], "Jane Smith")
        self.assertEqual(contact["title"], "Technical Recruiter")
        self.assertEqual(contact["email"], "jane.smith@stripe.com")
        self.assertEqual(contact["linkedin_url"], "https://linkedin.com/in/janesmith")
        self.assertEqual(contact["company"], "stripe.com")

    def test_handles_missing_fields(self):
        entry = {"value": "someone@company.com"}
        contact = _extract_hunter_contact(entry, "company.com")
        self.assertEqual(contact["name"], "")
        self.assertEqual(contact["title"], "")
        self.assertEqual(contact["linkedin_url"], "")


# ── _hunter_domain_search ──────────────────────────────────────────────────────

class TestHunterDomainSearch(unittest.TestCase):

    def _make_response(self, emails):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"emails": emails}}
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    @patch("outputs.recruiter_finder.requests.get")
    def test_prefers_recruiter_by_position(self, mock_get):
        emails = [
            {"first_name": "Bob", "last_name": "Jones", "position": "Software Engineer",
             "value": "bob@co.com", "linkedin": "", "confidence": 90},
            {"first_name": "Alice", "last_name": "Doe", "position": "Technical Recruiter",
             "value": "alice@co.com", "linkedin": "", "confidence": 70},
        ]
        mock_get.return_value = self._make_response(emails)

        contact = _hunter_domain_search("co.com", "test-key")
        self.assertEqual(contact["email"], "alice@co.com")

    @patch("outputs.recruiter_finder.requests.get")
    def test_falls_back_to_highest_confidence(self, mock_get):
        emails = [
            {"first_name": "A", "last_name": "B", "position": "Engineer",
             "value": "a@co.com", "linkedin": "", "confidence": 60},
            {"first_name": "C", "last_name": "D", "position": "Manager",
             "value": "c@co.com", "linkedin": "", "confidence": 95},
        ]
        mock_get.return_value = self._make_response(emails)

        contact = _hunter_domain_search("co.com", "test-key")
        self.assertEqual(contact["email"], "c@co.com")

    @patch("outputs.recruiter_finder.requests.get")
    def test_returns_none_for_empty_results(self, mock_get):
        mock_get.return_value = self._make_response([])
        result = _hunter_domain_search("co.com", "test-key")
        self.assertIsNone(result)

    @patch("outputs.recruiter_finder.requests.get")
    def test_returns_none_on_401(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp
        result = _hunter_domain_search("co.com", "bad-key")
        self.assertIsNone(result)

    @patch("outputs.recruiter_finder.requests.get")
    def test_returns_none_on_429(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_get.return_value = mock_resp
        result = _hunter_domain_search("co.com", "test-key")
        self.assertIsNone(result)

    @patch("outputs.recruiter_finder.requests.get")
    def test_returns_none_on_network_error(self, mock_get):
        import requests as req_lib
        mock_get.side_effect = req_lib.ConnectionError("timeout")
        result = _hunter_domain_search("co.com", "test-key")
        self.assertIsNone(result)


# ── find_recruiter ─────────────────────────────────────────────────────────────

class TestFindRecruiter(unittest.TestCase):

    @patch("outputs.recruiter_finder._hunter_domain_search")
    def test_returns_contact_when_found(self, mock_search):
        mock_search.return_value = {
            "name": "Jane Smith", "title": "Recruiter",
            "email": "jane@stripe.com", "linkedin_url": "", "company": "stripe.com",
        }
        contact = find_recruiter("Stripe", "Data Scientist", "https://boards.greenhouse.io/stripe", "key")
        self.assertIsNotNone(contact)
        self.assertEqual(contact["email"], "jane@stripe.com")

    @patch("outputs.recruiter_finder._hunter_domain_search")
    def test_returns_none_when_not_found(self, mock_search):
        mock_search.return_value = None
        result = find_recruiter("Unknown Co", "DS", "", "key")
        self.assertIsNone(result)

    def test_returns_none_when_no_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("HUNTER_API_KEY", None)
            result = find_recruiter("Stripe", "DS", "https://stripe.com", api_key="")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
