"""
Tests for pipeline/quality_gate.py — all external calls mocked.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.quality_gate import run_quality_gates, GateResult


SAMPLE_JD = "Looking for a Data Scientist with Python and SQL experience."

SAMPLE_JOB = {
    "title": "Data Scientist",
    "company": "Stripe",
    "url": "https://example.com/job/1",
}

MINIMAL_TEX = r"""
\documentclass{article}
\begin{document}
Data Scientist with Python and SQL experience.
\end{document}
"""


def _make_mock_client(score: float = 91.0):
    """Create a mock Anthropic client that returns a fixed ATS score."""
    import json
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(
        text=json.dumps({"required": ["python", "sql"], "preferred": []})
    )]
    mock_client.messages.create.return_value = mock_message
    return mock_client


class TestRunQualityGates(unittest.TestCase):

    @patch("pipeline.quality_gate.render_preview", return_value="/tmp/preview.jpg")
    @patch("pipeline.quality_gate.score_resume", return_value=91.0)
    @patch("pipeline.quality_gate.get_page_count", return_value=1)
    @patch("pipeline.quality_gate.compile_tex", return_value=(True, "/tmp/resume.pdf", ""))
    def test_all_gates_pass(self, mock_compile, mock_pages, mock_score, mock_preview):
        result = run_quality_gates(MINIMAL_TEX, SAMPLE_JOB, SAMPLE_JD, "/tmp", "test")
        self.assertTrue(result.passed)
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.ats_score, 91.0)
        self.assertEqual(result.page_count, 1)
        self.assertEqual(result.preview_path, "/tmp/preview.jpg")
        self.assertEqual(result.issues, [])

    @patch("pipeline.quality_gate.render_preview", return_value="")
    @patch("pipeline.quality_gate.score_resume", return_value=91.0)
    @patch("pipeline.quality_gate.get_page_count", return_value=1)
    @patch("pipeline.quality_gate.compile_tex", return_value=(False, "", "! Undefined control sequence"))
    def test_compile_failure_returns_immediately(self, mock_compile, mock_pages, mock_score, mock_preview):
        result = run_quality_gates(MINIMAL_TEX, SAMPLE_JOB, SAMPLE_JD, "/tmp", "test")
        self.assertFalse(result.passed)
        self.assertEqual(result.status, "compile_error")
        # Page count and ATS should NOT be called after compile failure
        mock_pages.assert_not_called()
        mock_score.assert_not_called()

    @patch("pipeline.quality_gate.render_preview", return_value="")
    @patch("pipeline.quality_gate.score_resume", return_value=91.0)
    @patch("pipeline.quality_gate.get_page_count", return_value=2)
    @patch("pipeline.quality_gate.compile_tex", return_value=(True, "/tmp/resume.pdf", ""))
    def test_page_count_failure_flagged_in_issues(self, mock_compile, mock_pages, mock_score, mock_preview):
        result = run_quality_gates(MINIMAL_TEX, SAMPLE_JOB, SAMPLE_JD, "/tmp", "test")
        self.assertFalse(result.passed)
        self.assertEqual(result.status, "page_error")
        self.assertTrue(any("page count" in i.lower() for i in result.issues))

    @patch("pipeline.quality_gate.render_preview", return_value="/tmp/preview.jpg")
    @patch("pipeline.quality_gate.score_resume", return_value=72.0)
    @patch("pipeline.quality_gate.get_page_count", return_value=1)
    @patch("pipeline.quality_gate.compile_tex", return_value=(True, "/tmp/resume.pdf", ""))
    def test_low_ats_score_flagged(self, mock_compile, mock_pages, mock_score, mock_preview):
        result = run_quality_gates(MINIMAL_TEX, SAMPLE_JOB, SAMPLE_JD, "/tmp", "test")
        self.assertFalse(result.passed)
        self.assertEqual(result.status, "low_ats")
        self.assertTrue(any("below minimum" in i for i in result.issues))

    @patch("pipeline.quality_gate.render_preview", return_value="/tmp/preview.jpg")
    @patch("pipeline.quality_gate.score_resume", return_value=95.0)
    @patch("pipeline.quality_gate.get_page_count", return_value=1)
    @patch("pipeline.quality_gate.compile_tex", return_value=(True, "/tmp/resume.pdf", ""))
    def test_high_ats_score_flagged_but_not_failed(self, mock_compile, mock_pages, mock_score, mock_preview):
        result = run_quality_gates(MINIMAL_TEX, SAMPLE_JOB, SAMPLE_JD, "/tmp", "test")
        # High ATS is a warning, not a failure — passed should be True
        self.assertTrue(result.passed)
        self.assertEqual(result.status, "high_ats")
        self.assertTrue(any("keyword stuffing" in i for i in result.issues))

    @patch("pipeline.quality_gate.render_preview", return_value="")
    @patch("pipeline.quality_gate.score_resume", return_value=91.0)
    @patch("pipeline.quality_gate.get_page_count", return_value=1)
    @patch("pipeline.quality_gate.compile_tex", return_value=(True, "/tmp/resume.pdf", ""))
    def test_missing_preview_is_warning_not_failure(self, mock_compile, mock_pages, mock_score, mock_preview):
        result = run_quality_gates(MINIMAL_TEX, SAMPLE_JOB, SAMPLE_JD, "/tmp", "test")
        # Should still pass — preview failure is a warning
        self.assertTrue(result.passed)
        self.assertTrue(any("preview" in i.lower() for i in result.issues))

    def test_gate_result_summary(self):
        result = GateResult(
            passed=True,
            pdf_path="/tmp/resume.pdf",
            ats_score=91.0,
            page_count=1,
            preview_path="/tmp/preview.jpg",
            status="ready",
        )
        summary = result.summary()
        self.assertIn("91.0%", summary)
        self.assertIn("ready", summary)


if __name__ == "__main__":
    unittest.main()
