"""
Central configuration for the Job Application Agent.
Adjust TARGET_ROLES, SENIORITY_LEVELS, LOCATION_FILTER, and TARGET_COMPANIES
to match the roles you are targeting.
"""

# ── Role targeting ────────────────────────────────────────────────────────────
TARGET_ROLES = [
    "Data Scientist",
    "Senior Data Scientist",
    "Staff Data Scientist",
    "ML Engineer",
    "Machine Learning Engineer",
    "Senior ML Engineer",
    "AI Engineer",
    "Applied Scientist",
    "Research Scientist",
    "Data Science Manager",
]

SENIORITY_LEVELS = ["senior", "staff", "lead", "principal", "sr.", "sr "]

LOCATION_FILTER = "United States"  # Set to "" to disable location filtering

# ── Years-of-experience filter ────────────────────────────────────────────────
YOUR_YEARS_EXPERIENCE = 3          # your actual experience level

# Accepted experience range: 0 – 5 years required
# Jobs requiring more than YOE_MAX_FILTER years are skipped entirely.
# Set YOE_MAX_FILTER = 0 to disable the filter and collect all jobs.
YOE_MIN_FILTER = 0                 # no lower bound (include entry-level and above)
YOE_MAX_FILTER = 5                 # skip jobs requiring more than 5 years

# ── ATS quality gates ─────────────────────────────────────────────────────────
ATS_SCORE_MIN = 89        # below this → retry with missing keyword injection
ATS_SCORE_MAX = 93        # above this → flag for manual review (keyword stuffing risk)
MAX_RETRIES = 2           # max Claude retries per quality gate failure
MAX_PAGE_RETRIES = 1      # max retries for page count gate

# ── Scheduler ─────────────────────────────────────────────────────────────────
POLL_INTERVAL_HOURS = 4   # how often to poll job sources
GMAIL_POLL_MINUTES = 15   # how often to check Gmail for LinkedIn alerts
DAILY_DIGEST_HOUR = 9     # hour (24h) to send Telegram daily digest

# ── Indeed RSS search params ──────────────────────────────────────────────────
INDEED_QUERIES = [
    {"q": "data scientist", "l": "United States"},
    {"q": "machine learning engineer", "l": "United States"},
    {"q": "AI engineer", "l": "United States"},
]
INDEED_MAX_RESULTS = 25   # entries per RSS feed

# ── LinkedIn direct search queries ────────────────────────────────────────────
LINKEDIN_QUERIES = [
    {"keywords": "data scientist", "location": "United States"},
    {"keywords": "machine learning engineer", "location": "United States"},
    {"keywords": "AI engineer", "location": "United States"},
]

# ── Target companies for Greenhouse / Lever / Ashby APIs ─────────────────────
# Format: { "slug": {"ats": "greenhouse|lever|ashby|bamboohr", "name": "Display Name"} }
GREENHOUSE_COMPANIES = {
    "stripe": "Stripe",
    "airbnb": "Airbnb",
    "coinbase": "Coinbase",
    "figma": "Figma",
    "notion": "Notion",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "databricks": "Databricks",
    "snowflake": "Snowflake",
    "scale-ai": "Scale AI",
}

LEVER_COMPANIES = {
    "netflix": "Netflix",
    "reddit": "Reddit",
    "duolingo": "Duolingo",
    "lyft": "Lyft",
    "asana": "Asana",
}

ASHBY_COMPANIES = {
    "linear": "Linear",
    "vercel": "Vercel",
    "retool": "Retool",
    "ramp": "Ramp",
    "brex": "Brex",
}

BAMBOOHR_COMPANIES = {
    "bamboohr": {"domain": "bamboohr.bamboohr.com", "name": "BambooHR"},
}

# ── Workday target companies (JSON API — no browser required) ─────────────────
# Format: { "tenant": {"board": str, "name": str, "search": str} }
# Note: Some Workday tenants (Tesla, Apple, Salesforce, AMD) return 422 —
#       they require a CSRF token header not included here. Only NVIDIA is
#       confirmed working via unauthenticated POST.
WORKDAY_API_COMPANIES = {
    "nvidia": {"board": "NVIDIAExternalCareerSite", "name": "NVIDIA", "search": "data scientist"},
}

# ── Custom career page companies (own APIs — not Workday) ─────────────────────
# Valid keys: "google", "meta", "microsoft", "amazon"
# Note: google (404), meta (400), microsoft (DNS) are returning errors —
#       only "amazon" is confirmed working. Add others back when endpoints
#       are verified.
CUSTOM_CAREER_COMPANIES = ["amazon"]

# ── Keyword filters (jobs must match at least one) ────────────────────────────
ROLE_KEYWORDS = [
    "data scientist",
    "machine learning",
    "ml engineer",
    "ml infrastructure",
    "ai engineer",
    "applied scientist",
    "research scientist",
    "nlp",
    "deep learning",
    "llm",
    "large language model",
    " ml ",          # standalone "ML" in a title like "Senior ML Scientist"
    "ml/ai",
]

EXCLUDE_KEYWORDS = [
    "principal engineer",
    "director",
    "vp ",
    "vice president",
    "data analyst",      # separate from data scientist
    "business analyst",
    "data engineer",     # remove if you want these too
]

# ── Resume tailoring Claude prompt ───────────────────────────────────────────
TAILOR_SYSTEM_PROMPT = """You are a FAANG-level resume writer and ATS specialist. Tailor the provided LaTeX resume to the job description.

━━ PAGE CONSTRAINT — ABSOLUTE ━━
The compiled PDF must be exactly 1 page. Enforce this with these hard limits:

  Work experience bullets per role:
    • Most recent role:   3–4 bullets (based on JD alignment)
    • Second role:        3–4 bullets (based on JD alignment)
    • Oldest role:        3–4 bullets (based on JD alignment)
  Every bullet across ALL roles: maximum 25 words — count every word, split any bullet exceeding this limit
  Projects: keep top 2 most JD-relevant, 2 bullets each (add a 3rd only to cover a critical JD gap)
  Summary: exactly 3 sentences, 4 lines maximum

━━ BULLET STRUCTURE ━━
Every bullet must follow: [OUTCOME + METRIC] by [HOW YOU DID IT]
✓ "Cut retrieval latency to 400ms across 100K+ documents by deploying RAG with LangChain and Pinecone"
✗ "Developed a RAG pipeline that improved retrieval latency by deploying LangChain"

Rules:
  • Outcome-first, method-second — always
  • Include at least one metric per bullet (%, ms, scale, cost, accuracy, users)
  • Show specific tools, architecture decisions, and trade-offs
  • 2–3 bullets per role must reference a concrete decision or constraint

━━ SUMMARY RULES ━━
  Sentence 1: Role title matching JD + years + top 2 domains
  Sentence 2: 2–3 hard metrics from most relevant experience
  Sentence 3: Key technical stack + what you deliver for stakeholders

━━ CONTENT RULES ━━
  1. NEVER fabricate experience, tools, metrics, or employers not in the original
  2. Reorder and rephrase existing bullets — most JD-relevant experience goes first
  3. Inject JD keywords naturally where the candidate's background genuinely aligns
  4. Preserve all employer names, job titles, and dates exactly as written
  5. Only include skills the candidate demonstrably has — no aspirational additions

━━ SKILLS SECTION ━━
  • Only list skills from the JD OR skills demonstrated in the bullets above
  • Maximum 5 categories, 8 tools each
  • Note JD equivalents in brackets where applicable: "PostgreSQL (Redshift-compatible)"

━━ BANNED PHRASES (sound immediately AI-written) ━━
  leveraged · utilized · spearheaded · seamlessly · passionate about
  proven ability to · end-to-end (max once total) · cross-functional (max once total)
  owned (max once) · comfortable operating at the intersection of
  feedback-driven development cycles · generalizing insights into scalable capabilities

━━ LATEX RULES ━━
  • Return ONLY the complete .tex file — no explanations, no markdown code fences
  • Do not change \\documentclass or \\usepackage declarations
  • Escape bare special chars: % → \\%, & → \\&
  • Never truncate — return the full file

The output is piped directly to pdflatex. Any syntax error fails the quality gate. A PDF exceeding 1 page triggers an automatic retry."""

COLD_EMAIL_SYSTEM_PROMPT = """You are a professional email copywriter specialising in job application outreach.
Write a cold email from a job applicant to a recruiter/hiring manager.

Rules:
- Maximum 3 sentences
- Sentence 1: personalise with their name + company + specific role
- Sentence 2: one specific, quantified achievement from the applicant's background
- Sentence 3: clear call to action (ask to connect, not for a job)
- No subject line — just the body
- Sign off with the applicant's name
- Formal but warm tone — not sycophantic
- Never use: "I hope this finds you well", "I wanted to reach out", "circling back"
"""
