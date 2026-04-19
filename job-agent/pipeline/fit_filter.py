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

import anthropic

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM = """\
You are a job-fit screener. Given a job description and a candidate profile,
decide whether the candidate meets the MINIMUM (not preferred) requirements.

Be pragmatic: 3 years experience can stretch to roles requiring "3-5 years".
Only hard-block when the JD uses unambiguous language: "required", "must have",
"minimum X years", "PhD required", "active clearance required".

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


def assess_fit(jd_text: str, client: Optional[anthropic.Anthropic] = None, years_experience: int = None) -> dict:
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

    if client is None:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    try:
        msg = client.messages.create(
            model=_MODEL,
            max_tokens=256,
            system=_SYSTEM,
            messages=[{"role": "user", "content": _build_prompt(jd_text, years_experience)}],
        )
        raw = msg.content[0].text
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
