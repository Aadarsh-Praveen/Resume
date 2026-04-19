# Applyflow — AI Job Application Agent

An automated pipeline that finds relevant job postings, tailors your resume for each one using Claude AI, enforces quality gates, tracks recruiters, and gives you a dashboard to approve applications before they're submitted.

---

## What it does

```
Job Sources → Deduplicate → Extract JD → Tailor Resume (Claude)
     → Compile PDF (pdflatex) → ATS Score Check → Find Recruiter
     → Dashboard Review → Auto-Apply (Greenhouse / Lever)
     → Telegram Alert
```

1. **Collects jobs** from 8 sources: Indeed RSS, Greenhouse (~75 companies), Lever (~25), Ashby (~35), Workday (NVIDIA + Apple/Salesforce/Tesla/AMD via CSRF), LinkedIn email alerts (Gmail), and custom career pages (Google/Meta/Microsoft/Amazon)
2. **Filters** duplicates (SQLite), wrong roles, wrong location, and postings requiring more experience than you have
3. **Rewrites your resume** using Claude (claude-sonnet-4-6) — emphasising relevant keywords from the JD without fabricating anything
4. **Compiles the PDF** with `pdflatex` and enforces exactly 1 page (margin shrink + Claude Haiku visual validator)
5. **Scores the PDF** against JD keywords (target: 89–95% ATS match)
6. **Retries automatically** if the score is too low or the PDF overflows a page
7. **Finds the recruiter** via Hunter.io and drafts a 3-sentence cold email via Claude
8. **Dashboard** — review tailored resumes and approve/reject before any application is submitted
9. **Auto-applies** to Greenhouse and Lever roles on approval
10. **Sends a Telegram alert** with PDF preview, ATS score, and cold email draft

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
git clone https://github.com/aadarsh-praveen/resume.git
cd resume/job-agent
pip install -r requirements.txt
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Fill in each value — see the [API Keys](#api-keys) section below.

### 3. Add your base resume

Replace `job-agent/base_resume.tex` with your own LaTeX resume. Keep it to **1 page**.

### 4. Run the agent

```bash
cd job-agent

# One full cycle (collect + process all new jobs)
python agent.py

# Run continuously on a schedule (every 4h + Gmail every 15min)
python agent.py --daemon

# Collect jobs only (no tailoring yet)
python agent.py --collect

# Process already-collected jobs
python agent.py --process

# Test the pipeline with a synthetic JD
python agent.py --test-job
```

### 5. Run the dashboard

```bash
cd job-agent
uvicorn dashboard.main:app --reload --port 8000
# Open http://localhost:8000
```

---

## API Keys

### Required

**`ANTHROPIC_API_KEY`** — Resume tailoring and cold email drafting.
Get it at: `console.anthropic.com` → API Keys

**`TELEGRAM_TOKEN` + `TELEGRAM_CHAT_ID`** — Where alerts are sent.
1. Message `@BotFather` on Telegram → `/newbot` → copy the token
2. Message your bot once, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates` → find `"chat": {"id": ...}`

### Strongly recommended

**`HUNTER_API_KEY`** — Finds recruiter emails per company (Hunter.io free tier = 25 searches/month).

### Optional

**`GMAIL_CREDENTIALS_PATH`** — Parses LinkedIn job alert emails via Gmail API.
1. Enable Gmail API at `console.cloud.google.com` → Create OAuth2 credentials (Desktop App) → download as `credentials.json`
2. Run `python agent.py` locally once to complete OAuth

**`SHEETS_CREDENTIALS_JSON` + `SHEETS_SPREADSHEET_ID`** — Logs applications to Google Sheets.

**Applicant profile** (used in auto-apply form submissions):
```
APPLICANT_NAME=
APPLICANT_EMAIL=
APPLICANT_PHONE=
APPLICANT_LINKEDIN=
APPLICANT_GITHUB=
```

---

## Configuration (`job-agent/config.py`)

```python
TARGET_ROLES = ["Data Scientist", "ML Engineer", "AI Engineer", ...]
YOUR_YEARS_EXPERIENCE = 3
YOE_MAX_FILTER = 5        # skip jobs requiring more than 5 yrs
ATS_SCORE_MIN = 89        # retry if below
ATS_SCORE_MAX = 95        # flag if above (keyword stuffing risk)

GREENHOUSE_COMPANIES = { "stripe": "Stripe", "openai": "OpenAI", ... }  # 75+ companies
LEVER_COMPANIES      = { "netflix": "Netflix", "reddit": "Reddit", ... } # 25+ companies
ASHBY_COMPANIES      = { "linear": "Linear", "ramp": "Ramp", ... }       # 35+ companies
```

---

## Automated scheduling (self-hosted GitHub Actions runner)

See `job-agent/RUNNER_SETUP.md` for one-time setup to run the agent on your machine automatically every 5 hours via GitHub Actions cron — no server required.

The workflow at `.github/workflows/agent.yml` triggers on schedule and on manual `workflow_dispatch` (also triggerable from the dashboard).

---

## Project structure

```
resume/
├── .github/workflows/agent.yml   ← GitHub Actions (self-hosted runner)
├── .gitignore
├── README.md
└── job-agent/
    ├── agent.py                  ← main entry point + scheduler
    ├── config.py                 ← all targeting and tuning knobs
    ├── base_resume.tex           ← your LaTeX resume (replace this)
    ├── requirements.txt
    ├── RUNNER_SETUP.md           ← self-hosted runner setup guide
    │
    ├── sources/                  ← job collection
    │   ├── indeed_rss.py         ← Indeed RSS + Himalayas fallback
    │   ├── greenhouse_api.py     ← Greenhouse public API (75+ companies)
    │   ├── lever_api.py          ← Lever public API (25+ companies)
    │   ├── ashby_api.py          ← Ashby public API (35+ companies)
    │   ├── workday_api.py        ← Workday JSON API + CSRF support
    │   ├── email_parser.py       ← Gmail → LinkedIn alert parser
    │   ├── linkedin_jobs.py      ← LinkedIn direct search
    │   └── custom_careers.py     ← Google / Meta / Microsoft / Amazon
    │
    ├── pipeline/                 ← processing
    │   ├── dedup.py              ← SQLite: jobs + recruiters tables
    │   ├── jd_extractor.py       ← fetch + clean JD text from URL
    │   ├── tailor_resume.py      ← Claude API: rewrite resume for JD
    │   ├── latex_compiler.py     ← pdflatex wrapper + page count
    │   ├── ats_scorer.py         ← keyword extraction + ATS score
    │   ├── quality_gate.py       ← quality checks + retries
    │   └── auto_apply.py         ← Greenhouse + Lever form submission
    │
    ├── outputs/                  ← notifications + tracking
    │   ├── tracker.py            ← Google Sheets logger
    │   ├── telegram_alert.py     ← Telegram bot alerts
    │   └── recruiter_finder.py   ← Hunter.io lookup + cold email
    │
    ├── dashboard/                ← FastAPI web dashboard
    │   ├── main.py               ← routes (review, approve, reject, analytics)
    │   ├── templates/            ← Jinja2 HTML templates
    │   └── static/               ← CSS
    │
    ├── tests/                    ← unit tests (run with pytest)
    ├── db/                       ← SQLite database (auto-created, gitignored)
    └── resumes/                  ← compiled PDFs (auto-created, gitignored)
```

---

## Running tests

```bash
cd job-agent
python -m pytest tests/ -v
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `base_resume.tex not found` | Make sure `base_resume.tex` is in `job-agent/` |
| `pdflatex: command not found` | `sudo apt install texlive-latex-extra` |
| `pdftotext: command not found` | `sudo apt install poppler-utils` |
| Telegram alerts not arriving | Check `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` |
| ATS score always 0 | `pdftotext` can't read the PDF — check pdflatex compiled successfully |
| Gmail auth browser doesn't open | Run `python agent.py` locally once to complete OAuth |
