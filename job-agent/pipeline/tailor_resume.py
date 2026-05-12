"""
Core resume tailoring pipeline.

Takes a job dict + JD text, sends the base resume .tex and JD to Claude,
runs quality gates (compile -> page count -> ATS score), and saves the PDF.

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
    OPUS_COMPANIES,
)
from pipeline.latex_compiler import (
    compile_tex, get_page_count,
    sanitise_latex, adjust_margin, adjust_bottom_margin, render_preview, measure_page_gap,
    find_long_bullets,
)
from pipeline.ats_scorer import score_resume, get_missing_keywords, extract_keywords

logger = logging.getLogger(__name__)

_HAIKU_MODEL = "claude-haiku-4-5"  # mechanical retry calls (fix/trim/expand/ATS)

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

    # No fences -- find the start of actual LaTeX content (\documentclass or \begin{document})
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
        "The JD explicitly mentions certifications -- include the Certifications section at the end."
        if include_certs else
        "DO NOT include a Certifications section -- the JD does not require it."
    )
    return (
        f"Tailor the master resume (in the system) for the following job description.\n\n"
        f"=== JOB DESCRIPTION ===\n{jd_text[:5000]}\n\n"
        f"CERTIFICATIONS RULE: {cert_instruction}\n"
        f"PUBLICATIONS RULE: DO NOT include a Publications section -- omit it entirely.\n\n"
        f"Return ONLY the complete tailored .tex file -- no explanations."
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
            "Add 1 bullet to each work experience role (most recent -> 4 bullets, others -> 3 each) "
            "and expand the summary to 4 full lines."
        )
    elif needed >= 12:
        guidance = (
            "Add 1 bullet to the most recent role only (-> 4 bullets total) "
            "and lengthen 3-4 existing bullets by 4-6 words each."
        )
    else:
        guidance = (
            "Lengthen existing bullets by 3-5 words each -- extend the result metric or method. "
            "Do NOT add new bullets."
        )
    return (
        f"This resume is only ~{fill_pct}% full and must fill the ENTIRE page.\n\n"
        f"{guidance}\n\n"
        f"Rules:\n"
        f"- Every bullet: 18-22 words max, [OUTCOME + METRIC] by [HOW YOU DID IT].\n"
        f"- CRITICAL: each bullet MUST fit in exactly 2 lines -- never 3. Hard cap: 22 words.\n"
        f"- No widow lines: if a bullet wraps to 2 lines, the 2nd line must have >= 6 words.\n"
        f"- Do NOT add a Certifications or Publications section.\n"
        f"- Do NOT add blank lines or \\vspace -- real content only.\n"
        f"- Summary: 3-4 lines max -- never exceed 4 lines.\n"
        f"- Skills: 4 categories x 6-7 tools each.\n\n"
        f"IMPORTANT: do not overshoot -- the goal is ~95% fill, not 2 pages.\n"
        f"Return ONLY the complete .tex file.\n\n"
        f"=== CURRENT .TEX ===\n{sparse_tex}"
    )


def _build_trim_prompt(long_tex: str, page_count: int) -> str:
    return (
        f"This resume compiled to {page_count} pages. It MUST fit on exactly 1 page.\n\n"
        f"Remove the MINIMUM content needed -- stop as soon as 1 page is achievable.\n"
        f"Apply in this exact order:\n"
        f"1. DELETE Certifications section entirely (always safe to remove).\n"
        f"2. DELETE Publications section entirely.\n"
        f"3. Shorten any bullet exceeding 22 words -- trim trailing clauses, keep the impact.\n"
        f"   CRITICAL: every bullet MUST fit in at most 2 lines -- never 3.\n"
        f"4. Most recent role: max 4 bullets. Second role: max 3. Oldest role: max 3.\n"
        f"5. Projects: keep top 2 most JD-relevant only, max 3 bullets each, ~20 words each.\n"
        f"6. Summary: 3 sentences, 3-4 lines max.\n"
        f"7. Skills: max 4 categories, 6 tools each.\n"
        f"8. Company line format: CompanyName \\hfill City, ST -- no pipes, no product names.\n\n"
        f"No widow lines: if a bullet wraps to 2 lines, the 2nd line must have >= 6 words.\n"
        f"Do NOT remove any job roles, companies, or dates.\n"
        f"Return ONLY the complete corrected .tex file -- no explanations.\n\n"
        f"=== CURRENT .TEX ===\n{long_tex}"
    )


def _build_ats_retry_prompt(current_tex: str, missing_keywords: list[str], score: float) -> str:
    kw_list = "\n".join(f"  - {kw}" for kw in missing_keywords[:30])
    return (
        f"ATS keyword score is {score:.1f}% -- below the 89% minimum.\n\n"
        f"Missing keywords that must appear naturally in the resume:\n{kw_list}\n\n"
        f"Inject these into the most relevant bullet points where they truthfully fit.\n"
        f"Do NOT fabricate experience. Only use these where already implied.\n\n"
        f"=== CURRENT .TEX ===\n{current_tex}\n\n"
        f"Return the complete corrected .tex file and nothing else."
    )


def _build_shorten_bullets_prompt(tex: str, long_bullets: list[str]) -> str:
    bullets_list = "\n".join(f"  - {b}" for b in long_bullets[:10])
    return (
        f"The following bullet points are too long and will wrap to 3 or more lines on the page.\n"
        f"Each bullet MUST fit in exactly 2 lines on A4 at 11pt with 0.25in margins (max 22 words).\n\n"
        f"Bullets to shorten:\n{bullets_list}\n\n"
        f"Rules:\n"
        f"- Shorten ONLY the listed bullets -- do not change anything else.\n"
        f"- Keep the impact metric and action verb intact.\n"
        f"- Target: 18-22 words per bullet.\n"
        f"- If a bullet wraps to 2 lines, the 2nd line must have >= 6 words.\n\n"
        f"Return the complete corrected .tex file and nothing else.\n\n"
        f"=== CURRENT .TEX ===\n{tex}"
    )


def _claude_verify_page(pdf_path: str, client: anthropic.Anthropic) -> tuple[bool, str]:
    """
    Verify the resume is exactly 1 full page.

    Decision order (cheapest first):
      1. Page count > 1                -> OVERFLOW immediately
      2. render_preview fails          -> SHORT (conservative, triggers expansion)
      3. Pixel gap > 15%               -> SHORT immediately (obvious gap, skip Gemini)
      4. Pixel gap < 4%                -> FULL immediately (within bottom-margin tolerance)
      5. Pixel gap 4-15% (ambiguous)   -> Gemini vision for nuanced judgment
    """
    pages = get_page_count(pdf_path)
    if pages > 1:
        logger.warning("_claude_verify_page: %d pages -- OVERFLOW", pages)
        return False, "OVERFLOW"

    img = render_preview(pdf_path)
    if img is None:
        logger.warning("_claude_verify_page: render failed -- assuming SHORT to be safe")
        return False, "SHORT"

    gap = measure_page_gap(img)
    logger.info("_claude_verify_page: pixel gap %.1f%%", gap * 100)

    if gap > 0.15:
        logger.info("_claude_verify_page: obvious gap %.1f%% -- SHORT (skip Gemini)", gap * 100)
        return False, "SHORT"

    if gap < 0.04:
        logger.info("_claude_verify_page: gap %.1f%% within bottom margin -- FULL (skip Gemini)", gap * 100)
        return True, "FULL"

    # Gap is 4-15%: ambiguous -- ask Gemini
    try:
        import time
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        vision_model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = (
            "This is a rendered resume page. Examine the BOTTOM of the page carefully.\n"
            "Answer with one word only:\n"
            "- FULL: the last line of text is within 3% of the bottom margin (almost no gap)\n"
            "- SHORT: there is visible empty space at the bottom -- any gap larger than 3% of page height\n"
            "- OVERFLOW: content is cut off or runs off the page\n\n"
            "Be strict: if you can see ANY noticeable whitespace gap at the bottom, say SHORT.\n"
            "Reply with exactly one word: FULL, SHORT, or OVERFLOW"
        )
        for attempt in range(3):
            try:
                response = vision_model.generate_content([img, prompt])
                verdict = response.text.strip().upper().split()[0]
                logger.info("Gemini page verify: %s (pixel gap was %.1f%%)", verdict, gap * 100)
                return verdict == "FULL", verdict
            except Exception as e:
                if "429" in str(e) and attempt < 2:
                    wait = 20 * (attempt + 1)
                    logger.warning("Page verify 429 -- retrying in %ds (attempt %d/3)", wait, attempt + 1)
                    time.sleep(wait)
                else:
                    raise
    except Exception as e:
        logger.warning("Gemini verify failed: %s -- using pixel gap %.1f%% as SHORT", e, gap * 100)
        return False, "SHORT"


def _call_claude(
    prompt: str,
    client: anthropic.Anthropic,
    system: str = TAILOR_SYSTEM_PROMPT,
    max_tokens: int = 3000,
    model: str = "claude-sonnet-4-6",
    cached_base_tex: Optional[str] = None,
) -> str:
    """Make a Claude API call and return the text response.

    TAILOR_SYSTEM_PROMPT and base_resume.tex are cached with type=ephemeral
    so sequential jobs across the same run share the cache entry.
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

    # Step 1: Initial tailoring call
    # base_tex goes in the system (cached) so all retry calls share the cache entry.
    prompt = _build_tailoring_prompt(jd_text, include_certs)
    tex_content = _extract_tex(
        _call_claude(prompt, client, model=_model, cached_base_tex=base_tex)
    )
    tex_content = sanitise_latex(tex_content)
    tex_content = adjust_margin(tex_content, 0.25)  # uniform 0.25in all sides from the start

    # Step 2: Compile loop with LaTeX error retries
    for compile_attempt in range(MAX_RETRIES + 1):
        success, pdf_path, error_log = compile_tex(tex_content, RESUMES_DIR, pdf_filename)

        if success:
            break

        if compile_attempt >= MAX_RETRIES:
            raise RuntimeError(
                f"Job #{job_id}: LaTeX compile failed after {MAX_RETRIES} retries.\n"
                f"Last error:\n{error_log}"
            )

        logger.warning("Compile attempt %d failed -- asking Claude to fix", compile_attempt + 1)
        fix_prompt = _build_fix_compile_prompt(tex_content, error_log)
        tex_content = _extract_tex(_call_claude(fix_prompt, client, model=_HAIKU_MODEL, max_tokens=4000))
        tex_content = sanitise_latex(tex_content)

    logger.info("PDF compiled: %s", pdf_path)

    # Bullet length gate: detect and fix any bullets > 24 words before proceeding.
    # Bullets over 24 words risk wrapping to 3 lines on A4 at 11pt with 0.25in margins.
    long_bullets = find_long_bullets(tex_content)
    if long_bullets:
        logger.warning("Job #%d: %d bullets exceed 24 words -- shortening before page gates", job_id, len(long_bullets))
        shorten_tex = _extract_tex(_call_claude(_build_shorten_bullets_prompt(tex_content, long_bullets), client, model=_HAIKU_MODEL, max_tokens=4000))
        shorten_tex = sanitise_latex(shorten_tex)
        ok, shorten_pdf, _ = compile_tex(shorten_tex, RESUMES_DIR, pdf_filename)
        if ok and get_page_count(shorten_pdf) == 1:
            tex_content = shorten_tex
            pdf_path = shorten_pdf
            logger.info("Bullet shorten: %d long bullets fixed", len(long_bullets))
        else:
            logger.warning("Job #%d: bullet shorten compile failed -- continuing with original", job_id)

    # Step 3: Page count gate -- content trim then margin shrink
    # Pass 1: ask Claude to trim content (up to MAX_PAGE_RETRIES times)
    for page_attempt in range(MAX_PAGE_RETRIES + 1):
        pages = get_page_count(pdf_path)
        if pages == 1 or pages == -1:
            break

        if page_attempt >= MAX_PAGE_RETRIES:
            # Pass 2: content trim exhausted -- try shrinking margins (0.25 -> 0.22 -> 0.20)
            margin = 0.25
            while margin >= 0.20:
                logger.warning(
                    "Job #%d: still %d pages -- reducing margin to %.2fin",
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
                    "Job #%d: could not fit on 1 page even at min margins -- flagging",
                    job_id,
                )
            break

        logger.warning("Resume is %d pages -- asking Claude to trim", pages)
        trim_prompt = _build_trim_prompt(tex_content, pages)
        tex_content = _extract_tex(_call_claude(trim_prompt, client, model=_HAIKU_MODEL, max_tokens=4000))
        tex_content = sanitise_latex(tex_content)
        tex_content = adjust_margin(tex_content, 0.25)  # re-lock margins after trim

        success, pdf_path, error_log = compile_tex(tex_content, RESUMES_DIR, pdf_filename)
        if not success:
            raise RuntimeError(f"Job #{job_id}: compile failed after trim: {error_log}")

    # Step 3b: Visual verify loop -- up to 3 attempts
    # SHORT: Claude content expansion only (margins stay at 0.25in max)
    # OVERFLOW: content trim first, then margin shrink down to 0.20in
    for visual_attempt in range(3):
        is_good, verdict = _claude_verify_page(pdf_path, client)
        if is_good:
            logger.info("Page verify: FULL -- approved (attempt %d)", visual_attempt + 1)
            break

        if verdict == "SHORT":
            # Measure actual gap to calibrate how aggressive to expand
            gap_img = render_preview(pdf_path)
            gap = measure_page_gap(gap_img) if gap_img is not None else 0.15
            # Each attempt gets more aggressive: lower effective fill_pct forces bigger expansion
            effective_fill = max(int((1.0 - gap) * 100) - (visual_attempt * 10), 60)
            logger.warning(
                "Job #%d: SHORT on attempt %d (gap %.1f%%, effective fill %d%%) -- expanding",
                job_id, visual_attempt + 1, gap * 100, effective_fill,
            )
            expand_prompt = _build_expand_prompt(tex_content, effective_fill)
            expanded_tex = _extract_tex(_call_claude(expand_prompt, client, model=_HAIKU_MODEL, max_tokens=4000))
            expanded_tex = sanitise_latex(expanded_tex)
            ok, expanded_pdf, error_log = compile_tex(expanded_tex, RESUMES_DIR, pdf_filename)
            if not ok:
                # Expansion produced broken LaTeX (often truncation) -- try to fix it
                logger.warning("Job #%d: expand compile failed on attempt %d -- trying auto-fix", job_id, visual_attempt + 1)
                for _fix in range(2):
                    fixed_tex = _extract_tex(_call_claude(_build_fix_compile_prompt(expanded_tex, error_log), client, model=_HAIKU_MODEL, max_tokens=4000))
                    fixed_tex = sanitise_latex(fixed_tex)
                    ok, expanded_pdf, error_log = compile_tex(fixed_tex, RESUMES_DIR, pdf_filename)
                    if ok:
                        expanded_tex = fixed_tex
                        break
                if not ok:
                    logger.warning("Job #%d: expand auto-fix also failed on attempt %d -- keeping current", job_id, visual_attempt + 1)
                    break
            new_pages = get_page_count(expanded_pdf)
            if new_pages == 1:
                tex_content = expanded_tex
                pdf_path = expanded_pdf
            elif new_pages > 1:
                # Expand overshot -- trim back to 1 page then stop expanding
                logger.warning("Job #%d: expand overflowed to %d pages -- trimming to recover", job_id, new_pages)
                recover_tex = _extract_tex(
                    _call_claude(_build_trim_prompt(expanded_tex, new_pages), client, model=_HAIKU_MODEL, max_tokens=4000)
                )
                recover_tex = sanitise_latex(recover_tex)
                recover_tex = adjust_margin(recover_tex, 0.25)
                ok, recovered_pdf, _ = compile_tex(recover_tex, RESUMES_DIR, pdf_filename)
                if ok and get_page_count(recovered_pdf) == 1:
                    tex_content = recover_tex
                    pdf_path = recovered_pdf
                    logger.info("Post-expand trim recovered 1-page layout")
                else:
                    logger.warning("Post-expand trim failed -- keeping pre-expand PDF")
                break  # stop expanding after an overflow recovery
            # continue loop to re-verify

        elif verdict == "OVERFLOW":
            logger.warning(
                "Job #%d: OVERFLOW on attempt %d -- trimming content",
                job_id, visual_attempt + 1,
            )
            pages_actual = get_page_count(pdf_path)
            trim_pages = pages_actual if pages_actual > 1 else 2
            trim_tex = _extract_tex(
                _call_claude(_build_trim_prompt(tex_content, trim_pages), client, model=_HAIKU_MODEL, max_tokens=4000)
            )
            trim_tex = sanitise_latex(trim_tex)
            trim_tex = adjust_margin(trim_tex, 0.25)
            ok, trimmed_pdf, _ = compile_tex(trim_tex, RESUMES_DIR, pdf_filename)
            if ok and get_page_count(trimmed_pdf) == 1:
                tex_content = trim_tex
                pdf_path = trimmed_pdf
                logger.info("Content trim fixed OVERFLOW")
            elif ok:
                # Content trim not enough -- shrink margins as last resort (0.23 -> 0.21 -> 0.20)
                for margin in [0.23, 0.21, 0.20]:
                    shrink_tex = adjust_margin(trim_tex, margin)
                    ok2, shrink_pdf, _ = compile_tex(shrink_tex, RESUMES_DIR, pdf_filename)
                    if ok2 and get_page_count(shrink_pdf) == 1:
                        tex_content = shrink_tex
                        pdf_path = shrink_pdf
                        logger.info("Margin %.2fin resolved OVERFLOW", margin)
                        break
                else:
                    logger.warning("Job #%d: could not fit on 1 page -- flagging", job_id)
            # continue loop to re-verify

        else:
            break

    # Pixel safety net: final check after loop.
    # Strategy:
    #   gap <= 6.4% (bottom margin <= 0.75in): absorb gap by increasing bottom margin —
    #     deterministic, always works, content reaches the margin line.
    #   gap > 6.4%: gap too large for margin trick (looks unprofessional) —
    #     try one last content expansion, then fall back to margin absorption.
    _A4_H_IN = 11.69
    safety_img = render_preview(pdf_path)
    if safety_img is not None:
        safety_gap = measure_page_gap(safety_img)
        if safety_gap > 0.04:
            new_bottom = round(safety_gap * _A4_H_IN, 3)
            if new_bottom <= 0.75:
                # Small gap: absorb deterministically by raising bottom margin
                adj_tex = adjust_bottom_margin(tex_content, new_bottom)
                ok, adj_pdf, _ = compile_tex(adj_tex, RESUMES_DIR, pdf_filename)
                if ok and get_page_count(adj_pdf) == 1:
                    pdf_path = adj_pdf
                    logger.info(
                        "Safety net: gap %.1f%% absorbed by bottom margin %.3fin",
                        safety_gap * 100, new_bottom,
                    )
                else:
                    logger.warning("Job #%d: bottom margin adjustment failed -- shipping as-is", job_id)
            else:
                # Large gap: try content expansion, then fall back to margin absorption
                logger.warning(
                    "Job #%d: safety net large gap %.1f%% -- trying content expansion",
                    job_id, safety_gap * 100,
                )
                net_fill = max(int((1.0 - safety_gap) * 100) - 10, 55)
                safety_tex = _extract_tex(
                    _call_claude(_build_expand_prompt(tex_content, net_fill), client, model=_HAIKU_MODEL, max_tokens=4000)
                )
                safety_tex = sanitise_latex(safety_tex)
                ok, safety_pdf, err = compile_tex(safety_tex, RESUMES_DIR, pdf_filename)
                if not ok:
                    for _fix in range(2):
                        safety_tex = _extract_tex(_call_claude(_build_fix_compile_prompt(safety_tex, err), client, model=_HAIKU_MODEL, max_tokens=4000))
                        safety_tex = sanitise_latex(safety_tex)
                        ok, safety_pdf, err = compile_tex(safety_tex, RESUMES_DIR, pdf_filename)
                        if ok:
                            break
                if ok and get_page_count(safety_pdf) == 1:
                    check_img = render_preview(safety_pdf)
                    post_gap = measure_page_gap(check_img) if check_img is not None else safety_gap
                    if post_gap < safety_gap:
                        tex_content = safety_tex
                        pdf_path = safety_pdf
                        logger.info("Safety net expand: gap %.1f%% -> %.1f%%", safety_gap * 100, post_gap * 100)
                        # If gap reduced but still > 4%, absorb the remainder with margin
                        if post_gap > 0.04:
                            rem_bottom = round(post_gap * _A4_H_IN, 3)
                            if rem_bottom <= 0.75:
                                adj_tex = adjust_bottom_margin(tex_content, rem_bottom)
                                ok2, adj_pdf, _ = compile_tex(adj_tex, RESUMES_DIR, pdf_filename)
                                if ok2 and get_page_count(adj_pdf) == 1:
                                    pdf_path = adj_pdf
                                    logger.info("Safety net: residual gap %.1f%% absorbed by bottom margin %.3fin", post_gap * 100, rem_bottom)
                    else:
                        # Expand didn't help — absorb with margin as last resort
                        rem_bottom = min(round(safety_gap * _A4_H_IN, 3), 0.75)
                        adj_tex = adjust_bottom_margin(tex_content, rem_bottom)
                        ok2, adj_pdf, _ = compile_tex(adj_tex, RESUMES_DIR, pdf_filename)
                        if ok2 and get_page_count(adj_pdf) == 1:
                            pdf_path = adj_pdf
                            logger.info("Safety net fallback: margin absorption %.3fin", rem_bottom)
                else:
                    # Expand compile failed — absorb with margin as last resort
                    rem_bottom = min(round(safety_gap * _A4_H_IN, 3), 0.75)
                    adj_tex = adjust_bottom_margin(tex_content, rem_bottom)
                    ok2, adj_pdf, _ = compile_tex(adj_tex, RESUMES_DIR, pdf_filename)
                    if ok2 and get_page_count(adj_pdf) == 1:
                        pdf_path = adj_pdf
                        logger.info("Safety net fallback: margin absorption %.3fin after failed expand", rem_bottom)

    # Step 4: ATS keyword score gate
    # Extract keywords once -- reused by both score_resume and get_missing_keywords
    # to avoid a duplicate Haiku call on every retry iteration.
    jd_keywords = extract_keywords(jd_text, client)
    ats_score = 0.0
    for ats_attempt in range(MAX_RETRIES + 1):
        ats_score = score_resume(pdf_path, jd_text, client, keywords=jd_keywords)

        if ATS_SCORE_MIN <= ats_score <= ATS_SCORE_MAX:
            logger.info("ATS score %.1f%% -- PASS (target: %d-%d%%)", ats_score, ATS_SCORE_MIN, ATS_SCORE_MAX)
            break

        if ats_score > ATS_SCORE_MAX:
            logger.warning(
                "ATS score %.1f%% exceeds maximum -- flagging for review",
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
        logger.info("ATS retry %d -- missing %d keywords", ats_attempt + 1, len(missing))
        retry_prompt = _build_ats_retry_prompt(tex_content, missing, ats_score)
        tex_content = _extract_tex(_call_claude(retry_prompt, client, model=_HAIKU_MODEL, max_tokens=4000))
        tex_content = sanitise_latex(tex_content)

        # Recompile after keyword injection; auto-fix if broken
        success, pdf_path, error_log = compile_tex(tex_content, RESUMES_DIR, pdf_filename)
        if not success:
            logger.warning("Job #%d: ATS retry compile failed -- attempting auto-fix", job_id)
            for _fix in range(2):
                tex_content = _extract_tex(_call_claude(_build_fix_compile_prompt(tex_content, error_log), client, model=_HAIKU_MODEL, max_tokens=4000))
                tex_content = sanitise_latex(tex_content)
                success, pdf_path, error_log = compile_tex(tex_content, RESUMES_DIR, pdf_filename)
                if success:
                    break
            if not success:
                raise RuntimeError(f"Job #{job_id}: compile failed after ATS retry (auto-fix also failed): {error_log}")
        # Gate: ATS keyword injection must not push to 2 pages
        if get_page_count(pdf_path) > 1:
            logger.warning("Job #%d: ATS keyword injection overflowed -- trimming back", job_id)
            ats_trim_tex = _extract_tex(_call_claude(_build_trim_prompt(tex_content, 2), client, model=_HAIKU_MODEL, max_tokens=4000))
            ats_trim_tex = sanitise_latex(ats_trim_tex)
            ats_trim_tex = adjust_margin(ats_trim_tex, 0.25)
            ok_t, ats_trim_pdf, _ = compile_tex(ats_trim_tex, RESUMES_DIR, pdf_filename)
            if ok_t and get_page_count(ats_trim_pdf) == 1:
                tex_content = ats_trim_tex
                pdf_path = ats_trim_pdf
                logger.info("ATS overflow: trimmed back to 1 page")
            else:
                logger.warning("Job #%d: ATS overflow trim failed -- shipping as-is", job_id)

    # ── Final hard gate ───────────────────────────────────────────────────────
    # Run up to 2 correction passes. Each pass: fix page count first, then absorb
    # any remaining bottom gap via margin adjustment. Only ships when both pass.
    for _final in range(2):
        _gate_changed = False

        # 1. Page count must be exactly 1
        gate_pages = get_page_count(pdf_path)
        if gate_pages > 1:
            logger.warning("Job #%d: FINAL GATE -- %d pages -- emergency trim", job_id, gate_pages)
            emerg_tex = _extract_tex(
                _call_claude(_build_trim_prompt(tex_content, gate_pages), client, model=_HAIKU_MODEL, max_tokens=4000)
            )
            emerg_tex = sanitise_latex(emerg_tex)
            for _margin in [0.25, 0.22, 0.20]:
                emerg_tex2 = adjust_margin(emerg_tex, _margin)
                ok, emerg_pdf, _ = compile_tex(emerg_tex2, RESUMES_DIR, pdf_filename)
                if ok and get_page_count(emerg_pdf) == 1:
                    tex_content = emerg_tex2
                    pdf_path = emerg_pdf
                    logger.info("Final gate: trimmed to 1 page at margin %.2fin", _margin)
                    _gate_changed = True
                    break
            else:
                logger.warning("Job #%d: FINAL GATE -- could not trim to 1 page -- shipping as-is", job_id)
                break

        # 2. Bottom gap must be < 4%
        gate_img = render_preview(pdf_path)
        if gate_img is not None:
            gate_gap = measure_page_gap(gate_img)
            if gate_gap > 0.04:
                gate_bottom = min(round(gate_gap * _A4_H_IN, 3), 0.75)
                adj_tex = adjust_bottom_margin(tex_content, gate_bottom)
                ok, adj_pdf, _ = compile_tex(adj_tex, RESUMES_DIR, pdf_filename)
                if ok and get_page_count(adj_pdf) == 1:
                    tex_content = adj_tex
                    pdf_path = adj_pdf
                    logger.info("Final gate: gap %.1f%% absorbed by bottom margin %.3fin", gate_gap * 100, gate_bottom)
                    _gate_changed = True
                else:
                    logger.warning("Job #%d: FINAL GATE -- margin absorption failed (gap %.1f%%)", job_id, gate_gap * 100)

        if not _gate_changed:
            break  # nothing changed -- either all good or unfixable

    # Step 5: Generate cover letter
    cover_letter = _generate_cover_letter(job_dict, jd_text, client)

    # Step 6: Upload PDF to GCS (if configured)
    from pipeline.gcs import upload_pdf
    pdf_filename = os.path.basename(pdf_path)
    pdf_path = upload_pdf(pdf_path, pdf_filename)

    logger.info(
        "Tailoring complete for job #%d -- PDF: %s | ATS: %.1f%%",
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
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.warning("Cover letter generation failed: %s", e)
        return ""
