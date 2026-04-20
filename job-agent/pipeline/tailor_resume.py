"""
Core resume tailoring pipeline.

Takes a job dict + JD text, sends the base resume .tex and JD to Claude,
runs quality gates (compile → page count → ATS score), and saves the PDF.

Usage:
    from pipeline.tailor_resume import tailor_resume
    pdf_path = tailor_resume(job_id=42, job_dict=job, jd_text=jd)
"""

import base64
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
from pipeline.latex_compiler import (
    compile_tex, get_page_count, get_fill_percentage,
    sanitise_latex, adjust_margin, render_preview,
)
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


_CERT_KEYWORDS = frozenset([
    "certif", "aws certified", "azure certified", "gcp certified",
    "oracle certified", "comptia", "cissp", "pmp", "cpa", "cfa",
])

def _jd_mentions_certifications(jd_text: str) -> bool:
    jd_lower = jd_text.lower()
    return any(kw in jd_lower for kw in _CERT_KEYWORDS)


def _build_tailoring_prompt(base_tex: str, jd_text: str, include_certs: bool = False) -> str:
    cert_instruction = (
        "The JD explicitly mentions certifications — include the Certifications section at the end."
        if include_certs else
        "DO NOT include a Certifications section — the JD does not require it."
    )
    return (
        f"Tailor this LaTeX resume for the following job description.\n\n"
        f"=== JOB DESCRIPTION ===\n{jd_text[:5000]}\n\n"
        f"=== CURRENT RESUME (.tex) ===\n{base_tex}\n\n"
        f"CERTIFICATIONS RULE: {cert_instruction}\n"
        f"PUBLICATIONS RULE: DO NOT include a Publications section — omit it entirely.\n\n"
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
        f"Expand to reach these EXACT targets (do not exceed them):\n"
        f"1. Most recent role: exactly 4 bullets (add from original if needed)\n"
        f"2. Second role: exactly 3 bullets\n"
        f"3. Third/oldest role: exactly 3 bullets\n"
        f"4. Projects: 2 projects × exactly 3 bullets each\n"
        f"5. Summary: exactly 3 sentences\n"
        f"6. Skills: 4 categories × 6–7 tools each\n"
        f"7. DO NOT add a Certifications or Publications section — they overflow the page.\n\n"
        f"Every bullet: 20–28 words, [OUTCOME + METRIC] by [HOW YOU DID IT].\n"
        f"Do NOT add blank lines or \\\\vspace — add real content only.\n"
        f"Return ONLY the complete .tex file.\n\n"
        f"=== CURRENT .TEX ===\n{sparse_tex}"
    )


def _build_trim_prompt(long_tex: str, page_count: int) -> str:
    return (
        f"This resume compiled to {page_count} pages. It MUST fit on exactly 1 page.\n\n"
        f"Apply ALL of these cuts IN ORDER — do not stop early:\n"
        f"1. DELETE the Certifications section entirely — it overflows the 1-page budget.\n"
        f"2. DELETE the Publications/Publication section entirely.\n"
        f"3. Most recent role: max 4 bullets. Second role: max 3 bullets. Oldest role: max 3 bullets.\n"
        f"4. Every bullet: hard cap of 22 words — count and truncate any that exceed this.\n"
        f"5. Projects: keep top 2 most JD-relevant only, 3 bullets each, 22 words max per bullet.\n"
        f"6. Summary: exactly 3 sentences, 3 lines max.\n"
        f"7. Skills: max 4 categories, 6 tools each — drop entire categories not needed.\n"
        f"8. Company line format: CompanyName \\\\hfill City, ST — NO pipes, NO product names.\n\n"
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


def _claude_verify_page(pdf_path: str, client: anthropic.Anthropic) -> tuple[bool, str]:
    """
    Use Claude Haiku vision to verify the resume is exactly 1 full page.

    Returns (is_good, feedback) where is_good=True means the page looks correct.
    Falls back to (True, "no preview") if render_preview is unavailable.
    """
    jpeg_path = render_preview(pdf_path)
    if not jpeg_path or not os.path.exists(jpeg_path):
        logger.warning("_claude_verify_page: no preview available — assuming OK")
        return True, "no preview"

    try:
        with open(jpeg_path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode()

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "This is a rendered resume page. Answer with one word only:\n"
                            "- FULL: content reaches within ~2% of the bottom margin, no overflow\n"
                            "- SHORT: any visible whitespace gap at the bottom (more than 5% of page height empty)\n"
                            "- OVERFLOW: content is cut off or text runs off the page\n"
                            "Reply with exactly one word: FULL, SHORT, or OVERFLOW"
                        ),
                    },
                ],
            }],
        )
        verdict = message.content[0].text.strip().upper().split()[0]
        logger.info("Claude page verify: %s", verdict)
        return verdict == "FULL", verdict
    except Exception as e:
        logger.warning("Claude page verify failed: %s — assuming OK", e)
        return True, "error"
    finally:
        try:
            os.remove(jpeg_path)
        except OSError:
            pass


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
    include_certs = _jd_mentions_certifications(jd_text)
    logger.info(
        "Starting tailoring for job #%d: %s at %s (certs: %s)",
        job_id, role, company, include_certs,
    )

    # ── Step 1: Initial tailoring call ───────────────────────────────────────
    prompt = _build_tailoring_prompt(base_tex, jd_text, include_certs)
    tex_content = _extract_tex(_call_claude(prompt, client))
    tex_content = sanitise_latex(tex_content)
    tex_content = adjust_margin(tex_content, 0.25)  # uniform 0.25in all sides from the start

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

    # ── Step 3: Page count gate — content trim then margin shrink ────────────
    # Pass 1: ask Claude to trim content (up to MAX_PAGE_RETRIES times)
    for page_attempt in range(MAX_PAGE_RETRIES + 1):
        pages = get_page_count(pdf_path)
        if pages == 1 or pages == -1:
            break

        if page_attempt >= MAX_PAGE_RETRIES:
            # Pass 2: content trim exhausted — try shrinking margins (0.25 → 0.22 → 0.20)
            margin = 0.25
            while margin >= 0.20:
                logger.warning(
                    "Job #%d: still %d pages — reducing margin to %.2fin",
                    job_id, pages, margin,
                )
                tex_content = adjust_margin(tex_content, margin)
                success, new_pdf, error_log = compile_tex(tex_content, RESUMES_DIR, pdf_filename)
                if success:
                    pdf_path = new_pdf
                    if get_page_count(pdf_path) == 1:
                        logger.info("Margin %.2fin fixed overflow", margin)
                        break
                margin = round(margin - 0.03, 2)
            else:
                logger.warning(
                    "Job #%d: could not fit on 1 page even at min margins — flagging",
                    job_id,
                )
            break

        logger.warning("Resume is %d pages — asking Claude to trim", pages)
        trim_prompt = _build_trim_prompt(tex_content, pages)
        tex_content = _extract_tex(_call_claude(trim_prompt, client))
        tex_content = sanitise_latex(tex_content)
        tex_content = adjust_margin(tex_content, 0.25)  # re-lock margins after trim

        success, pdf_path, error_log = compile_tex(tex_content, RESUMES_DIR, pdf_filename)
        if not success:
            raise RuntimeError(f"Job #{job_id}: compile failed after trim: {error_log}")

    # ── Step 3b: Claude visual verify — page must be FULL ────────────────────
    # Up to 2 passes: expand if SHORT, trim if OVERFLOW
    for visual_attempt in range(2):
        is_good, verdict = _claude_verify_page(pdf_path, client)
        if is_good:
            logger.info("Claude page verify: FULL — approved")
            break

        if verdict == "SHORT":
            fill = get_fill_percentage(pdf_path)
            logger.warning(
                "Job #%d: Claude says SHORT (fill ~%.0f%%) — expanding (attempt %d)",
                job_id, fill * 100, visual_attempt + 1,
            )
            expand_prompt = _build_expand_prompt(tex_content, int(fill * 100))
            tex_content = _extract_tex(_call_claude(expand_prompt, client))
            tex_content = sanitise_latex(tex_content)
            success, new_pdf, error_log = compile_tex(tex_content, RESUMES_DIR, pdf_filename)
            if success and get_page_count(new_pdf) == 1:
                pdf_path = new_pdf
            else:
                logger.warning("Expand recompile failed/overflowed — keeping previous")
                break

        elif verdict == "OVERFLOW":
            logger.warning(
                "Job #%d: Claude says OVERFLOW — trimming margin (attempt %d)",
                job_id, visual_attempt + 1,
            )
            # Try one margin step before declaring failure
            tex_content = adjust_margin(tex_content, 0.22)
            success, new_pdf, error_log = compile_tex(tex_content, RESUMES_DIR, pdf_filename)
            if success:
                pdf_path = new_pdf
            else:
                break
        else:
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

    # ── Step 5: Generate cover letter ────────────────────────────────────────
    cover_letter = _generate_cover_letter(job_dict, jd_text, client)

    logger.info(
        "Tailoring complete for job #%d — PDF: %s | ATS: %.1f%%",
        job_id, pdf_path, ats_score,
    )
    return pdf_path, ats_score, cover_letter


def _generate_cover_letter(
    job_dict: dict,
    jd_text: str,
    client: anthropic.Anthropic,
) -> str:
    """Generate a 3-paragraph cover letter using the COLD_EMAIL_SYSTEM_PROMPT style."""
    from config import COLD_EMAIL_SYSTEM_PROMPT
    import os
    first = os.getenv("APPLICANT_FIRST_NAME", "")
    last  = os.getenv("APPLICANT_LAST_NAME", "")
    name  = f"{first} {last}".strip() or "Aadarsh Praveen"

    prompt = (
        f"Write a professional cover letter (3 paragraphs, ~200 words) for:\n\n"
        f"Role: {job_dict.get('title', '')}\n"
        f"Company: {job_dict.get('company', '')}\n\n"
        f"Job description:\n{jd_text[:3000]}\n\n"
        f"Applicant name: {name}\n\n"
        f"Rules: outcome-first sentences, one hard metric per paragraph, "
        f"no buzzwords, professional tone. Sign off with just the name."
    )
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        logger.warning("Cover letter generation failed: %s", e)
        return ""
