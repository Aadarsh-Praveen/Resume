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
    OPUS_COMPANIES,
)
from pipeline.latex_compiler import (
    compile_tex, get_page_count, get_fill_percentage,
    sanitise_latex, adjust_margin, render_preview,
)
from pipeline.ats_scorer import score_resume, get_missing_keywords, extract_keywords

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


def _build_tailoring_prompt(jd_text: str, include_certs: bool = False) -> str:
    """Build the initial tailoring prompt.

    The base resume is now in the system (cached), so only the JD goes here.
    """
    cert_instruction = (
        "The JD explicitly mentions certifications — include the Certifications section at the end."
        if include_certs else
        "DO NOT include a Certifications section — the JD does not require it."
    )
    return (
        f"Tailor the master resume (in the system) for the following job description.\n\n"
        f"=== JOB DESCRIPTION ===\n{jd_text[:5000]}\n\n"
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
    needed = 100 - fill_pct
    if needed >= 25:
        guidance = (
            "Add 1 bullet to each work experience role (most recent → 4 bullets, others → 3 each) "
            "and expand the summary to 4 full lines."
        )
    elif needed >= 12:
        guidance = (
            "Add 1 bullet to the most recent role only (→ 4 bullets total) "
            "and lengthen 3–4 existing bullets by 4–6 words each."
        )
    else:
        guidance = (
            "Lengthen existing bullets by 3–5 words each — extend the result metric or method. "
            "Do NOT add new bullets."
        )
    return (
        f"This resume is only ~{fill_pct}% full and must fill the ENTIRE page.\n\n"
        f"{guidance}\n\n"
        f"Rules:\n"
        f"• Every bullet: 20–28 words, [OUTCOME + METRIC] by [HOW YOU DID IT].\n"
        f"• No widow lines: if a bullet wraps to 2 lines, the 2nd line must have ≥8 words.\n"
        f"• Do NOT add a Certifications or Publications section.\n"
        f"• Do NOT add blank lines or \\\\vspace — real content only.\n"
        f"• Summary: 3–4 lines max — never exceed 4 lines.\n"
        f"• Skills: 4 categories × 6–7 tools each.\n\n"
        f"IMPORTANT: do not overshoot — the goal is ~95%% fill, not 2 pages.\n"
        f"Return ONLY the complete .tex file.\n\n"
        f"=== CURRENT .TEX ===\n{sparse_tex}"
    )


def _build_trim_prompt(long_tex: str, page_count: int) -> str:
    return (
        f"This resume compiled to {page_count} pages. It MUST fit on exactly 1 page.\n\n"
        f"Remove the MINIMUM content needed — stop as soon as 1 page is achievable.\n"
        f"Apply in this exact order:\n"
        f"1. DELETE Certifications section entirely (always safe to remove).\n"
        f"2. DELETE Publications section entirely.\n"
        f"3. Shorten any bullet exceeding 22 words — trim trailing clauses, keep the impact.\n"
        f"4. Most recent role: max 4 bullets. Second role: max 3. Oldest role: max 3.\n"
        f"5. Projects: keep top 2 most JD-relevant only, max 3 bullets each, ≤20 words each.\n"
        f"6. Summary: 3 sentences, 3–4 lines max.\n"
        f"7. Skills: max 4 categories, 6 tools each.\n"
        f"8. Company line format: CompanyName \\\\hfill City, ST — no pipes, no product names.\n\n"
        f"No widow lines: if a bullet wraps to 2 lines, the 2nd line must have ≥8 words.\n"
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
    Verify the resume is exactly 1 full page.

    Fast-path order (cheapest first):
      1. Page count > 1 → OVERFLOW (no vision call)
      2. Page count == 1 and fill 82–96% → FULL (no vision call)
      3. Otherwise → Haiku vision call
    """
    pages = get_page_count(pdf_path)
    if pages > 1:
        logger.warning("_claude_verify_page: %d pages detected — OVERFLOW", pages)
        return False, "OVERFLOW"

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
    model: str = "claude-sonnet-4-6",
    cached_base_tex: Optional[str] = None,
) -> str:
    """Make a Claude API call and return the text response.

    TAILOR_SYSTEM_PROMPT is always sent with cache_control (ephemeral).
    When ``cached_base_tex`` is provided it is added as a second cached
    content block in the system — this lets all parallel jobs in the same
    5-minute window share the same base resume cache entry (~10× cheaper
    on that block after the first write).
    """
    if system is TAILOR_SYSTEM_PROMPT:
        system_content = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}},
        ]
        if cached_base_tex:
            system_content.append({
                "type": "text",
                "text": f"=== MASTER RESUME (.tex) ===\n{cached_base_tex}",
                "cache_control": {"type": "ephemeral"},
            })
    else:
        system_content = system

    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_content,
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

    # Route top-tier companies through Opus for best possible resume quality
    company_lower = company.lower()
    _model = (
        "claude-opus-4-7"
        if any(name in company_lower for name in OPUS_COMPANIES)
        else "claude-sonnet-4-6"
    )
    logger.info(
        "Starting tailoring for job #%d: %s at %s (certs: %s, model: %s)",
        job_id, role, company, include_certs, _model,
    )

    # ── Step 1: Initial tailoring call ───────────────────────────────────────
    # base_tex goes in the system (cached) so all retry calls share the cache entry.
    prompt = _build_tailoring_prompt(jd_text, include_certs)
    tex_content = _extract_tex(
        _call_claude(prompt, client, model=_model, cached_base_tex=base_tex)
    )
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
        tex_content = _extract_tex(_call_claude(fix_prompt, client, model=_model))
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
        tex_content = _extract_tex(_call_claude(trim_prompt, client, model=_model))
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
            # First try widening margins (0.25 → 0.27 → 0.28) — no content change needed
            margin_fixed = False
            for margin in [0.27, 0.28]:
                test_tex = adjust_margin(tex_content, margin)
                ok, test_pdf, _ = compile_tex(test_tex, RESUMES_DIR, pdf_filename)
                if ok and get_page_count(test_pdf) == 1:
                    test_fill = get_fill_percentage(test_pdf)
                    if test_fill >= 0.85:
                        tex_content = test_tex
                        pdf_path = test_pdf
                        margin_fixed = True
                        logger.info("Margin %.2fin filled page to %.0f%%", margin, test_fill * 100)
                        break
            if margin_fixed:
                break
            # Margin didn't help — ask Claude to add content
            expand_prompt = _build_expand_prompt(tex_content, int(fill * 100))
            tex_content = _extract_tex(_call_claude(expand_prompt, client, model=_model))
            tex_content = sanitise_latex(tex_content)
            success, new_pdf, error_log = compile_tex(tex_content, RESUMES_DIR, pdf_filename)
            if not success:
                logger.warning("Expand recompile failed — keeping pre-expand PDF")
                break
            new_pages = get_page_count(new_pdf)
            if new_pages == 1:
                pdf_path = new_pdf
            elif new_pages > 1:
                # Expand overshot — trim lightly to recover 1 page
                logger.warning(
                    "Job #%d: expand overflowed to %d pages — trimming to recover",
                    job_id, new_pages,
                )
                recover_tex = _extract_tex(
                    _call_claude(_build_trim_prompt(tex_content, new_pages), client, model=_model)
                )
                recover_tex = sanitise_latex(recover_tex)
                recover_tex = adjust_margin(recover_tex, 0.25)
                ok, recovered_pdf, _ = compile_tex(recover_tex, RESUMES_DIR, pdf_filename)
                if ok and get_page_count(recovered_pdf) == 1:
                    tex_content = recover_tex
                    pdf_path = recovered_pdf
                    logger.info("Post-expand trim recovered 1-page layout")
                else:
                    logger.warning("Post-expand trim also failed — keeping pre-expand PDF")
            break

        elif verdict == "OVERFLOW":
            logger.warning(
                "Job #%d: visual OVERFLOW on attempt %d — trimming content",
                job_id, visual_attempt + 1,
            )
            # Content trim is more reliable than margin shrink for true overflow
            pages_actual = get_page_count(pdf_path)
            trim_pages = pages_actual if pages_actual > 1 else 2
            trim_tex = _extract_tex(
                _call_claude(_build_trim_prompt(tex_content, trim_pages), client, model=_model)
            )
            trim_tex = sanitise_latex(trim_tex)
            trim_tex = adjust_margin(trim_tex, 0.25)
            ok, trimmed_pdf, _ = compile_tex(trim_tex, RESUMES_DIR, pdf_filename)
            if ok and get_page_count(trimmed_pdf) == 1:
                tex_content = trim_tex
                pdf_path = trimmed_pdf
                logger.info("Visual OVERFLOW content trim recovered 1-page layout")
            elif ok:
                # Still overflowing — try minimum margins as last resort
                tex_content = adjust_margin(trim_tex, 0.20)
                ok2, new_pdf2, _ = compile_tex(tex_content, RESUMES_DIR, pdf_filename)
                if ok2:
                    pdf_path = new_pdf2
        else:
            break

    # ── Step 4: ATS keyword score gate ───────────────────────────────────────
    # Extract keywords once — reused by both score_resume and get_missing_keywords
    # to avoid a duplicate Haiku call on every retry iteration.
    jd_keywords = extract_keywords(jd_text, client)
    ats_score = 0.0
    for ats_attempt in range(MAX_RETRIES + 1):
        ats_score = score_resume(pdf_path, jd_text, client, keywords=jd_keywords)

        if ATS_SCORE_MIN <= ats_score <= ATS_SCORE_MAX:
            logger.info("ATS score %.1f%% — PASS (target: %d–%d%%)", ats_score, ATS_SCORE_MIN, ATS_SCORE_MAX)
            break

        if ats_score > ATS_SCORE_MAX:
            logger.warning(
                "ATS score %.1f%% exceeds maximum — flagging for review",
                ats_score,
            )
            break

        # score < ATS_SCORE_MIN
        if ats_attempt >= MAX_RETRIES:
            logger.warning(
                "Job #%d: ATS score %.1f%% still below %d%% after %d retries",
                job_id, ats_score, ATS_SCORE_MIN, MAX_RETRIES,
            )
            break

        missing = get_missing_keywords(pdf_path, jd_text, client, keywords=jd_keywords)
        logger.info("ATS retry %d — missing %d keywords", ats_attempt + 1, len(missing))
        retry_prompt = _build_ats_retry_prompt(tex_content, missing, ats_score)
        tex_content = _extract_tex(_call_claude(retry_prompt, client, model=_model))
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
