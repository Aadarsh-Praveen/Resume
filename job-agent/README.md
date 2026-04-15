# Job Application Agent

An automated pipeline that finds relevant job postings, tailors your resume for each one using Claude AI, enforces quality gates, and sends you a Telegram alert with the ready-to-send PDF.

---

## What it does

```
Job Sources → Deduplicate → Extract JD → Tailor Resume (Claude)
     → Compile PDF (pdflatex) → ATS Score Check → Find Recruiter
     → Log to Notion → Send Telegram Alert
```

1. **Collects jobs** from 5 sources: Indeed RSS, Greenhouse, Lever, Ashby, and LinkedIn email alerts (Gmail)
2. **Filters** duplicates (SQLite), wrong roles, wrong location, and postings that require more years of experience than you have
3. **Rewrites your resume** using Claude (claude-sonnet-4-6) — emphasising relevant keywords from the JD without fabricating anything
4. **Compiles the PDF** with `pdflatex` and checks it is exactly 1 page
5. **Scores the PDF** against the JD keywords (target: 89–93% ATS match)
6. **Retries automatically** if the score is too low or the PDF overflows a page
7. **Finds the recruiter** at that company via Apollo.io and drafts a 3-sentence cold email
8. **Logs the application** to your Notion database
9. **Sends a Telegram alert** with a preview image of the PDF, ATS score, and the cold email draft

---

## Prerequisites

| Tool | Purpose | Install |
|---|---|---|
| Python 3.11+ | Runtime | `python3 --version` |
| `pdflatex` | Compile `.tex` → PDF | `sudo apt install texlive-latex-extra` |
| `pdftotext` | Extract PDF text for ATS scoring | `sudo apt install poppler-utils` |
| `pdfinfo` | Count PDF pages | Included with `poppler-utils` |
| `pdftoppm` | Render PDF preview image for Telegram | Included with `poppler-utils` |

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/aadarsh-praveen/Resume.git
cd Resume/job-agent
pip install -r requirements.txt
playwright install chromium   # for Workday scraping (optional)
```

### 2. Create your `.env` file

Copy the example and fill in your keys:

```bash
cp .env.example .env
```

Open `.env` and fill in each value — see the [API Keys](#api-keys) section below.

### 3. Add your base resume

Replace `base_resume.tex` with your own LaTeX resume. The agent rewrites this file for every job. Keep it to **1 page** — the quality gate will reject anything longer.

If you don't have a LaTeX resume, the included `base_resume.tex` is a working template you can customise.

### 4. Run

```bash
# One full cycle (collect + process all new jobs)
python agent.py

# Run continuously on a schedule (every 4h + Gmail every 15min)
python agent.py --daemon

# Collect jobs only (no tailoring yet)
python agent.py --collect

# Process already-collected jobs
python agent.py --process

# Test the pipeline with a synthetic JD (no real API calls for jobs)
python agent.py --test-job

# Send the daily Telegram digest right now
python agent.py --digest
```

---

## API Keys

### Required

**`ANTHROPIC_API_KEY`** — Powers resume tailoring and keyword extraction.
- Get it at: `console.anthropic.com` → API Keys

**`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`** — Where alerts are sent.
1. Message `@BotFather` on Telegram → `/newbot` → copy the token
2. Message your new bot once, then visit:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   Find `"chat": {"id": 123456789}` — that's your chat ID

### Strongly recommended

**`NOTION_API_KEY` + `NOTION_DATABASE_ID`** — Tracks every application.
1. Go to `notion.so/profile/integrations` → **New integration** → copy the `secret_xxx` key
2. Create a Notion database with these exact property names and types:

   | Property | Notion type |
   |---|---|
   | Name | Title |
   | Company | Text |
   | JD URL | URL |
   | Email | Email |
   | Date | Date |
   | Resume File | Text |
   | ATS Score | Number |
   | Status | Select (options: `ready`, `low_ats`, `high_ats`, `failed`) |
   | Notes | Text |

3. Open the database → `...` → **Connect to** → select your integration
4. Copy the database ID from the URL: `notion.so/workspace/<DATABASE_ID>?v=...`

### Optional

**`APOLLO_API_KEY`** — Finds the recruiter's email + LinkedIn for each company.
- Sign up at `apollo.io` → Settings → Integrations → API → Create API Key (free tier works)

**`GMAIL_CREDENTIALS_PATH` + `GMAIL_TOKEN_PATH`** — Parses LinkedIn job alert emails.
1. Enable Gmail API at `console.cloud.google.com` → APIs & Services
2. Create OAuth2 credentials (Desktop App) → download as `credentials.json`
3. Set `GMAIL_CREDENTIALS_PATH=/path/to/credentials.json`
4. On first run, a browser window opens for you to log in — after that, a token is saved automatically

**`APPLICANT_EMAIL` + `APPLICANT_NAME`** — Your name/email used in the Notion tracker and cold email drafts.

---

## Configuration (`config.py`)

All targeting rules live in `config.py`. You don't need to touch any other file to change what jobs are collected.

```python
# Which job titles to accept
TARGET_ROLES = [
    "Data Scientist", "ML Engineer", "AI Engineer", ...
]

# How many years of experience you have
YOUR_YEARS_EXPERIENCE = 3

# Skip jobs that require more than this many years (0 = no filter)
YOE_MAX_FILTER = 5   # allows 5-yr stretch roles for a 3-yr candidate

# ATS score target range (89–93%)
# Below 89 → Claude retries with missing keywords injected
# Above 93 → flagged as keyword stuffing risk
ATS_SCORE_MIN = 89
ATS_SCORE_MAX = 93

# Companies to poll directly via their ATS API
GREENHOUSE_COMPANIES = { "stripe": "Stripe", "openai": "OpenAI", ... }
LEVER_COMPANIES      = { "netflix": "Netflix", "reddit": "Reddit", ... }
ASHBY_COMPANIES      = { "linear": "Linear", "ramp": "Ramp", ... }

# Keywords a job title or description must contain
ROLE_KEYWORDS = ["data scientist", "machine learning", "ml engineer", ...]

# Keywords that disqualify a job
EXCLUDE_KEYWORDS = ["director", "vp ", "data engineer", ...]
```

---

## Project structure

```
job-agent/
├── agent.py                  ← main entry point + scheduler
├── config.py                 ← all targeting and tuning knobs
├── base_resume.tex           ← your LaTeX resume (replace this)
├── requirements.txt
├── .env.example              ← template — copy to .env and fill in
│
├── sources/                  ← job collection
│   ├── indeed_rss.py         ← Indeed RSS feed parser
│   ├── greenhouse_api.py     ← Greenhouse public API
│   ├── lever_api.py          ← Lever public API
│   ├── ashby_api.py          ← Ashby public API
│   ├── email_parser.py       ← Gmail → LinkedIn alert parser
│   └── workday_scraper.py    ← Playwright scraper (Phase 5)
│
├── pipeline/                 ← processing
│   ├── dedup.py              ← SQLite deduplication + job state
│   ├── jd_extractor.py       ← fetch + clean JD text from URL
│   ├── tailor_resume.py      ← Claude API: rewrite resume for JD
│   ├── latex_compiler.py     ← pdflatex wrapper + page count + preview
│   ├── ats_scorer.py         ← keyword extraction + ATS score
│   └── quality_gate.py       ← orchestrates all quality checks + retries
│
├── outputs/                  ← notifications + tracking
│   ├── tracker.py            ← Notion database logger
│   ├── telegram_alert.py     ← Telegram bot alerts + daily digest
│   └── recruiter_finder.py   ← Apollo.io lookup + cold email via Claude
│
├── tests/                    ← unit tests (run with pytest)
├── db/                       ← SQLite database (auto-created, gitignored)
└── resumes/                  ← compiled PDFs (auto-created, gitignored)
```

---

## How the ATS scoring works

The agent uses a two-step weighted scoring formula:

1. **Extract keywords** — Claude reads the JD and returns two lists: `required` (must-have skills listed in core responsibilities or "required" sections) and `preferred` (nice-to-haves).

2. **Score the PDF** — `pdftotext` extracts the plain text of the compiled PDF, then each keyword is checked:

   ```
   score = (2 × required_found + preferred_found)
           ────────────────────────────────────────  × 100
           (2 × required_total + preferred_total)
   ```

   Required keywords count double so the score is dominated by must-have skills.

3. **Quality gates:**
   - Score < 89% → Claude retries with the missing keywords injected into the prompt
   - Score > 93% → flagged as possible keyword stuffing (still saved, marked `high_ats`)
   - Score 89–93% → marked `ready`

---

## How the YOE filter works

After fetching each job's full description, the agent scans the **Requirements / Qualifications** sections for patterns like:

- `5+ years` → requires 5
- `3-5 years` → requires 3 (lower bound)
- `at least 4 years` → requires 4
- `minimum of 6 years` → requires 6

If the minimum required years exceeds `YOE_MAX_FILTER` (default: 5), the job is skipped and logged. Set `YOE_MAX_FILTER = 0` in `config.py` to disable this filter.

---

## Running tests

```bash
cd job-agent
python -m pytest tests/ -v
```

134 tests, 7 skipped (the 7 require `pdflatex`/`pdftoppm` to be installed on the machine — they pass in production).

---

## Folder layout for generated files

```
job-agent/
├── resumes/
│   ├── 42_stripe_senior_data_scientist.pdf   ← job #42
│   ├── 43_netflix_ml_engineer.pdf
│   └── ...
├── db/
│   └── jobs.db    ← SQLite: every job seen, its status, ATS score, PDF path
└── agent.log      ← full run log
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `base_resume.tex not found` | Make sure `base_resume.tex` is in the `job-agent/` directory |
| `pdflatex: command not found` | `sudo apt install texlive-latex-extra` |
| `pdftotext: command not found` | `sudo apt install poppler-utils` |
| Telegram alerts not arriving | Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` — message the bot first |
| Notion rows not appearing | Confirm the integration is connected to the database (database `...` → Connect to) |
| ATS score always 0 | `pdftotext` can't read the PDF — check `pdflatex` compiled successfully |
| Gmail auth browser doesn't open | Run `python agent.py` locally once to complete OAuth; the token file is reused after that |
