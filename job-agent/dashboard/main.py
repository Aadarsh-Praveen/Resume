"""
FastAPI dashboard for the job application agent.

Routes:
    GET  /                 All jobs feed
    GET  /pending          Jobs awaiting approval
    GET  /history          Applied / rejected jobs
    GET  /job/{id}/resume  Serve the tailored PDF
    POST /approve/{id}     Approve → trigger auto-apply
    POST /reject/{id}      Mark rejected
    POST /run              Trigger GitHub Actions workflow_dispatch
"""

import os
import sys
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

# Allow running from repo root or from job-agent/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

load_dotenv()

from pipeline.dedup import (
    init_db, get_job, get_all_jobs, get_pending_review_jobs,
    get_stats, set_approval, mark_applied,
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
    return templates.TemplateResponse("jobs.html", {
        "request": request,
        "jobs":    jobs,
        "stats":   stats,
        "page":    page,
        "filter":  filter,
        "active":  "all",
    })


@app.get("/pending", response_class=HTMLResponse)
async def pending(request: Request):
    jobs  = get_pending_review_jobs(DB_PATH)
    stats = get_stats(DB_PATH)
    return templates.TemplateResponse("pending.html", {
        "request": request,
        "jobs":    jobs,
        "stats":   stats,
        "active":  "pending",
    })


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request, page: int = 1):
    limit  = 25
    offset = (page - 1) * limit
    applied  = get_all_jobs(limit=limit, offset=offset, approval_status="applied",  db_path=DB_PATH)
    rejected = get_all_jobs(limit=20,    offset=0,      approval_status="rejected", db_path=DB_PATH)
    stats    = get_stats(DB_PATH)
    return templates.TemplateResponse("history.html", {
        "request":  request,
        "applied":  applied,
        "rejected": rejected,
        "stats":    stats,
        "page":     page,
        "active":   "history",
    })


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

    # Try to auto-apply; fall back to just marking approved
    success, application_id = apply_job(job)
    if success:
        mark_applied(job_id, application_id, DB_PATH)
        logger.info("Applied to %s @ %s — ID: %s", job["title"], job["company"], application_id)
    else:
        # Mark approved but not yet applied (user can open URL manually)
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
        return templates.TemplateResponse("error.html", {
            "request": request,
            "message": "GITHUB_DASHBOARD_TOKEN not set in .env — cannot trigger workflow.",
        })

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
