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

# ── Workday target companies (Phase 5 — Playwright scraping) ──────────────────
WORKDAY_COMPANIES = [
    {
        "name": "Louis Vuitton",
        "url": "https://careers.louisvuitton.com/eng",
        "keywords": ["data", "scientist", "analyst", "ml", "machine learning"],
    },
    {
        "name": "Google",
        "url": "https://careers.google.com/jobs/results/?q=data+scientist",
        "keywords": ["data scientist", "ml engineer"],
    },
    {
        "name": "Meta",
        "url": "https://www.metacareers.com/jobs?q=data+scientist",
        "keywords": ["data scientist", "ml"],
    },
]

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
TAILOR_SYSTEM_PROMPT = """You are an expert resume writer and ATS optimization specialist.
Your job is to tailor a LaTeX resume to a specific job description while:

1. NEVER fabricating experience, skills, or achievements that aren't in the original
2. Reordering and rephrasing existing bullets to emphasize most relevant experience
3. Adding JD keywords naturally into existing bullets where accurate
4. Ensuring the resume compiles to exactly 1 page
5. Keeping all LaTeX formatting valid and compilable with pdflatex
6. Preserving all employer names, job titles, and dates exactly as-is

CRITICAL RULES:
- Return ONLY the complete .tex file content — no explanations, no markdown code blocks
- Do not add \\usepackage or document class changes unless fixing a compile error
- Escape all special LaTeX characters: % → \\%, & → \\&, $ → \\$, # → \\#, _ → \\_
- Never truncate the output — return the full .tex file

The output will be directly passed to pdflatex. Any LaTeX error means the resume fails quality gates."""

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
