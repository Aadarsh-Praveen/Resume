# Applyflow — AI Job Application Agent

An automated pipeline that finds relevant job postings, tailors your resume for each one using Claude AI, enforces quality gates, tracks recruiters, and gives you a web dashboard to approve applications before anything is submitted.

---

## How it works

```
Job Sources → Deduplicate → Extract JD → LLM Fit Filter (Claude Haiku)
     → Tailor Resume (Claude Sonnet) → Compile PDF (pdflatex)
     → ATS Score Check → Find Recruiter → Dashboard Review
         ↓ You click Apply
     Auto-Apply (Greenhouse / Lever) → Telegram Alert
```

**The agent never submits anything without your approval.** Every tailored resume sits in the dashboard waiting for you to click Apply or Reject.

1. **Collects jobs** from 8 sources: LinkedIn direct search, LinkedIn Gmail alerts, Indeed RSS, Greenhouse (~75 companies), Lever (~25), Ashby (~35), Workday (NVIDIA, Apple, Salesforce, Tesla, AMD), and custom career pages (Google, Meta, Microsoft, Amazon)
2. **Filters** duplicates, wrong roles, wrong location, and postings requiring more experience than you have
3. **LLM fit screen** — Claude Haiku reads the JD and skips hard blockers (PhD required, 8+ years minimum, active clearance) before spending Sonnet tokens on tailoring
4. **Rewrites your resume** using Claude Sonnet — emphasising relevant keywords from the JD without fabricating anything
5. **Compiles the PDF** with `pdflatex` and enforces exactly 1 page
6. **Scores the PDF** against JD keywords (target: 89–95% ATS match) and retries automatically if too low
7. **Finds the recruiter** via Hunter.io and drafts a cold email via Claude
8. **Sends a Telegram alert** with PDF preview, ATS score, and cold email draft
9. **You approve** in the dashboard — auto-submits for Greenhouse/Lever, or gives you the link for everything else

---

## Prerequisites

| Tool | Purpose | Install |
|---|---|---|
| Python 3.11+ | Runtime | `python3 --version` |
| `pdflatex` | Compile `.tex` → PDF | `sudo apt install texlive-latex-extra` |
| `pdftotext` | Extract PDF text for ATS scoring | `sudo apt install poppler-utils` |
| `pdfinfo` | Count PDF pages | Included with `poppler-utils` |
| `pdftoppm` | Render PDF preview for Telegram | Included with `poppler-utils` |

---

## Quick start (local)

### 1. Clone and install

```bash
git clone https://github.com/aadarsh-praveen/resume.git
cd resume/job-agent
pip install -r requirements.txt
playwright install chromium   # needed for CSRF-protected Workday tenants
```

### 2. Create your `.env` file

```env
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Applicant profile (used in auto-apply form submissions)
APPLICANT_FIRST_NAME=Your
APPLICANT_LAST_NAME=Name
APPLICANT_EMAIL=you@example.com
APPLICANT_PHONE=+1 555 000 0000
APPLICANT_LINKEDIN_URL=https://linkedin.com/in/yourhandle
APPLICANT_GITHUB=https://github.com/yourhandle
APPLICANT_LOCATION=Boston, MA

# Dashboard password (leave blank to disable auth)
DASHBOARD_PASSWORD=yourpassword

# Optional — Telegram alerts
TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=

# Optional — recruiter finder
HUNTER_API_KEY=

# Optional — Gmail (LinkedIn alert emails)
GMAIL_CREDENTIALS_PATH=credentials.json

# Optional — Google Sheets logging
SHEETS_CREDENTIALS_JSON=
SHEETS_SPREADSHEET_ID=

# Database — leave blank for local SQLite, set for PostgreSQL (Neon/Railway)
DATABASE_URL=
DB_PATH=db/jobs.db
RESUMES_DIR=resumes
```

### 3. Add your resume

Replace `job-agent/base_resume.tex` with your own LaTeX resume. Keep it to **exactly 1 page**. This is the only file you edit when your experience changes — all future tailored resumes are generated from it.

```bash
# After editing, verify it compiles and fits one page
cd job-agent
pdflatex base_resume.tex
open base_resume.pdf
```

### 4. Run the agent

```bash
cd job-agent

# One full cycle (collect + tailor all new jobs)
python agent.py

# Run on a schedule (every 4h + Gmail every 15min)
python agent.py --daemon

# Collect jobs only (no tailoring)
python agent.py --collect

# Process already-collected jobs
python agent.py --process

# Test the pipeline with a synthetic JD
python agent.py --test-job
```

### 5. Open the dashboard

```bash
cd job-agent
uvicorn dashboard.main:app --reload --port 8000
# Open http://localhost:8000
```

---

## Updating your resume

Edit `job-agent/base_resume.tex` whenever you gain new experience, skills, or projects. Then:

```bash
cd job-agent
pdflatex base_resume.tex          # verify it still compiles to 1 page
git add base_resume.tex base_resume.pdf
git commit -m "Update resume"
git push origin main
```

All future agent runs automatically use the updated resume. Existing tailored PDFs in the tracker are unaffected.

---

## Cloud deployment (Railway + Neon PostgreSQL)

This gives you a publicly accessible dashboard and lets the agent run on a schedule via GitHub Actions.

### Database — Neon PostgreSQL

1. Create a free project at [neon.tech](https://neon.tech)
2. Copy the connection string — looks like `postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require`

### Dashboard — Railway

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub → select this repo
2. Add these environment variables in Railway settings:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Neon connection string |
| `DASHBOARD_PASSWORD` | Password to protect the dashboard |
| `ANTHROPIC_API_KEY` | Claude API key |
| `APPLICANT_FIRST_NAME` | Your first name |
| `APPLICANT_LAST_NAME` | Your last name |
| `APPLICANT_EMAIL` | Your email |
| `APPLICANT_PHONE` | Your phone |
| `APPLICANT_LINKEDIN_URL` | LinkedIn URL |

Railway auto-deploys from `main` on every push and uses `railway.toml` for the start command.

### GitHub Actions — automated agent runs

The workflow at `.github/workflows/agent.yml` runs every 5 hours on a **self-hosted runner** (your own machine) for a residential IP — important because LinkedIn blocks GitHub's hosted IPs.

**One-time runner setup:**

1. Go to your repo → Settings → Actions → Runners → **New self-hosted runner**
2. Follow the download and configure steps shown
3. Start the runner:
```bash
cd ~/actions-runner
./run.sh             # foreground
# or as a background service:
./svc.sh install && ./svc.sh start
```

**GitHub Secrets to add** (repo → Settings → Secrets → Actions):

| Secret | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key |
| `DATABASE_URL` | Neon connection string |
| `TELEGRAM_TOKEN` | (optional) Telegram bot token |
| `TELEGRAM_CHAT_ID` | (optional) Your chat ID |
| `HUNTER_API_KEY` | (optional) Hunter.io key |

**Trigger a run manually:** GitHub → Actions tab → Job Application Agent → **Run workflow**

---

## Approval workflow

```
Agent runs (GitHub Actions, 5am, 10am, 3pm, 8pm, 1am...)
  ↓
Telegram notification: "New resume ready — Generac | ATS 98 | PDF attached"
  ↓
Open Railway dashboard → All Tracked Jobs tab
  ↓
Review the PDF → click Apply or Reject
  ↓
Greenhouse/Lever jobs → auto-submitted by the agent
LinkedIn/Workday/Indeed jobs → you get the link, apply manually
```

The `Status` column in the tracker shows the exact state of every job:

| Status | Meaning |
|---|---|
| `Resume Ready` | Tailored and waiting for your decision |
| `Low ATS` | Resume prepared but scored below threshold |
| `Applied` | You clicked Apply |
| `Not Applied` | You clicked Reject |
| `Failed` | Tailoring crashed — see `agent.log` |
| `No JD` | Job description couldn't be fetched |
| `Skipped` | Fit filter determined you're underqualified |

---

## Configuration (`job-agent/config.py`)

The top of `config.py` has all the knobs:

```python
TARGET_ROLES = ["Data Scientist", "ML Engineer", "AI Engineer", ...]
YOUR_YEARS_EXPERIENCE = 3
YOE_MAX_FILTER = 5        # skip jobs requiring more than this many years
ATS_SCORE_MIN  = 89       # retry tailoring if ATS is below this
ATS_SCORE_MAX  = 95       # flag if above (keyword stuffing risk)

ROLE_KEYWORDS    = [...]  # job title must contain one of these
EXCLUDE_KEYWORDS = [...]  # job title must NOT contain any of these
LOCATION_FILTER  = True   # True = US + remote only

GREENHOUSE_COMPANIES = { "stripe": "Stripe", "openai": "OpenAI", ... }
LEVER_COMPANIES      = { "netflix": "Netflix", "reddit": "Reddit", ... }
ASHBY_COMPANIES      = { "linear": "Linear", "ramp": "Ramp", ... }
WORKDAY_API_COMPANIES  = { "nvidia": {...}, ... }
WORKDAY_CSRF_COMPANIES = { "tesla": {...}, "salesforce": {...}, ... }
```

---

## API keys

### Required
- **`ANTHROPIC_API_KEY`** — [console.anthropic.com](https://console.anthropic.com) → API Keys

### Telegram (strongly recommended — this is how you get notified)
1. Message `@BotFather` → `/newbot` → copy the token
2. Message your bot once, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` → find `"chat": {"id": ...}`

### Optional
- **`HUNTER_API_KEY`** — [hunter.io](https://hunter.io) free tier = 25 searches/month
- **Gmail** — Enable Gmail API at [console.cloud.google.com](https://console.cloud.google.com) → OAuth2 credentials (Desktop App) → download as `credentials.json` → run `python agent.py` once locally to complete OAuth

---

## Project structure

```
resume/
├── .github/workflows/agent.yml   ← GitHub Actions (self-hosted runner, every 5h)
├── railway.toml                  ← Railway deployment config
├── frontend/                     ← React dashboard (served by FastAPI)
│   ├── index.html
│   ├── styles.css
│   ├── favicon.svg
│   └── src/
│       ├── app.jsx               ← root app + auth + routing
│       ├── login.jsx             ← password login
│       ├── dashboard.jsx         ← overview + stats
│       ├── tracker.jsx           ← job tracker (approve / reject / status)
│       ├── recruiters.jsx        ← recruiter outreach tracker
│       ├── analytics.jsx         ← charts (ATS distribution, funnel, portals)
│       ├── chrome.jsx            ← sidebar + topbar
│       ├── data.jsx              ← API fetch layer
│       └── icons.jsx             ← icon set
└── job-agent/
    ├── agent.py                  ← main entry point + scheduler
    ├── config.py                 ← all targeting and tuning knobs
    ├── base_resume.tex           ← your LaTeX master resume (edit this)
    ├── requirements.txt
    ├── RUNNER_SETUP.md           ← self-hosted runner setup guide
    ├── sources/                  ← job collection
    │   ├── linkedin_jobs.py      ← LinkedIn direct search (guest API)
    │   ├── email_parser.py       ← Gmail → LinkedIn alert parser
    │   ├── indeed_rss.py
    │   ├── greenhouse_api.py
    │   ├── lever_api.py
    │   ├── ashby_api.py
    │   ├── workday_api.py        ← Workday JSON API + Playwright CSRF support
    │   └── custom_careers.py     ← Google / Meta / Microsoft / Amazon
    ├── pipeline/                 ← processing
    │   ├── dedup.py              ← SQLite + PostgreSQL dual-backend
    │   ├── jd_extractor.py       ← fetch + clean JD text
    │   ├── fit_filter.py         ← Claude Haiku quick qualification screen
    │   ├── tailor_resume.py      ← Claude Sonnet resume rewriter
    │   ├── latex_compiler.py     ← pdflatex wrapper + page count
    │   ├── ats_scorer.py         ← keyword extraction + ATS score
    │   ├── quality_gate.py       ← quality checks + retry logic
    │   └── auto_apply.py         ← Greenhouse + Lever form submission
    ├── outputs/                  ← notifications + tracking
    │   ├── tracker.py            ← Google Sheets logger
    │   ├── telegram_alert.py     ← Telegram bot alerts + PDF preview
    │   └── recruiter_finder.py   ← Hunter.io lookup + cold email draft
    └── dashboard/
        └── main.py               ← FastAPI backend (API + static file serving)
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `base_resume.tex not found` | Make sure `base_resume.tex` is in `job-agent/` |
| `pdflatex: command not found` | `sudo apt install texlive-latex-extra` |
| `pdftotext: command not found` | `sudo apt install poppler-utils` |
| Telegram alerts not arriving | Check `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` |
| ATS score always 0 | `pdftotext` can't read the PDF — check pdflatex compiled cleanly |
| Gmail auth browser won't open | Run `python agent.py` locally once to complete OAuth flow |
| Workday CSRF 422 errors | Run `playwright install chromium` once |
| `malloc double free` on macOS | `pip uninstall psycopg2-binary` — the project uses `pg8000` instead |
| Jobs disappear after approve | Restart the dashboard server to apply latest DB migrations |
| Dashboard shows blank page | Check that `DATABASE_URL` or `DB_PATH` is set correctly in `.env` |

---

## Running tests

```bash
cd job-agent
python -m pytest tests/ -v
```
