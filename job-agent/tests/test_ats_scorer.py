"""
Tests for pipeline/ats_scorer.py

Claude API calls are mocked throughout.
pdftotext-dependent tests are skipped if pdftotext is not installed.
"""

import os
import sys
import shutil
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.ats_scorer import (
    extract_keywords,
    score_resume,
    get_missing_keywords,
    _keyword_matches,
    extract_pdf_text,
    PDFTEXTRACT_BIN,
)

PDFTOTEXT_AVAILABLE = shutil.which(PDFTEXTRACT_BIN) is not None

SAMPLE_JD = """
We are looking for a Senior Data Scientist.

Required:
- 5+ years Python experience
- SQL and data modelling
- Machine learning (PyTorch or TensorFlow)
- A/B testing and statistical analysis
- Experience with AWS or GCP

Preferred:
- Experience with Spark or distributed computing
- PhD in Statistics or Computer Science
- Knowledge of MLflow or similar experiment tracking
"""

SAMPLE_RESUME_TEXT = """
Aadarsh Praveen — Data Scientist

Skills: Python, SQL, TensorFlow, AWS, A/B testing, machine learning

Experience:
- Designed and deployed ML pipelines using Python and TensorFlow
- Ran A/B tests on 10M+ users, improving retention by 12%
- Queried data using SQL with complex joins and window functions
"""


class TestKeywordMatches(unittest.TestCase):

    def test_exact_match(self):
        self.assertTrue(_keyword_matches("experience with python and sql", "python"))

    def test_multi_word_partial_match(self):
        # "google bigquery" should match if "bigquery" is in text
        self.assertTrue(_keyword_matches("we use bigquery for analytics", "google bigquery"))

    def test_no_match(self):
        self.assertFalse(_keyword_matches("experience with java and scala", "python"))

    def test_case_insensitive(self):
        self.assertTrue(_keyword_matches("PYTORCH is required", "pytorch"))

    def test_empty_keyword(self):
        self.assertFalse(_keyword_matches("python sql", ""))


class TestExtractKeywords(unittest.TestCase):

    def _make_mock_client(self, json_response: str):
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=json_response)]
        mock_client.messages.create.return_value = mock_message
        return mock_client

    def test_valid_json_response(self):
        json_resp = '{"required": ["Python", "SQL"], "preferred": ["Spark", "PhD"]}'
        client = self._make_mock_client(json_resp)
        result = extract_keywords("some jd text", client)
        self.assertEqual(result["required"], ["python", "sql"])
        self.assertEqual(result["preferred"], ["spark", "phd"])

    def test_json_wrapped_in_markdown(self):
        json_resp = '```json\n{"required": ["Python"], "preferred": []}\n```'
        client = self._make_mock_client(json_resp)
        result = extract_keywords("jd text", client)
        self.assertEqual(result["required"], ["python"])

    def test_malformed_json_returns_empty(self):
        client = self._make_mock_client("not valid json at all")
        result = extract_keywords("jd text", client)
        self.assertEqual(result["required"], [])
        self.assertEqual(result["preferred"], [])

    def test_keywords_normalised_to_lowercase(self):
        json_resp = '{"required": ["PyTorch", "AWS"], "preferred": ["MLflow"]}'
        client = self._make_mock_client(json_resp)
        result = extract_keywords("jd text", client)
        self.assertIn("pytorch", result["required"])
        self.assertIn("mlflow", result["preferred"])


class TestScoreResume(unittest.TestCase):

    def _make_mock_client(self, required: list, preferred: list):
        mock_client = MagicMock()
        mock_message = MagicMock()
        import json
        mock_message.content = [MagicMock(
            text=json.dumps({"required": required, "preferred": preferred})
        )]
        mock_client.messages.create.return_value = mock_message
        return mock_client

    @patch("pipeline.ats_scorer.extract_pdf_text")
    def test_perfect_score_all_keywords_present(self, mock_extract):
        mock_extract.return_value = "python sql tensorflow aws a/b testing machine learning"
        client = self._make_mock_client(
            ["python", "sql", "tensorflow", "aws"],
            ["spark"]
        )
        # spark is missing → preferred_found=0, preferred_total=1
        # required: 4/4 → 8/9 ≈ 88.9
        score = score_resume("/fake/path.pdf", SAMPLE_JD, client)
        self.assertGreater(score, 85)

    @patch("pipeline.ats_scorer.extract_pdf_text")
    def test_zero_score_no_keywords_present(self, mock_extract):
        mock_extract.return_value = "marketing sales accounting"
        client = self._make_mock_client(
            ["python", "sql", "tensorflow"],
            ["spark", "phd"]
        )
        score = score_resume("/fake/path.pdf", SAMPLE_JD, client)
        self.assertEqual(score, 0.0)

    @patch("pipeline.ats_scorer.extract_pdf_text")
    def test_empty_pdf_text_returns_zero(self, mock_extract):
        mock_extract.return_value = ""
        client = self._make_mock_client(["python"], [])
        score = score_resume("/fake/path.pdf", SAMPLE_JD, client)
        self.assertEqual(score, 0.0)

    @patch("pipeline.ats_scorer.extract_pdf_text")
    def test_weighted_formula_required_counts_double(self, mock_extract):
        # required: [A, B], preferred: [C]
        # If only A found: numerator=2, denominator=2*2+1=5 → 40%
        mock_extract.return_value = "skill_a"
        client = self._make_mock_client(["skill_a", "skill_b"], ["skill_c"])
        score = score_resume("/fake/path.pdf", "jd", client)
        self.assertAlmostEqual(score, 40.0, places=0)

    @patch("pipeline.ats_scorer.extract_pdf_text")
    def test_no_keywords_returns_zero(self, mock_extract):
        mock_extract.return_value = "some text"
        client = self._make_mock_client([], [])
        score = score_resume("/fake/path.pdf", "jd", client)
        self.assertEqual(score, 0.0)


class TestGetMissingKeywords(unittest.TestCase):

    @patch("pipeline.ats_scorer.extract_pdf_text")
    @patch("pipeline.ats_scorer.extract_keywords")
    def test_identifies_missing_required_keywords(self, mock_extract_kw, mock_pdf):
        mock_pdf.return_value = "python sql experience"
        mock_extract_kw.return_value = {
            "required": ["python", "sql", "pytorch"],
            "preferred": ["spark"],
        }
        missing = get_missing_keywords("/fake.pdf", "jd")
        # pytorch and spark should be missing
        self.assertTrue(any("pytorch" in m for m in missing))
        self.assertTrue(any("spark" in m for m in missing))

    @patch("pipeline.ats_scorer.extract_pdf_text")
    @patch("pipeline.ats_scorer.extract_keywords")
    def test_required_keywords_tagged(self, mock_extract_kw, mock_pdf):
        mock_pdf.return_value = "python"
        mock_extract_kw.return_value = {
            "required": ["pytorch"],
            "preferred": [],
        }
        missing = get_missing_keywords("/fake.pdf", "jd")
        self.assertTrue(missing[0].startswith("[REQUIRED]"))

    @patch("pipeline.ats_scorer.extract_pdf_text")
    @patch("pipeline.ats_scorer.extract_keywords")
    def test_no_missing_when_all_present(self, mock_extract_kw, mock_pdf):
        mock_pdf.return_value = "python sql pytorch spark"
        mock_extract_kw.return_value = {
            "required": ["python", "sql"],
            "preferred": ["spark"],
        }
        missing = get_missing_keywords("/fake.pdf", "jd")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
