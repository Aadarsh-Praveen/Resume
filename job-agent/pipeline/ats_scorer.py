"""
ATS keyword scoring.

Extracts required and preferred keywords from a JD (via Claude),
then scores a compiled PDF resume against those keywords.

Scoring formula (weighted):
    score = (2 * required_found + preferred_found) /
            (2 * required_total + preferred_total) * 100

Target range: 89–93%
"""

import os
import re
import json
import logging
import subprocess
from typing import Optional

import google.generativeai as genai

logger = logging.getLogger(__name__)


def _gemini_model():
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    return genai.GenerativeModel("gemini-2.0-flash")


PDFTEXTRACT_BIN = os.getenv("PDFTOTEXT_BIN", "pdftotext")

_KEYWORD_EXTRACTION_PROMPT = """Analyse this job description and extract:
1. REQUIRED keywords: specific technologies, tools, languages, frameworks, and must-have skills
   (things listed as 'required', 'must have', or appear in the core responsibilities)
2. PREFERRED keywords: nice-to-have skills, preferred qualifications, domain terms

Return ONLY valid JSON in this exact format with no additional text:
{
  "required": ["Python", "SQL", "machine learning", "..."],
  "preferred": ["Spark", "Kubernetes", "PhD", "..."]
}

Job Description:
"""


def extract_keywords(jd_text: str, client=None) -> dict:
    """
    Use Gemini Flash to extract required and preferred keywords from a JD.

    Returns:
        {"required": [...], "preferred": [...]}
    """
    try:
        model = _gemini_model()
        response = model.generate_content(_KEYWORD_EXTRACTION_PROMPT + jd_text[:4000])
        raw = response.text.strip()

        # Strip markdown code blocks if Claude wrapped it
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        keywords = json.loads(raw)
        if "required" not in keywords or "preferred" not in keywords:
            raise ValueError("Unexpected keyword JSON structure")

        # Normalise to lowercase for matching
        keywords["required"] = [k.lower().strip() for k in keywords["required"] if k.strip()]
        keywords["preferred"] = [k.lower().strip() for k in keywords["preferred"] if k.strip()]

        logger.info(
            "Extracted %d required + %d preferred keywords",
            len(keywords["required"]),
            len(keywords["preferred"]),
        )
        return keywords

    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.error("Keyword extraction failed: %s", e)
        # Fallback: return empty lists so pipeline can continue with a low score
        return {"required": [], "preferred": []}


def extract_pdf_text(pdf_path: str) -> str:
    """Extract plain text from a PDF using pdftotext."""
    try:
        result = subprocess.run(
            [PDFTEXTRACT_BIN, "-layout", pdf_path, "-"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            logger.warning("pdftotext failed: %s", result.stderr)
            return ""
        return result.stdout.lower()
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.warning("pdftotext error: %s", e)
        return ""


def _keyword_matches(resume_text: str, keyword: str) -> bool:
    """
    Return True if keyword appears in resume_text.
    Handles partial matches for compound terms
    (e.g., 'google bigquery' matches if 'bigquery' is present).
    """
    keyword = keyword.lower().strip()
    if not keyword:
        return False

    resume_lower = resume_text.lower()

    # Exact phrase match
    if keyword in resume_lower:
        return True

    # For multi-word keywords, check if the last meaningful word is present
    parts = [p for p in keyword.split() if p]
    if len(parts) > 1:
        # e.g., "google bigquery" → check for "bigquery"
        last_word = parts[-1]
        return bool(last_word) and last_word in resume_lower

    return False


def score_resume(
    pdf_path: str,
    jd_text: str,
    client=None,
    keywords: Optional[dict] = None,
) -> float:
    """
    Score a resume PDF against a job description.

    Pass pre-extracted ``keywords`` to avoid a redundant API call when
    ``get_missing_keywords`` will be called in the same loop iteration.

    Returns:
        float 0–100 representing the weighted ATS keyword match score.
    """
    if keywords is None:
        keywords = extract_keywords(jd_text, client)
    resume_text = extract_pdf_text(pdf_path)

    if not resume_text:
        logger.warning("Could not extract text from PDF: %s", pdf_path)
        return 0.0

    required = keywords.get("required", [])
    preferred = keywords.get("preferred", [])

    required_found = sum(1 for kw in required if _keyword_matches(resume_text, kw))
    preferred_found = sum(1 for kw in preferred if _keyword_matches(resume_text, kw))

    total_required = len(required)
    total_preferred = len(preferred)

    if total_required == 0 and total_preferred == 0:
        logger.warning("No keywords extracted — returning 0 score")
        return 0.0

    # Weighted formula: required counts double
    numerator = 2 * required_found + preferred_found
    denominator = 2 * total_required + total_preferred

    score = (numerator / denominator) * 100 if denominator > 0 else 0.0

    logger.info(
        "ATS score: %.1f%% (required: %d/%d, preferred: %d/%d)",
        score, required_found, total_required, preferred_found, total_preferred,
    )
    return round(score, 1)


def get_missing_keywords(
    pdf_path: str,
    jd_text: str,
    client=None,
    keywords: Optional[dict] = None,
) -> list[str]:
    """
    Return a list of keywords from the JD that are NOT present in the resume.
    Required keywords are listed first.

    Pass pre-extracted ``keywords`` to skip a redundant API call.
    """
    if keywords is None:
        keywords = extract_keywords(jd_text, client)
    resume_text = extract_pdf_text(pdf_path)

    missing = []
    for kw in keywords.get("required", []):
        if not _keyword_matches(resume_text, kw):
            missing.append(f"[REQUIRED] {kw}")
    for kw in keywords.get("preferred", []):
        if not _keyword_matches(resume_text, kw):
            missing.append(kw)

    return missing
