"""
Tests for pipeline/latex_compiler.py

pdflatex-dependent tests are skipped when pdflatex is not installed.
"""

import os
import sys
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.latex_compiler import (
    compile_tex,
    get_page_count,
    render_preview,
    sanitise_latex,
    adjust_margin,
    _extract_errors,
    PDFLATEX,
    PDFINFO,
    PDFTOPPM,
)

PDFLATEX_AVAILABLE = shutil.which(PDFLATEX) is not None
PDFINFO_AVAILABLE = shutil.which(PDFINFO) is not None
PDFTOPPM_AVAILABLE = shutil.which(PDFTOPPM) is not None

MINIMAL_VALID_TEX = r"""
\documentclass{article}
\begin{document}
Hello, World!
\end{document}
"""

INVALID_TEX = r"""
\documentclass{article}
\begin{document}
\undefinedcommand{broken}
\end{document}
"""


class TestSanitiseLatex(unittest.TestCase):

    def test_unescaped_percent_is_escaped(self):
        result = sanitise_latex("Score: 95%")
        self.assertIn(r"\%", result)

    def test_already_escaped_percent_not_doubled(self):
        result = sanitise_latex(r"Score: 95\%")
        self.assertEqual(result.count(r"\%"), 1)

    def test_unescaped_ampersand_escaped(self):
        result = sanitise_latex("Python & SQL experience")
        self.assertIn(r"\&", result)

    def test_normal_text_unchanged(self):
        result = sanitise_latex("Hello World")
        self.assertEqual(result, "Hello World")

    def test_negative_vspace_removed(self):
        result = sanitise_latex(r"Some text \vspace{-11pt} more text")
        self.assertNotIn(r"\vspace{-11pt}", result)
        self.assertIn("Some text", result)
        self.assertIn("more text", result)

    def test_negative_vspace_various_units_removed(self):
        for unit in ["-8pt", "-1em", "-0.5cm"]:
            tex = rf"\vspace{{{unit}}}"
            result = sanitise_latex(tex)
            self.assertNotIn(tex, result, f"Should remove \\vspace{{{unit}}}")

    def test_positive_vspace_preserved(self):
        result = sanitise_latex(r"\vspace{5pt}")
        self.assertIn(r"\vspace{5pt}", result)

    def test_multiple_negative_vspaces_all_removed(self):
        tex = r"line1 \vspace{-11pt} \\ \vspace{-8pt} line2"
        result = sanitise_latex(tex)
        self.assertNotIn("-11pt", result)
        self.assertNotIn("-8pt", result)


class TestAdjustMargin(unittest.TestCase):

    BASE_TEX = r"\usepackage[a4paper,margin=0.28in]{geometry}"

    def test_replaces_margin_value(self):
        result = adjust_margin(self.BASE_TEX, 0.22)
        self.assertIn("margin=0.22in", result)
        self.assertNotIn("margin=0.28in", result)

    def test_clamps_below_minimum(self):
        result = adjust_margin(self.BASE_TEX, 0.10)
        self.assertIn("margin=0.2in", result)

    def test_clamps_above_maximum(self):
        result = adjust_margin(self.BASE_TEX, 0.50)
        self.assertIn("margin=0.28in", result)

    def test_preserves_a4paper(self):
        result = adjust_margin(self.BASE_TEX, 0.22)
        self.assertIn("a4paper", result)


class TestExtractErrors(unittest.TestCase):

    def test_extracts_bang_lines(self):
        log = "Some output\n! Undefined control sequence.\n\\mycommand"
        errors = _extract_errors(log)
        self.assertIn("! Undefined control sequence", errors)

    def test_empty_log_returns_tail(self):
        log = "a" * 3000
        errors = _extract_errors(log)
        self.assertLessEqual(len(errors), 2001)

    def test_no_errors_returns_tail(self):
        log = "Normal pdflatex output\nCompiling...\nDone."
        errors = _extract_errors(log)
        # Should return the tail since no error lines found
        self.assertIsInstance(errors, str)


@unittest.skipUnless(PDFLATEX_AVAILABLE, "pdflatex not installed — skipping compile tests")
class TestCompileTex(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_valid_tex_compiles_successfully(self):
        success, pdf_path, error_log = compile_tex(MINIMAL_VALID_TEX, self.tmpdir, "test_valid")
        self.assertTrue(success, f"Compile failed: {error_log}")
        self.assertTrue(os.path.exists(pdf_path))
        self.assertEqual(error_log, "")

    def test_invalid_tex_returns_failure(self):
        success, pdf_path, error_log = compile_tex(INVALID_TEX, self.tmpdir, "test_invalid")
        self.assertFalse(success)
        self.assertEqual(pdf_path, "")
        self.assertGreater(len(error_log), 0)

    def test_output_file_is_pdf(self):
        success, pdf_path, _ = compile_tex(MINIMAL_VALID_TEX, self.tmpdir, "test_pdf_ext")
        self.assertTrue(success)
        self.assertTrue(pdf_path.endswith(".pdf"))


@unittest.skipUnless(PDFLATEX_AVAILABLE and PDFINFO_AVAILABLE, "pdflatex/pdfinfo not installed")
class TestGetPageCount(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_single_page_document(self):
        _, pdf_path, _ = compile_tex(MINIMAL_VALID_TEX, self.tmpdir, "pagecount_test")
        pages = get_page_count(pdf_path)
        self.assertEqual(pages, 1)

    def test_nonexistent_file_returns_minus_one(self):
        pages = get_page_count("/nonexistent/file.pdf")
        self.assertEqual(pages, -1)


@unittest.skipUnless(PDFLATEX_AVAILABLE and PDFTOPPM_AVAILABLE, "pdflatex/pdftoppm not installed")
class TestRenderPreview(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_renders_jpeg_preview(self):
        _, pdf_path, _ = compile_tex(MINIMAL_VALID_TEX, self.tmpdir, "preview_test")
        jpeg_path = render_preview(pdf_path)
        self.assertTrue(os.path.exists(jpeg_path), f"JPEG not found: {jpeg_path}")
        self.assertTrue(jpeg_path.endswith(".jpg"))

    def test_nonexistent_pdf_returns_empty(self):
        result = render_preview("/nonexistent/file.pdf")
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
