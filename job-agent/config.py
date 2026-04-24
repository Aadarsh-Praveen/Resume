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
ATS_SCORE_MAX = 100       # no upper cap — higher score = better match, never block
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
    # ── Data science ─────────────────────────────────────────────────────────
    {"keywords": "data scientist",                       "location": "United States"},
    {"keywords": "senior data scientist",                "location": "United States"},
    {"keywords": "staff data scientist",                 "location": "United States"},
    {"keywords": "data science manager",                 "location": "United States"},
    # ── ML / AI engineering ───────────────────────────────────────────────────
    {"keywords": "machine learning engineer",            "location": "United States"},
    {"keywords": "senior machine learning engineer",     "location": "United States"},
    {"keywords": "ml engineer",                          "location": "United States"},
    {"keywords": "ai engineer",                          "location": "United States"},
    {"keywords": "senior ai engineer",                   "location": "United States"},
    # ── Applied / research ────────────────────────────────────────────────────
    {"keywords": "applied scientist",                    "location": "United States"},
    {"keywords": "research scientist machine learning",  "location": "United States"},
    {"keywords": "nlp engineer",                         "location": "United States"},
    {"keywords": "deep learning engineer",               "location": "United States"},
    {"keywords": "llm engineer",                         "location": "United States"},
    # ── Remote variants ───────────────────────────────────────────────────────
    {"keywords": "data scientist",                       "location": "Remote"},
    {"keywords": "machine learning engineer",            "location": "Remote"},
    {"keywords": "ai engineer",                          "location": "Remote"},
    # ── Top hubs (some companies post only to metro pages) ────────────────────
    {"keywords": "data scientist",                       "location": "San Francisco Bay Area"},
    {"keywords": "machine learning engineer",            "location": "New York City Metropolitan Area"},
    {"keywords": "data scientist",                       "location": "Seattle, Washington"},
]

LINKEDIN_MAX_PAGES   = 4    # pages per query (25 results/page = up to 100 jobs/query)
LINKEDIN_PAGE_DELAY  = 2.0  # seconds between page requests within a query
LINKEDIN_QUERY_DELAY = 3.0  # seconds between queries

# ── Target companies for Greenhouse / Lever / Ashby APIs ─────────────────────
# Format: { "slug": {"ats": "greenhouse|lever|ashby|bamboohr", "name": "Display Name"} }
GREENHOUSE_COMPANIES = {
    # ── Core AI/ML product companies ─────────────────────────────────────────
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
    # ── Big tech / high DS-ML hiring ─────────────────────────────────────────
    "spotify": "Spotify",
    "uber": "Uber",
    "dropbox": "Dropbox",
    "snap": "Snap",
    "discord": "Discord",
    "roblox": "Roblox",
    "box": "Box",
    "zoom": "Zoom",
    "okta": "Okta",
    "hashicorp": "HashiCorp",
    "pagerduty": "PagerDuty",
    "elastic": "Elastic",
    "fastly": "Fastly",
    "intercom": "Intercom",
    "miro": "Miro",
    "loom": "Loom",
    "clickup": "ClickUp",
    "procore": "Procore",
    "samsara": "Samsara",
    "flexport": "Flexport",
    "navan": "Navan",
    "toast": "Toast",
    "adyen": "Adyen",
    "servicenow": "ServiceNow",
    "postman": "Postman",
    "algolia": "Algolia",
    "cloudinary": "Cloudinary",
    "contentful": "Contentful",
    "celonis": "Celonis",
    "collibra": "Collibra",
    # ── Data/ML infrastructure ────────────────────────────────────────────────
    "datadog": "Datadog",
    "confluent": "Confluent",
    "dbt-labs": "dbt Labs",
    "fivetran": "Fivetran",
    "labelbox": "Labelbox",
    "roboflow": "Roboflow",
    "amplitude": "Amplitude",
    "mixpanel": "Mixpanel",
    "launchdarkly": "LaunchDarkly",
    "statsig": "Statsig",
    "glean": "Glean",
    "moveworks": "Moveworks",
    # ── Security / infra ──────────────────────────────────────────────────────
    "snyk": "Snyk",
    "lacework": "Lacework",
    "wiz-inc": "Wiz",
    "rubrik": "Rubrik",
    # ── AI / robotics / autonomy ──────────────────────────────────────────────
    "appliedintuition": "Applied Intuition",
    "shieldai": "Shield AI",
    "covariant": "Covariant",
    "recursionpharma": "Recursion Pharmaceuticals",
    "tempus": "Tempus",
    "insitro": "Insitro",
    "skild-ai": "Skild AI",
    # ── Biotech / pharma on Greenhouse ───────────────────────────────────────
    "modernatx": "Moderna",
    "ginkgobioworks": "Ginkgo Bioworks",
    "biosplice": "BioSplice Therapeutics",
    # ── Additional tech ───────────────────────────────────────────────────────
    "duolingo": "Duolingo",
    "brainly": "Brainly",
    "quora": "Quora",
    "canva": "Canva",
    "notion-so": "Notion",
    "vercel": "Vercel",
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
    "huggingface": "HuggingFace",
    "mistral": "Mistral AI",
    "anyscale": "Anyscale",
    "weights-biases": "Weights & Biases",
    "replit": "Replit",
    "zapier": "Zapier",
    "carta": "Carta",
    "nuro": "Nuro",
    # ── Additional ───────────────────────────────────────────────────────────
    "coursera": "Coursera",
    "udemy": "Udemy",
    "headspace": "Headspace",
    "qualtrics": "Qualtrics",
    "veeva": "Veeva Systems",
    "figureai": "Figure AI",
    "imbue": "Imbue",
    "adept": "Adept AI",
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
    "elevenlabs": "ElevenLabs",
    "midjourney": "Midjourney",
    "pika": "Pika Labs",
    "characterai": "Character.AI",
    "inflection-ai": "Inflection AI",
    # ── Additional AI-first startups on Ashby ────────────────────────────────
    "physical-intelligence": "Physical Intelligence",
    "cognition-labs": "Cognition (Devin)",
    "twelve-labs": "Twelve Labs",
    "luma-ai": "Luma AI",
    "magic": "Magic AI",
    "sierra-ai": "Sierra AI",
    "poolside": "Poolside",
    "nabla": "Nabla",
    "fixie-ai": "Fixie AI",
    "contextual-ai": "Contextual AI",
    "imbue": "Imbue (Ashby)",
    "sakana-ai": "Sakana AI",
    "xai": "xAI",
    "moonhub": "Moonhub",
    "abridge": "Abridge",
    "laion": "LAION",
}

BAMBOOHR_COMPANIES = {
    "bamboohr": {"domain": "bamboohr.bamboohr.com", "name": "BambooHR"},
}

# ── Workday target companies (JSON API — no browser required) ─────────────────
# Format: { "tenant": {"board": str, "name": str, "search": str} }
# Note: Some Workday tenants (Tesla, Apple, Salesforce, AMD) return 422 —
#       they require a CSRF token header. Use WORKDAY_CSRF_COMPANIES for those.
WORKDAY_API_COMPANIES = {
    "nvidia":               {"board": "NVIDIAExternalCareerSite",  "name": "NVIDIA",                   "search": "data scientist"},
    "bristolmyerssquibb":   {"board": "bristolmyerssquibb",        "name": "Bristol Myers Squibb",      "search": "data scientist"},
    "jnjcareers":           {"board": "jnjcareers",                "name": "Johnson & Johnson",         "search": "data scientist"},
    "pfizer":               {"board": "pfizer",                    "name": "Pfizer",                   "search": "data scientist"},
    "msd":                  {"board": "msd",                       "name": "Merck",                    "search": "machine learning"},
    "roche":                {"board": "roche",                     "name": "Genentech / Roche",        "search": "data scientist"},
    "astrazeneca":          {"board": "astrazeneca",               "name": "AstraZeneca",              "search": "data scientist"},
    "abbvie":               {"board": "abbvie",                    "name": "AbbVie",                   "search": "data scientist"},
    "adobe":                {"board": "adobe",                     "name": "Adobe",                    "search": "machine learning"},
    "intuit":               {"board": "intuit",                    "name": "Intuit",                   "search": "data scientist"},
    "workday":              {"board": "workday",                   "name": "Workday",                  "search": "data scientist"},
    "walmart":              {"board": "walmart",                   "name": "Walmart",                  "search": "data scientist"},
    "target":               {"board": "target",                    "name": "Target",                   "search": "data scientist"},
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

━━ SECTIONS TO INCLUDE — IN THIS EXACT ORDER ━━
  1. Header (name + contact)
  2. Summary
  3. Skills
  4. Work Experience
  5. Projects
  6. Education  ← always last
  DO NOT include Certifications, Publications, or any other section.
  Certifications and Publications overflow the 1-page budget — omit them entirely.

━━ CONTENT BUDGET — FIXED TARGETS ━━
  Work experience bullets per role (use exactly these counts):
    • Most recent role:   4 bullets
    • Second role:        3 bullets
    • Third/oldest role:  3 bullets
  Every bullet: 20–28 words — must be a complete, metric-driven sentence.
  Projects: top 2 most JD-relevant, 3 bullets each (28 words max per bullet).
  Summary: 3 sentences, 3–4 lines when compiled — never exceed 4 lines.
  Skills: exactly 4 categories, 6–7 tools each.

  These targets are calibrated to fill exactly 1 A4 page at 10pt with 0.25in margins on all sides.
  Do NOT deviate from these counts — deviating causes under- or over-fill.

━━ BULLET STRUCTURE ━━
Every bullet must follow: [OUTCOME + METRIC] by [HOW YOU DID IT]
✓ "Cut retrieval latency to 400ms across 100K docs by deploying RAG with LangChain and Pinecone"
✗ "Developed a RAG pipeline that improved retrieval latency by deploying LangChain"

Rules:
  • Outcome-first, method-second — always
  • At least one hard metric per bullet (%, ms, $, scale, accuracy, users)
  • Show specific tools — no generic verbs without a named technology
  • No widow lines: if a bullet wraps to 2 lines, the second line must contain
    at least 8 words. Rephrase or extend the bullet to avoid 2–5 word orphan endings.

━━ BOLD KEYWORDS ━━
  • Use \\textbf{} to bold 2–4 JD-relevant technical terms per job/project section
  • Only bold: tool names, library names, technologies, key metrics — never verbs or filler words
  • Never bold the same word twice within the same job or project section
  • Never bold more than 4 terms per section — less is more
  • Examples: \\textbf{PyTorch}, \\textbf{Kubernetes}, \\textbf{85\\% accuracy}, \\textbf{LangChain}

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
  Hard limit: 3–4 compiled lines — if it wraps to 5+ lines, shorten sentence 2 or 3.

━━ CONTENT RULES ━━
  1. NEVER fabricate experience, tools, metrics, or employers not in the original
  2. Reorder and rephrase existing bullets — most JD-relevant experience goes first
  3. Inject JD keywords naturally where the candidate's background genuinely aligns
  4. Preserve all employer names, job titles, and dates exactly as written
  5. Only include skills the candidate demonstrably has — no aspirational additions

━━ SKILLS SECTION ━━
  • Only list skills from the JD OR demonstrated in the bullets above
  • Exactly 4 categories, 6–7 tools each
  • Remove entire categories absent from the JD

━━ BANNED PHRASES ━━
  leveraged · utilized · spearheaded · seamlessly · passionate about
  proven ability to · end-to-end (max once) · cross-functional (max once)

━━ LATEX RULES ━━
  • Return ONLY the complete .tex file — no explanations, no markdown code fences
  • Do not change \\documentclass or \\usepackage declarations
  • Escape bare special chars: % → \\%, & → \\&
  • Never truncate — return the full file

The output is piped directly to pdflatex. LaTeX errors or page-count failures trigger an automatic retry."""

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
