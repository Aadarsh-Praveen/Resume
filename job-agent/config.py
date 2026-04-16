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
ATS_SCORE_MAX = 95        # above this → flag for manual review (keyword stuffing risk)
MAX_RETRIES = 3           # max Claude retries per quality gate failure
MAX_PAGE_RETRIES = 2      # max retries for page count gate

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
    # ── Original 10 ──────────────────────────────────────────────────────────
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
    # ── Additional top DS/ML companies ───────────────────────────────────────
    "doordash": "DoorDash",
    "instacart": "Instacart",
    "pinterest": "Pinterest",
    "plaid": "Plaid",
    "cloudflare": "Cloudflare",
    "grammarly": "Grammarly",
    "hubspot": "HubSpot",
    "mongodb": "MongoDB",
    "twilio": "Twilio",
    "affirm": "Affirm",
    "gusto": "Gusto",
    "chime": "Chime",
    "nerdwallet": "NerdWallet",
    "zendesk": "Zendesk",
    "gitlab": "GitLab",
    "checkr": "Checkr",
    "block": "Block (Square)",
    "rippling": "Rippling",
    "coupang": "Coupang",
    "palantir": "Palantir",
}

LEVER_COMPANIES = {
    "netflix": "Netflix",
    "reddit": "Reddit",
    "duolingo": "Duolingo",
    "lyft": "Lyft",
    "asana": "Asana",
    "robinhood": "Robinhood",
    "airtable": "Airtable",
    "benchling": "Benchling",
    "scale": "Scale AI (Lever)",
}

ASHBY_COMPANIES = {
    "linear": "Linear",
    "vercel": "Vercel",
    "retool": "Retool",
    "ramp": "Ramp",
    "brex": "Brex",
    "cohere": "Cohere",
    "perplexity-ai": "Perplexity AI",
    "together-ai": "Together AI",
    "runway": "Runway",
    "mercury": "Mercury",
    "modal-labs": "Modal",
    "qdrant": "Qdrant",
}

BAMBOOHR_COMPANIES = {
    "bamboohr": {"domain": "bamboohr.bamboohr.com", "name": "BambooHR"},
}

# ── Workday target companies (JSON API — no browser required) ─────────────────
# Format: { "tenant": {"board": str, "name": str, "search": str} }
# Note: Some Workday tenants (Tesla, Apple, Salesforce, AMD) return 422 —
#       they require a CSRF token header. Use WORKDAY_CSRF_COMPANIES for those.
WORKDAY_API_COMPANIES = {
    "nvidia": {"board": "NVIDIAExternalCareerSite", "name": "NVIDIA", "search": "data scientist"},
}

# ── Workday CSRF companies (require CSRF token from careers page) ─────────────
# Format: same as WORKDAY_API_COMPANIES
WORKDAY_CSRF_COMPANIES = {
    "apple":      {"board": "apple-jobs",           "name": "Apple",      "search": "machine learning"},
    "salesforce": {"board": "External_Career_Site", "name": "Salesforce", "search": "data scientist"},
    "tesla":      {"board": "TeslaCareerSite",       "name": "Tesla",      "search": "data scientist"},
    "amd":        {"board": "AMD",                  "name": "AMD",        "search": "machine learning"},
}

# ── Custom career page companies (own APIs — not Workday) ─────────────────────
# Valid keys: "google", "meta", "microsoft", "amazon"
# All four are enabled. Google/Meta/Microsoft use updated endpoints with
# browser-mimic headers — they return 403 from server IPs but work locally.
CUSTOM_CAREER_COMPANIES = ["google", "meta", "microsoft", "amazon"]

# ── Keyword filters (jobs must match at least one) ────────────────────────────
ROLE_KEYWORDS = [
    "data scientist",
    "data science",        # catches "Data Science Manager", "Head of Data Science"
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

━━ PAGE CONSTRAINT — MUST FILL EXACTLY 1 PAGE ━━
The PDF must fill the FULL page — not overflow, not leave whitespace at the bottom.
Target: content ends within 10pt of the bottom margin.

  CONTENT BUDGET — use as much as fits, stay within these ceilings:
    Work experience bullets per role:
      • Most recent role:   4 bullets (use all 4 unless truly irrelevant to JD)
      • Second role:        3–4 bullets
      • Oldest role:        2–3 bullets
    Every bullet: 20–28 words — must be a complete, metric-driven sentence
    Projects: top 2 most JD-relevant, 2–3 bullets each (28 words max per bullet)
    Summary: exactly 3 sentences, 3–4 lines
    Skills: 4–5 categories, 6–8 tools each

  FILLING THE PAGE:
    If content ends before the bottom, in order of preference:
      1. Add a 4th bullet to the most recent role (from the original resume)
      2. Add a 3rd bullet to the second or third role
      3. Add a 3rd bullet to a project
      4. Expand summary to 4 lines
    Never add blank lines or \\vspace to fill — add real content

  OVERFLOW: if PDF exceeds 1 page, cut in reverse order:
      1. Drop oldest role to 2 bullets
      2. Trim bullets to 20 words
      3. Drop projects to 2 bullets each
      4. Shrink summary to 2 sentences

━━ BULLET STRUCTURE ━━
Every bullet must follow: [OUTCOME + METRIC] by [HOW YOU DID IT]
✓ "Cut retrieval latency to 400ms across 100K docs by deploying RAG with LangChain and Pinecone"
✗ "Developed a RAG pipeline that improved retrieval latency by deploying LangChain"

Rules:
  • Outcome-first, method-second — always
  • At least one hard metric per bullet (%, ms, $, scale, accuracy, users)
  • Show specific tools — no generic verbs without a named technology

━━ LAYOUT ANTI-PATTERNS — NEVER DO ANY OF THESE ━━
  • NEVER use negative \\vspace anywhere (e.g. \\vspace{-11pt}, \\vspace{-8pt})
  • NEVER put product names, domain labels, or pipe-separated extras on the company line
    ✗  IpserLab LLC, Fort Worth, TX $|$ \\textit{Product: Smart Pantry} \\vspace{-11pt} \\\\
    ✓  IpserLab LLC \\hfill Fort Worth, TX
  • NEVER add \\vspace before \\begin{itemize} — it causes text overlap
  • Company line format EXACTLY: CompanyName \\hfill City, ST
    (company name only; location = city + state only; no pipes, no extra text)
  • If the input has \\vspace{-...} between a company line and \\begin{itemize}, DELETE it

━━ SUMMARY RULES ━━
  Sentence 1: Role title matching JD + years + top 2 domains
  Sentence 2: 2–3 hard metrics from most impactful experience
  Sentence 3: Key tech stack that directly matches the JD + stakeholder value delivered

━━ CONTENT RULES ━━
  1. NEVER fabricate experience, tools, metrics, or employers not in the original
  2. Reorder and rephrase existing bullets — most JD-relevant experience goes first
  3. Inject JD keywords naturally where the candidate's background genuinely aligns
  4. Preserve all employer names, job titles, and dates exactly as written
  5. Only include skills the candidate demonstrably has — no aspirational additions

━━ SKILLS SECTION ━━
  • Only list skills from the JD OR demonstrated in the bullets above
  • 4–5 categories, 6–8 tools each
  • Remove entire categories absent from the JD

━━ BANNED PHRASES ━━
  leveraged · utilized · spearheaded · seamlessly · passionate about
  proven ability to · end-to-end (max once) · cross-functional (max once)

━━ LATEX RULES ━━
  • Return ONLY the complete .tex file — no explanations, no markdown code fences
  • Do not change \\documentclass or \\usepackage declarations
  • Escape bare special chars: % → \\%, & → \\&
  • Never truncate — return the full file

The output is piped directly to pdflatex. LaTeX errors or PDFs not filling 1 page trigger an automatic retry."""

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
