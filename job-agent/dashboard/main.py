"""
FastAPI dashboard for the job application agent.

Routes:
    GET  /                      All jobs feed (HTML)
    GET  /pending               Jobs awaiting approval (HTML)
    GET  /history               Applied / rejected jobs (HTML)
    GET  /job/{id}/resume       Serve the tailored PDF
    POST /approve/{id}          Approve → trigger auto-apply
    POST /reject/{id}           Mark rejected
    POST /run                   Trigger GitHub Actions workflow_dispatch

    GET  /api/profile           Applicant profile (JSON)
    GET  /api/stats             Job counts (JSON)
    GET  /api/jobs              Paginated job list (JSON)
    GET  /api/recruiters        Recruiter list + stats (JSON)
    GET  /api/analytics/weekly  Weekly submission counts (JSON)
    GET  /api/analytics/ats     ATS score distribution (JSON)
    GET  /api/analytics/funnel  Application funnel (JSON)
    GET  /api/analytics/portals Portal mix (JSON)
"""

import os
import sys
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

# Allow running from repo root or from job-agent/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

load_dotenv()

from pipeline.dedup import (
    init_db, get_job, get_all_jobs, get_pending_review_jobs,
    get_stats, set_approval, mark_applied,
    get_all_recruiters, get_recruiter_stats,
    get_weekly_submissions, get_ats_distribution, get_funnel_data, get_portal_mix,
)
from pipeline.auto_apply import apply_job

logger = logging.getLogger(__name__)

DB_PATH   = os.getenv("DB_PATH", "db/jobs.db")
RESUMES_DIR = os.getenv("RESUMES_DIR", "resumes")

GITHUB_TOKEN = os.getenv("GITHUB_DASHBOARD_TOKEN", "")
GITHUB_REPO  = os.getenv("GITHUB_REPO", "aadarsh-praveen/resume")


# ── App setup ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(DB_PATH)
    yield

app = FastAPI(title="Job Agent Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:3001", "http://127.0.0.1:3001",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_HERE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")
templates = Jinja2Templates(directory=str(_HERE / "templates"))


# ── Helper ────────────────────────────────────────────────────────────────────

def _badge(status: str) -> str:
    mapping = {
        "pending_review": "badge-warning",
        "approved":       "badge-info",
        "applied":        "badge-success",
        "rejected":       "badge-error",
    }
    return mapping.get(status or "", "badge-neutral")


def _source_icon(source: str) -> str:
    icons = {
        "greenhouse":         "🏠",
        "lever":              "⚙️",
        "ashby":              "🔷",
        "workday":            "🏢",
        "linkedin":           "💼",
        "indeed_rss":         "🔍",
        "himalayas":          "🏔️",
        "google_careers":     "🔵",
        "meta_careers":       "📘",
        "microsoft_careers":  "🪟",
        "amazon_jobs":        "📦",
    }
    return icons.get(source or "", "📋")


templates.env.globals["badge_class"] = _badge
templates.env.globals["source_icon"] = _source_icon


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, page: int = 1, filter: str = ""):
    limit  = 25
    offset = (page - 1) * limit
    jobs   = get_all_jobs(limit=limit, offset=offset, approval_status=filter or None, db_path=DB_PATH)
    stats  = get_stats(DB_PATH)
    return templates.TemplateResponse(
        request=request,
        name="jobs.html",
        context={"jobs": jobs, "stats": stats, "page": page, "filter": filter, "active": "all"},
    )


@app.get("/pending", response_class=HTMLResponse)
async def pending(request: Request):
    jobs  = get_pending_review_jobs(DB_PATH)
    stats = get_stats(DB_PATH)
    return templates.TemplateResponse(
        request=request,
        name="pending.html",
        context={"jobs": jobs, "stats": stats, "active": "pending"},
    )


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request, page: int = 1):
    limit  = 25
    offset = (page - 1) * limit
    applied  = get_all_jobs(limit=limit, offset=offset, approval_status="applied",  db_path=DB_PATH)
    rejected = get_all_jobs(limit=20,    offset=0,      approval_status="rejected", db_path=DB_PATH)
    stats    = get_stats(DB_PATH)
    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={"applied": applied, "rejected": rejected, "stats": stats, "page": page, "active": "history"},
    )


@app.get("/job/{job_id}/resume")
async def serve_resume(job_id: int):
    job = get_job(job_id, DB_PATH)
    if not job or not job.get("pdf_path"):
        raise HTTPException(404, "Resume not found")
    pdf_path = job["pdf_path"]
    if not os.path.exists(pdf_path):
        raise HTTPException(404, f"PDF file missing: {pdf_path}")
    return FileResponse(pdf_path, media_type="application/pdf",
                        filename=f"{job['company']}_{job['title']}.pdf".replace(" ", "_"))


@app.post("/approve/{job_id}")
async def approve(job_id: int):
    job = get_job(job_id, DB_PATH)
    if not job:
        raise HTTPException(404, "Job not found")

    success, application_id = apply_job(job)
    if success:
        mark_applied(job_id, application_id, DB_PATH)
        logger.info("Applied to %s @ %s — ID: %s", job["title"], job["company"], application_id)
    else:
        set_approval(job_id, "approved", DB_PATH)
        logger.warning("Auto-apply failed for job %d — marked approved, needs manual submit", job_id)

    return RedirectResponse("/pending", status_code=303)


@app.post("/reject/{job_id}")
async def reject(job_id: int):
    job = get_job(job_id, DB_PATH)
    if not job:
        raise HTTPException(404, "Job not found")
    set_approval(job_id, "rejected", DB_PATH)
    return RedirectResponse("/pending", status_code=303)


@app.post("/run")
async def manual_run(request: Request, mode: str = Form(default="full")):
    """Trigger a GitHub Actions workflow_dispatch run."""
    import requests as req

    if not GITHUB_TOKEN:
        return templates.TemplateResponse(
            request=request,
            name="jobs.html",
            context={
                "jobs": [], "stats": get_stats(DB_PATH), "page": 1, "filter": "",
                "active": "all", "error": "GITHUB_DASHBOARD_TOKEN not set in .env",
            },
        )

    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/agent.yml/dispatches"
    resp = req.post(
        url,
        json={"ref": "main", "inputs": {"mode": mode}},
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
        },
        timeout=10,
    )
    if resp.status_code == 204:
        logger.info("Triggered GitHub Actions workflow (mode=%s)", mode)
    else:
        logger.warning("workflow_dispatch failed: %d %s", resp.status_code, resp.text)

    return RedirectResponse("/", status_code=303)


# ── JSON API (consumed by the React frontend) ─────────────────────────────────

@app.get("/api/profile")
async def api_profile():
    try:
        from config import YOUR_YEARS_EXPERIENCE, TARGET_ROLES
        years = YOUR_YEARS_EXPERIENCE
        roles = TARGET_ROLES
    except ImportError:
        years, roles = 0, []
    return JSONResponse({
        "name":             os.getenv("APPLICANT_NAME", ""),
        "email":            os.getenv("APPLICANT_EMAIL", ""),
        "role":             os.getenv("APPLICANT_ROLE", ", ".join(roles[:2]) if roles else ""),
        "location":         os.getenv("APPLICANT_LOCATION", ""),
        "phone":            os.getenv("APPLICANT_PHONE", ""),
        "linkedin":         os.getenv("APPLICANT_LINKEDIN", ""),
        "github":           os.getenv("APPLICANT_GITHUB", ""),
        "years_experience": years,
        "target_roles":     roles,
    })


@app.get("/api/stats")
async def api_stats():
    return JSONResponse(get_stats(DB_PATH))


@app.get("/api/jobs")
async def api_jobs(limit: int = 50, offset: int = 0, approval_status: str = ""):
    jobs = get_all_jobs(
        limit=limit, offset=offset,
        approval_status=approval_status or None,
        db_path=DB_PATH,
    )
    return JSONResponse(jobs)


@app.get("/api/recruiters")
async def api_recruiters(limit: int = 200, offset: int = 0):
    recruiters = get_all_recruiters(limit=limit, offset=offset, db_path=DB_PATH)
    stats = get_recruiter_stats(DB_PATH)
    return JSONResponse({"recruiters": recruiters, "stats": stats})


@app.get("/api/analytics/weekly")
async def api_weekly():
    return JSONResponse(get_weekly_submissions(db_path=DB_PATH))


@app.get("/api/analytics/ats")
async def api_ats():
    return JSONResponse(get_ats_distribution(db_path=DB_PATH))


@app.get("/api/analytics/funnel")
async def api_funnel():
    return JSONResponse(get_funnel_data(db_path=DB_PATH))


@app.get("/api/analytics/portals")
async def api_portals():
    return JSONResponse(get_portal_mix(db_path=DB_PATH))
