"""
LLM-based job fit assessment using Claude Haiku.

Runs BEFORE resume tailoring to skip jobs the candidate clearly cannot meet,
saving Claude Sonnet tokens and pdflatex time.

Catches what regex year-extraction misses:
  - PhD / security-clearance / domain-license hard requirements
  - "preferred" vs "minimum" experience distinctions
  - Implicit seniority signals ("lead a team of 10")
  - Compound blocks ("5+ years AND management experience required")
"""

import json
import logging
import os
import re
from typing import Optional

import google.generativeai as genai

logger = logging.getLogger(__name__)


def _gemini_model():
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    return genai.GenerativeModel("gemini-2.0-flash", system_instruction=_SYSTEM)

_SYSTEM = """\
You are a job-fit screener. Given a job description and a candidate profile,
decide whether the candidate meets the MINIMUM (not preferred) requirements.

Rules (apply in order):
1. HARD SKIP if min years required > candidate years + 2. A candidate with 3 years cannot
   apply to a role requiring 6+, 8+, 10+ years. No exceptions.
2. HARD SKIP if the JD requires a PhD and candidate has none.
3. HARD SKIP if the JD requires active security clearance.
4. HARD SKIP if the JD requires team/people management ("lead a team of X", "manage engineers").
5. Small stretch is OK: 3 years can apply to "3-5 years" or "up to 5 years preferred" roles.
   Only stretch when the word "preferred" or "nice to have" is used, NOT "required"/"must".

Respond ONLY with a JSON object — no markdown, no explanation:
{
  "verdict": "apply" | "skip",
  "min_years_required": <integer or null>,
  "hard_blockers": ["..."],   // list of specific hard requirements not met, empty if apply
  "reason": "one sentence"
}"""


def _build_prompt(jd_text: str, years_experience: int) -> str:
    jd_snippet = jd_text[:3000].strip()
    return (
        f"Candidate: {years_experience} years of experience in data science / ML / AI.\n"
        f"No PhD. No active security clearance.\n\n"
        f"Job description (first 3000 chars):\n{jd_snippet}\n\n"
        f"Assess fit."
    )


def _parse_response(text: str) -> dict:
    """Extract JSON from the model response robustly."""
    text = text.strip()
    # Strip markdown fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def assess_fit(jd_text: str, client=None, years_experience: int = None) -> dict:
    """
    Assess whether the candidate fits the job based on the JD text.

    Args:
        jd_text:          Full or partial job description text.
        client:           Anthropic client instance.
        years_experience: Candidate's years of experience (reads from config if None).

    Returns:
        {
            "skip":      bool,   # True → skip tailoring
            "reason":    str,    # one-sentence explanation
            "min_years": int | None,
        }
        On any error → {"skip": False, "reason": "filter error", "min_years": None}
        so the pipeline always continues.
    """
    if not jd_text or len(jd_text.strip()) < 100:
        return {"skip": False, "reason": "jd too short to assess", "min_years": None}

    if years_experience is None:
        try:
            from config import YOUR_YEARS_EXPERIENCE
            years_experience = YOUR_YEARS_EXPERIENCE
        except ImportError:
            years_experience = 3

    # Fast pre-check: regex for obvious year overrequirements before calling Gemini
    yr_matches = re.findall(r'(\d+)\+?\s*years?\s+(?:of\s+)?(?:relevant\s+)?(?:engineering\s+|work\s+)?experience', jd_text[:3000], re.IGNORECASE)
    if yr_matches:
        max_required = max(int(y) for y in yr_matches)
        if max_required > years_experience + 2:
            reason = f"requires {max_required}+ years, candidate has {years_experience}"
            logger.info("Fit filter fast-skip (regex): %s", reason)
            return {"skip": True, "reason": reason, "min_years": max_required}

    try:
        model = _gemini_model()
        response = model.generate_content(_build_prompt(jd_text, years_experience))
        raw = response.text
        parsed = _parse_response(raw)

        verdict  = parsed.get("verdict", "apply")
        reason   = parsed.get("reason", "")
        min_yrs  = parsed.get("min_years_required")
        blockers = parsed.get("hard_blockers", [])

        skip = verdict == "skip"
        if skip:
            logger.info("Fit filter SKIP: %s | blockers: %s", reason, blockers)
        else:
            logger.debug("Fit filter APPLY: %s", reason)

        return {
            "skip":      skip,
            "reason":    reason,
            "min_years": min_yrs,
        }

    except Exception as e:
        logger.warning("Fit filter error (non-fatal, proceeding): %s", e)
        return {"skip": False, "reason": f"filter error: {e}", "min_years": None}
