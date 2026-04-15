"""
Tests for pipeline/jd_extractor.py — mocks HTTP to avoid network calls.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.jd_extractor import extract_jd_text, _detect_source, _clean_text, extract_min_years


SAMPLE_GREENHOUSE_HTML = """
<html><body>
<nav>Navigation</nav>
<div id="content">
<h1>Senior Data Scientist</h1>
<p>We are looking for a Senior Data Scientist to join our team at Stripe.</p>
<ul>
  <li>5+ years of experience in machine learning</li>
  <li>Proficiency in Python, SQL, and TensorFlow</li>
  <li>Experience with A/B testing and experimentation</li>
  <li>Strong communication skills and ability to present results</li>
</ul>
<p>Preferred qualifications:</p>
<ul>
  <li>Experience with Spark or distributed computing</li>
  <li>PhD in Statistics, Computer Science, or related field</li>
</ul>
</div>
<footer>Footer content</footer>
</body></html>
"""

SAMPLE_PLAIN_HTML = """
<html><body>
<main>
<h2>Machine Learning Engineer</h2>
<p>Build and deploy production ML models.</p>
<p>Requirements: PyTorch, Python, AWS SageMaker, Docker, Kubernetes.</p>
<p>Nice to have: MLflow, Ray, distributed training experience.</p>
</main>
</body></html>
"""


class TestDetectSource(unittest.TestCase):

    def test_greenhouse_url(self):
        self.assertEqual(_detect_source("https://boards.greenhouse.io/stripe/jobs/12345"), "greenhouse")

    def test_lever_url(self):
        self.assertEqual(_detect_source("https://jobs.lever.co/netflix/abc123"), "lever")

    def test_ashby_url(self):
        self.assertEqual(_detect_source("https://jobs.ashby.com/ramp/data-scientist"), "ashby")

    def test_indeed_url(self):
        self.assertEqual(_detect_source("https://www.indeed.com/viewjob?jk=abc"), "indeed")

    def test_linkedin_url(self):
        self.assertEqual(_detect_source("https://www.linkedin.com/jobs/view/12345"), "linkedin")

    def test_unknown_url_returns_generic(self):
        self.assertEqual(_detect_source("https://careers.example.com/job/123"), "generic")

    def test_bamboohr_url(self):
        self.assertEqual(_detect_source("https://stripe.bamboohr.com/jobs/embed2.php"), "bamboohr")


class TestCleanText(unittest.TestCase):

    def test_strips_script_tags(self):
        html = "<html><body><script>alert('x')</script><p>Job description</p></body></html>"
        text = _clean_text(html)
        self.assertNotIn("alert", text)
        self.assertIn("Job description", text)

    def test_strips_nav_and_footer(self):
        html = "<html><body><nav>Nav</nav><main><p>Content</p></main><footer>Foot</footer></body></html>"
        text = _clean_text(html)
        self.assertNotIn("Nav", text)
        self.assertNotIn("Foot", text)
        self.assertIn("Content", text)

    def test_container_selector(self):
        text = _clean_text(SAMPLE_GREENHOUSE_HTML, "#content")
        self.assertIn("Senior Data Scientist", text)
        # Navigation should not appear
        self.assertNotIn("Navigation", text)

    def test_fallback_when_selector_missing(self):
        # Even if selector doesn't match, should still return text
        text = _clean_text(SAMPLE_PLAIN_HTML, "#nonexistent")
        self.assertIn("Machine Learning Engineer", text)

    def test_normalises_whitespace(self):
        html = "<p>Line 1</p>\n\n\n\n\n<p>Line 2</p>"
        text = _clean_text(html)
        # Should not have more than 2 consecutive newlines
        self.assertNotIn("\n\n\n", text)


class TestExtractJdText(unittest.TestCase):

    @patch("pipeline.jd_extractor._fetch_html")
    def test_extracts_greenhouse_jd(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_GREENHOUSE_HTML
        text = extract_jd_text("https://boards.greenhouse.io/stripe/jobs/12345")
        self.assertIn("Senior Data Scientist", text)
        self.assertIn("Python", text)

    @patch("pipeline.jd_extractor._fetch_html")
    def test_extracts_generic_jd(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_PLAIN_HTML
        text = extract_jd_text("https://careers.example.com/job/123")
        self.assertIn("Machine Learning Engineer", text)

    @patch("pipeline.jd_extractor._fetch_html")
    def test_raises_on_too_short_text(self, mock_fetch):
        mock_fetch.return_value = "<html><body><p>Hi</p></body></html>"
        with self.assertRaises(ValueError):
            extract_jd_text("https://example.com/job/1")

    @patch("pipeline.jd_extractor.requests.get")
    def test_retries_on_connection_error(self, mock_get):
        import requests as req_lib
        mock_get.side_effect = [
            req_lib.ConnectionError("timeout"),
            req_lib.ConnectionError("timeout"),
            req_lib.ConnectionError("timeout"),
        ]
        with self.assertRaises(req_lib.RequestException):
            extract_jd_text("https://example.com/job/fail")


class TestExtractMinYears(unittest.TestCase):

    def test_plus_notation(self):
        jd = "Minimum Requirements:\n- 5+ years of experience in machine learning\n- Python proficiency"
        self.assertEqual(extract_min_years(jd), 5)

    def test_range_returns_lower_bound(self):
        jd = "Required Qualifications:\n- 2-5 years of relevant experience\n- SQL knowledge"
        self.assertEqual(extract_min_years(jd), 2)

    def test_at_least_pattern(self):
        jd = "Requirements:\n- At least 3 years of experience in data science\n- Strong Python skills"
        self.assertEqual(extract_min_years(jd), 3)

    def test_minimum_of_pattern(self):
        jd = "Basic Qualifications:\n- Minimum of 4 years experience with ML frameworks\n- PyTorch"
        self.assertEqual(extract_min_years(jd), 4)

    def test_or_more_pattern(self):
        jd = "Qualifications:\n- 3 or more years of industry experience\n- Deep learning"
        self.assertEqual(extract_min_years(jd), 3)

    def test_years_experience_pattern(self):
        jd = "Requirements:\n- 6 years of experience in applied ML\n- Research background"
        self.assertEqual(extract_min_years(jd), 6)

    def test_returns_minimum_when_multiple_found(self):
        # Multiple requirements sections — returns the smallest lower bound
        jd = (
            "Minimum Requirements:\n- 3+ years of experience\n\n"
            "Preferred Qualifications:\n- 7+ years of experience preferred"
        )
        self.assertEqual(extract_min_years(jd), 3)

    def test_no_yoe_pattern_returns_none(self):
        jd = "We are looking for a talented data scientist to join our team.\nPython and SQL required."
        self.assertIsNone(extract_min_years(jd))

    def test_empty_string_returns_none(self):
        self.assertIsNone(extract_min_years(""))

    def test_none_returns_none(self):
        self.assertIsNone(extract_min_years(None))

    def test_fallback_to_full_text_when_no_section(self):
        # No section header — falls back to whole-text scan
        jd = "We need someone with 4+ years of data science experience and strong SQL skills."
        self.assertEqual(extract_min_years(jd), 4)

    def test_dash_range_with_em_dash(self):
        jd = "Requirements:\n- 3–5 years of relevant experience"
        self.assertEqual(extract_min_years(jd), 3)


if __name__ == "__main__":
    unittest.main()
