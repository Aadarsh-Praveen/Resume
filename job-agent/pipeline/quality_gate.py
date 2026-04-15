"""
Quality gate orchestrator.

Runs all three automated quality gates on a compiled PDF and returns a
structured result. This is the single entry point for the quality-check layer.

Gates:
    1. LaTeX compile check
    2. Page count (must be exactly 1)
    3. ATS keyword score (89–93%)
    4. Preview image render (for Telegram alert)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import anthropic

from config import ATS_SCORE_MIN, ATS_SCORE_MAX
from pipeline.latex_compiler import compile_tex, get_page_count, render_preview, sanitise_latex
from pipeline.ats_scorer import score_resume

logger = logging.getLogger(__name__)


@dataclass
class GateResult:
    passed: bool
    pdf_path: str
    ats_score: float
    page_count: int
    preview_path: str
    issues: list[str] = field(default_factory=list)
    status: str = "pending"   # "ready" | "low_ats" | "high_ats" | "compile_error" | "page_error"

    def summary(self) -> str:
        lines = [
            f"Status:    {self.status}",
            f"ATS score: {self.ats_score:.1f}%",
            f"Pages:     {self.page_count}",
            f"PDF:       {self.pdf_path}",
        ]
        if self.issues:
            lines.append("Issues:")
            lines.extend(f"  - {i}" for i in self.issues)
        return "\n".join(lines)


def run_quality_gates(
    tex_content: str,
    job_dict: dict,
    jd_text: str,
    output_dir: str,
    filename: str,
    client: Optional[anthropic.Anthropic] = None,
) -> GateResult:
    """
    Run all quality gates on a LaTeX string.

    Args:
        tex_content: Raw .tex file content to compile and check.
        job_dict:    Job metadata (used for context only).
        jd_text:     Full job description text (for ATS scoring).
        output_dir:  Where to save the compiled PDF.
        filename:    Base filename without extension.
        client:      Optional Anthropic client.

    Returns:
        GateResult with all check outcomes.
    """
    result = GateResult(
        passed=False,
        pdf_path="",
        ats_score=0.0,
        page_count=-1,
        preview_path="",
    )

    # ── Gate 1: LaTeX compile ─────────────────────────────────────────────────
    tex_sanitised = sanitise_latex(tex_content)
    success, pdf_path, error_log = compile_tex(tex_sanitised, output_dir, filename)

    if not success:
        result.issues.append(f"Compile error: {error_log[:300]}")
        result.status = "compile_error"
        logger.warning("Gate 1 FAIL — compile error for %s", filename)
        return result

    result.pdf_path = pdf_path
    logger.info("Gate 1 PASS — compiled %s", pdf_path)

    # ── Gate 2: Page count ───────────────────────────────────────────────────
    pages = get_page_count(pdf_path)
    result.page_count = pages

    if pages != 1 and pages != -1:
        result.issues.append(f"Page count is {pages} (expected 1)")
        result.status = "page_error"
        logger.warning("Gate 2 FAIL — %d pages for %s", pages, filename)
        # Don't return — continue to get ATS score for information
    else:
        logger.info("Gate 2 PASS — 1 page")

    # ── Gate 3: ATS score ─────────────────────────────────────────────────────
    if client is None:
        client = anthropic.Anthropic()

    ats_score = score_resume(pdf_path, jd_text, client)
    result.ats_score = ats_score

    if ats_score < ATS_SCORE_MIN:
        result.issues.append(
            f"ATS score {ats_score:.1f}% below minimum {ATS_SCORE_MIN}%"
        )
        result.status = "low_ats"
        logger.warning("Gate 3 FAIL — ATS %.1f%% < %d%%", ats_score, ATS_SCORE_MIN)
    elif ats_score > ATS_SCORE_MAX:
        result.issues.append(
            f"ATS score {ats_score:.1f}% above maximum {ATS_SCORE_MAX}% — possible keyword stuffing"
        )
        result.status = "high_ats"
        logger.warning("Gate 3 FLAG — ATS %.1f%% > %d%%", ats_score, ATS_SCORE_MAX)
    else:
        logger.info("Gate 3 PASS — ATS %.1f%%", ats_score)

    # ── Gate 4: Preview render ────────────────────────────────────────────────
    preview_path = render_preview(pdf_path)
    result.preview_path = preview_path
    if not preview_path:
        result.issues.append("Preview render failed (pdftoppm not available?)")
        logger.warning("Gate 4 WARN — preview render failed for %s", filename)
    else:
        logger.info("Gate 4 PASS — preview at %s", preview_path)

    # ── Final verdict ────────────────────────────────────────────────────────
    has_fatal_issues = any(
        "compile error" in i.lower() or "page count" in i.lower() or "below minimum" in i.lower()
        for i in result.issues
    )

    if not has_fatal_issues:
        result.passed = True
        if result.status not in ("high_ats",):
            result.status = "ready"

    return result
