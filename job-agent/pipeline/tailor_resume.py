"""
Core resume tailoring pipeline.

Takes a job dict + JD text, sends the base resume .tex and JD to Claude,
runs quality gates (compile → page count → ATS score), and saves the PDF.

Usage:
    from pipeline.tailor_resume import tailor_resume
    pdf_path = tailor_resume(job_id=42, job_dict=job, jd_text=jd)
"""

import os
import re
import logging
from pathlib import Path
from typing import Optional

import anthropic

from config import (
    TAILOR_SYSTEM_PROMPT,
    ATS_SCORE_MIN,
    ATS_SCORE_MAX,
    MAX_RETRIES,
    MAX_PAGE_RETRIES,
)
from pipeline.latex_compiler import compile_tex, get_page_count, get_fill_percentage, sanitise_latex
from pipeline.ats_scorer import score_resume, get_missing_keywords

logger = logging.getLogger(__name__)

BASE_RESUME_PATH = os.getenv("BASE_RESUME_PATH", "base_resume.tex")
RESUMES_DIR = os.getenv("RESUMES_DIR", "resumes")


def load_base_resume() -> str:
    """Load the master base_resume.tex from disk."""
    path = Path(BASE_RESUME_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"base_resume.tex not found at {path.resolve()}. "
            "Export your Overleaf template and place it here."
        )
    return path.read_text(encoding="utf-8")


def _extract_tex(response_text: str) -> str:
    """
    Extract .tex content from Claude's response.

    Handles:
    - Raw .tex (no fences)
    - ```latex...``` or ```tex...``` or ``` ``` blocks (anywhere in the response)
    - Leading/trailing explanation text
    """
    text = response_text.strip()

    # Try to find content inside a markdown code fence (anywhere in the response)
    fence_match = re.search(r"```(?:latex|tex)?\s*\n([\s\S]+?)\n```", text)
    if fence_match:
        return fence_match.group(1).strip()

    # No fences — find the start of actual LaTeX content (\documentclass or \begin{document})
    doc_match = re.search(r"(\\documentclass[\s\S]+)", text)
    if doc_match:
        return doc_match.group(1).strip()

    # Fallback: return as-is
    return text


def _build_tailoring_prompt(base_tex: str, jd_text: str) -> str:
    return (
        f"Tailor this LaTeX resume for the following job description.\n\n"
        f"=== JOB DESCRIPTION ===\n{jd_text[:5000]}\n\n"
        f"=== CURRENT RESUME (.tex) ===\n{base_tex}\n\n"
        f"Return ONLY the complete tailored .tex file — no explanations."
    )


def _build_fix_compile_prompt(broken_tex: str, error_log: str) -> str:
    return (
        f"The following LaTeX resume failed to compile with pdflatex.\n\n"
        f"=== COMPILE ERROR ===\n{error_log[:2000]}\n\n"
        f"=== BROKEN .TEX ===\n{broken_tex}\n\n"
        f"Fix ONLY the LaTeX error. Return the complete corrected .tex file and nothing else."
    )


def _build_expand_prompt(sparse_tex: str, fill_pct: int) -> str:
    return (
        f"This resume is only ~{fill_pct}% full — it must fill the ENTIRE page.\n\n"
        f"Add content back from the original resume to fill the page:\n"
        f"1. Expand most recent role to 4 bullets (pick the most JD-relevant from the original)\n"
        f"2. Expand second role to 3–4 bullets\n"
        f"3. Expand oldest role to 3 bullets\n"
        f"4. Add a 3rd bullet to each project (must be metric-driven, 20–28 words)\n"
        f"5. Expand summary to 3 full sentences (4 lines)\n"
        f"6. Add more tools per skill category (up to 8 each)\n\n"
        f"Every bullet: 20–28 words, [OUTCOME + METRIC] by [HOW YOU DID IT].\n"
        f"Do NOT add blank lines or \\\\vspace to fill — add real content only.\n"
        f"Do NOT use negative \\\\vspace anywhere.\n"
        f"Return ONLY the complete .tex file.\n\n"
        f"=== CURRENT .TEX ===\n{sparse_tex}"
    )


def _build_trim_prompt(long_tex: str, page_count: int) -> str:
    return (
        f"This resume compiled to {page_count} pages. It MUST fit on exactly 1 page.\n\n"
        f"Apply ALL of these cuts IN ORDER — do not stop early:\n"
        f"1. Most recent role: max 3 bullets. Second role: max 3 bullets. Oldest role: max 2 bullets.\n"
        f"2. Every bullet: hard cap of 20 words — count and truncate any that exceed this.\n"
        f"3. Projects: keep top 2 most JD-relevant only, 2 bullets each, 20 words max per bullet.\n"
        f"4. Summary: exactly 2 sentences, 3 lines max.\n"
        f"5. Skills: max 4 categories, 6 tools each — drop entire categories not needed.\n"
        f"6. Remove ALL negative \\\\vspace values (e.g. \\\\vspace{{-11pt}}) — they cause text overlap.\n"
        f"7. Remove product names and domain labels from company lines — company name + location only.\n\n"
        f"Do NOT remove any job roles, companies, or dates.\n"
        f"Return ONLY the complete corrected .tex file — no explanations.\n\n"
        f"=== CURRENT .TEX ===\n{long_tex}"
    )


def _build_ats_retry_prompt(current_tex: str, missing_keywords: list[str], score: float) -> str:
    kw_list = "\n".join(f"  - {kw}" for kw in missing_keywords[:30])
    return (
        f"ATS keyword score is {score:.1f}% — below the 89% minimum.\n\n"
        f"Missing keywords that must appear naturally in the resume:\n{kw_list}\n\n"
        f"Inject these into the most relevant bullet points where they truthfully fit.\n"
        f"Do NOT fabricate experience. Only use these where already implied.\n\n"
        f"=== CURRENT .TEX ===\n{current_tex}\n\n"
        f"Return the complete corrected .tex file and nothing else."
    )


def _call_claude(
    prompt: str,
    client: anthropic.Anthropic,
    system: str = TAILOR_SYSTEM_PROMPT,
    max_tokens: int = 4096,
) -> str:
    """Make a Claude API call and return the text response."""
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def tailor_resume(
    job_id: int,
    job_dict: dict,
    jd_text: str,
    client: Optional[anthropic.Anthropic] = None,
) -> str:
    """
    Full tailoring pipeline for one job.

    Args:
        job_id:   Database row id (used for filename and logging).
        job_dict: Job metadata dict with keys: title, company, url, etc.
        jd_text:  Full job description text.
        client:   Optional Anthropic client (created from env if None).

    Returns:
        Absolute path to the verified, saved PDF.

    Raises:
        RuntimeError: if all quality gates fail after max retries.
        FileNotFoundError: if base_resume.tex is missing.
    """
    if client is None:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    company = re.sub(r"[^\w\s-]", "", job_dict.get("company", "Unknown")).strip().replace(" ", "")
    role = re.sub(r"[^\w\s-]", "", job_dict.get("title", "Role")).strip().replace(" ", "")
    from datetime import datetime
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    pdf_filename = f"{company}_{role}_{date_str}"

    os.makedirs(RESUMES_DIR, exist_ok=True)

    base_tex = load_base_resume()
    logger.info("Starting tailoring for job #%d: %s at %s", job_id, role, company)

    # ── Step 1: Initial tailoring call ───────────────────────────────────────
    prompt = _build_tailoring_prompt(base_tex, jd_text)
    tex_content = _extract_tex(_call_claude(prompt, client))
    tex_content = sanitise_latex(tex_content)

    # ── Step 2: Compile loop with LaTeX error retries ─────────────────────────
    for compile_attempt in range(MAX_RETRIES + 1):
        success, pdf_path, error_log = compile_tex(tex_content, RESUMES_DIR, pdf_filename)

        if success:
            break

        if compile_attempt >= MAX_RETRIES:
            raise RuntimeError(
                f"Job #{job_id}: LaTeX compile failed after {MAX_RETRIES} retries.\n"
                f"Last error:\n{error_log}"
            )

        logger.warning("Compile attempt %d failed — asking Claude to fix", compile_attempt + 1)
        fix_prompt = _build_fix_compile_prompt(tex_content, error_log)
        tex_content = _extract_tex(_call_claude(fix_prompt, client))
        tex_content = sanitise_latex(tex_content)

    logger.info("PDF compiled: %s", pdf_path)

    # ── Step 3: Page count gate ───────────────────────────────────────────────
    for page_attempt in range(MAX_PAGE_RETRIES + 1):
        pages = get_page_count(pdf_path)

        if pages == 1:
            break
        if pages == -1:
            logger.warning("Could not determine page count — skipping page gate")
            break

        if page_attempt >= MAX_PAGE_RETRIES:
            logger.warning(
                "Job #%d: page count %d after %d retries — flagging for manual review",
                job_id, pages, MAX_PAGE_RETRIES,
            )
            break

        logger.warning("Resume is %d pages — asking Claude to trim", pages)
        trim_prompt = _build_trim_prompt(tex_content, pages)
        tex_content = _extract_tex(_call_claude(trim_prompt, client))
        tex_content = sanitise_latex(tex_content)

        # Recompile after trim
        success, pdf_path, error_log = compile_tex(tex_content, RESUMES_DIR, pdf_filename)
        if not success:
            raise RuntimeError(f"Job #{job_id}: compile failed after trim: {error_log}")

    # ── Step 3b: Page fill check — expand if resume is under-full ────────────
    for fill_attempt in range(2):  # at most 1 expand pass
        fill = get_fill_percentage(pdf_path)
        if fill >= 0.85:
            logger.info("Page fill %.0f%% — OK", fill * 100)
            break

        logger.warning(
            "Job #%d: page only %.0f%% full — asking Claude to expand (attempt %d)",
            job_id, fill * 100, fill_attempt + 1,
        )
        expand_prompt = _build_expand_prompt(tex_content, int(fill * 100))
        tex_content = _extract_tex(_call_claude(expand_prompt, client))
        tex_content = sanitise_latex(tex_content)

        success, new_pdf, error_log = compile_tex(tex_content, RESUMES_DIR, pdf_filename)
        if not success:
            logger.warning("Expand recompile failed — keeping under-filled version")
            break

        # Verify we didn't overflow to 2 pages after expanding
        if get_page_count(new_pdf) == 1:
            pdf_path = new_pdf
        else:
            logger.warning("Expansion overflowed to 2 pages — keeping previous version")
            break

    # ── Step 4: ATS keyword score gate ───────────────────────────────────────
    ats_score = 0.0
    for ats_attempt in range(MAX_RETRIES + 1):
        ats_score = score_resume(pdf_path, jd_text, client)

        if ATS_SCORE_MIN <= ats_score <= ATS_SCORE_MAX:
            logger.info("ATS score %.1f%% — PASS (target: %d–%d%%)", ats_score, ATS_SCORE_MIN, ATS_SCORE_MAX)
            break

        if ats_score > ATS_SCORE_MAX:
            logger.warning(
                "ATS score %.1f%% exceeds maximum %d%% — possible keyword stuffing, flagging for review",
                ats_score, ATS_SCORE_MAX,
            )
            break

        # score < ATS_SCORE_MIN
        if ats_attempt >= MAX_RETRIES:
            logger.warning(
                "Job #%d: ATS score %.1f%% still below %d%% after %d retries",
                job_id, ats_score, ATS_SCORE_MIN, MAX_RETRIES,
            )
            break

        missing = get_missing_keywords(pdf_path, jd_text, client)
        logger.info("ATS retry %d — missing %d keywords", ats_attempt + 1, len(missing))
        retry_prompt = _build_ats_retry_prompt(tex_content, missing, ats_score)
        tex_content = _extract_tex(_call_claude(retry_prompt, client))
        tex_content = sanitise_latex(tex_content)

        # Recompile after keyword injection — next loop iteration re-scores
        success, pdf_path, error_log = compile_tex(tex_content, RESUMES_DIR, pdf_filename)
        if not success:
            raise RuntimeError(f"Job #{job_id}: compile failed after ATS retry: {error_log}")

    logger.info(
        "Tailoring complete for job #%d — PDF: %s | ATS: %.1f%%",
        job_id, pdf_path, ats_score,
    )
    return pdf_path
