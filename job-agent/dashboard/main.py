"""
FastAPI backend for the job application agent.

Serves the React frontend (frontend/) at / and exposes a JSON API.

API routes:
    GET  /api/profile           Applicant profile
    GET  /api/stats             Job counts
    GET  /api/jobs              Paginated job list
    GET  /api/recruiters        Recruiter list + stats
    GET  /api/analytics/weekly  Weekly submission counts
    GET  /api/analytics/ats     ATS score distribution
    GET  /api/analytics/funnel  Application funnel
    GET  /api/analytics/portals Portal mix
    POST /api/approve/{id}      Approve job → trigger auto-apply
    POST /api/reject/{id}       Reject job
    POST /api/run               Trigger GitHub Actions workflow
    GET  /job/{id}/resume       Download tailored PDF
"""

import os
import sys
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

load_dotenv()

from pipeline.dedup import (
    init_db, get_job, get_all_jobs, get_pending_review_jobs,
    get_stats, set_approval, mark_applied, set_manual_review, set_application_status,
    get_all_recruiters, get_recruiter_stats, get_recruiter, update_recruiter,
    get_weekly_submissions, get_ats_distribution, get_funnel_data, get_portal_mix,
    get_jobs_with_pending_questions, get_pending_questions, answer_question,
    count_unanswered, delete_pending_questions,
    _USE_PG,
)
from pipeline.gcs import get_signed_url, is_gcs_uri
import threading
from pipeline.auto_apply import apply_job, submit_pending_answers
from outputs.telegram_alert import send_approval_alert, send_pending_questions_alert

logger = logging.getLogger(__name__)

DB_PATH     = os.getenv("DB_PATH", "db/jobs.db")
RESUMES_DIR = os.getenv("RESUMES_DIR", "resumes")
GITHUB_TOKEN = os.getenv("GITHUB_DASHBOARD_TOKEN", "")
GITHUB_REPO  = os.getenv("GITHUB_REPO", "aadarsh-praveen/resume")

_HERE     = Path(__file__).resolve().parent          # job-agent/dashboard/
_FRONTEND = _HERE.parent.parent / "frontend"         # resume/frontend/


# ── App setup ─────────────────────────────────────────────────────────────────

_DB_AVAILABLE = True
_DB_ERROR: str = ""

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _DB_AVAILABLE, _DB_ERROR
    try:
        init_db(DB_PATH)
        _DB_AVAILABLE = True
        _DB_ERROR = ""
    except Exception as e:
        _DB_AVAILABLE = False
        _DB_ERROR = str(e)
        logger.critical(
            "Database unavailable at startup (%s). Error: %s",
            "PostgreSQL" if _USE_PG else DB_PATH, e,
            exc_info=True,
        )
    yield

app = FastAPI(title="Applyflow", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def db_health_gate(request, call_next):
    """Return 503 for all /api/* routes when the database is unavailable."""
    if not _DB_AVAILABLE and request.url.path.startswith("/api/"):
        return JSONResponse(
            {"error": "Database unavailable — check Neon quota or DATABASE_URL"},
            status_code=503,
        )
    return await call_next(request)


# ── JSON API ──────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def api_health():
    import os
    db_url = os.getenv("DATABASE_URL", "")
    masked = (db_url[:40] + "...") if len(db_url) > 40 else db_url
    return JSONResponse({
        "db_available": _DB_AVAILABLE,
        "db_error": _DB_ERROR,
        "db_type": "PostgreSQL" if _USE_PG else "SQLite",
        "database_url_set": bool(db_url),
        "database_url_preview": masked,
    })


@app.get("/api/profile")
async def api_profile():
    try:
        from config import YOUR_YEARS_EXPERIENCE, TARGET_ROLES
        years = YOUR_YEARS_EXPERIENCE
        roles = TARGET_ROLES
    except ImportError:
        years, roles = 0, []
    return JSONResponse({
        "name":             os.getenv("APPLICANT_NAME", os.getenv("APPLICANT_FIRST_NAME", "")),
        "email":            os.getenv("APPLICANT_EMAIL", ""),
        "role":             os.getenv("APPLICANT_ROLE", ", ".join(roles[:2]) if roles else ""),
        "location":         os.getenv("APPLICANT_LOCATION", ""),
        "phone":            os.getenv("APPLICANT_PHONE", ""),
        "linkedin":         os.getenv("APPLICANT_LINKEDIN", os.getenv("APPLICANT_LINKEDIN_URL", "")),
        "github":           os.getenv("APPLICANT_GITHUB", ""),
        "years_experience": years,
        "target_roles":     roles,
    })


@app.get("/api/auth/check")
async def api_auth_check():
    """Returns whether a password is required."""
    return JSONResponse({"required": bool(os.getenv("DASHBOARD_PASSWORD", ""))})


@app.post("/api/auth/login")
async def api_auth_login(request: Request):
    """Verify dashboard password. If DASHBOARD_PASSWORD not set, always succeeds."""
    pwd = os.getenv("DASHBOARD_PASSWORD", "")
    if not pwd:
        return JSONResponse({"ok": True})
    body = await request.json()
    if body.get("password") == pwd:
        return JSONResponse({"ok": True})
    raise HTTPException(401, "Incorrect password")


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


@app.post("/api/jobs/{job_id}/set_application_status")
async def api_set_application_status(job_id: int, request: Request):
    job = get_job(job_id, DB_PATH)
    if not job:
        raise HTTPException(404, "Job not found")
    body = await request.json()
    status = body.get("status", "")
    allowed = {"", "Interviewing", "Accepted", "Rejected"}
    if status not in allowed:
        raise HTTPException(400, f"Invalid status '{status}'")
    set_application_status(job_id, status, DB_PATH)
    return JSONResponse({"application_status": status})


@app.post("/api/jobs/{job_id}/toggle_review")
async def api_toggle_review(job_id: int):
    job = get_job(job_id, DB_PATH)
    if not job:
        raise HTTPException(404, "Job not found")
    new_val = not bool(job.get("manual_review", 0))
    set_manual_review(job_id, new_val, DB_PATH)
    return JSONResponse({"manual_review": new_val})


@app.post("/api/recruiters/{recruiter_id}/toggle/{field}")
async def api_recruiter_toggle(recruiter_id: int, field: str):
    allowed = {"email_sent", "linkedin_sent", "replied"}
    if field not in allowed:
        raise HTTPException(400, f"Field '{field}' is not toggleable")
    rec = get_recruiter(recruiter_id, DB_PATH)
    if not rec:
        raise HTTPException(404, "Recruiter not found")
    new_val = 0 if rec.get(field) else 1
    update_recruiter(recruiter_id, field, new_val, DB_PATH)
    return JSONResponse({"field": field, "value": new_val})


@app.post("/api/recruiters/{recruiter_id}/set_replied_via")
async def api_set_replied_via(recruiter_id: int, request: Request):
    rec = get_recruiter(recruiter_id, DB_PATH)
    if not rec:
        raise HTTPException(404, "Recruiter not found")
    body = await request.json()
    via = body.get("via", "")
    update_recruiter(recruiter_id, "replied_via", via or None, DB_PATH)
    return JSONResponse({"replied_via": via})


@app.post("/api/approve/{job_id}")
async def api_approve(job_id: int):
    job = get_job(job_id, DB_PATH)
    if not job:
        raise HTTPException(404, "Job not found")

    result = apply_job(job)
    status = result["status"]

    if status == "applied":
        mark_applied(job_id, result["application_id"], DB_PATH)
        threading.Thread(
            target=send_approval_alert,
            args=(job, True, result["application_id"], []),
            daemon=True,
        ).start()
        return JSONResponse({"status": "applied", "application_id": result["application_id"]})

    if status == "pending_questions":
        # Don't mark applied yet — user must answer questions first
        set_approval(job_id, "pending_questions", DB_PATH)
        pending = get_pending_questions(job_id, DB_PATH)
        unanswered = [q for q in pending if q["answer"] is None]
        threading.Thread(
            target=send_pending_questions_alert,
            args=(job, len(unanswered)),
            daemon=True,
        ).start()
        return JSONResponse({
            "status": "pending_questions",
            "pending_count": len(unanswered),
            "questions": unanswered,
        })

    if status == "no_autoapply":
        mark_applied(job_id, None, DB_PATH)
        threading.Thread(
            target=send_approval_alert,
            args=(job, False, "", []),
            daemon=True,
        ).start()
        return JSONResponse({
            "status": "approved",
            "note": "auto-apply not supported — submit manually",
            "job_url": job.get("url", ""),
        })

    # failed
    mark_applied(job_id, None, DB_PATH)
    return JSONResponse({"status": "failed", "note": "auto-apply encountered an error"})


@app.get("/api/pending")
async def api_pending():
    """Return jobs that have unanswered questions waiting for user input."""
    jobs = get_jobs_with_pending_questions(DB_PATH)
    return JSONResponse(jobs)


@app.post("/api/pending/{job_id}/answer")
async def api_answer_question(job_id: int, request: Request):
    """Save one or more user-provided answers for a job's pending questions."""
    job = get_job(job_id, DB_PATH)
    if not job:
        raise HTTPException(404, "Job not found")
    body = await request.json()
    answers = body.get("answers", [])  # [{id: int, answer: str}, ...]
    for a in answers:
        answer_question(int(a["id"]), str(a["answer"]), DB_PATH)
    remaining = count_unanswered(job_id, DB_PATH)
    return JSONResponse({"saved": len(answers), "remaining": remaining})


@app.post("/api/pending/{job_id}/submit")
async def api_submit_pending(job_id: int, request: Request):
    """
    Save final answers then POST the Greenhouse application.
    Body: {answers: [{id, answer}, ...]}
    """
    job = get_job(job_id, DB_PATH)
    if not job:
        raise HTTPException(404, "Job not found")

    body = await request.json()
    answers = body.get("answers", [])
    for a in answers:
        answer_question(int(a["id"]), str(a["answer"]), DB_PATH)

    remaining = count_unanswered(job_id, DB_PATH)
    if remaining > 0:
        pending = get_pending_questions(job_id, DB_PATH)
        unanswered = [q for q in pending if q["answer"] is None]
        return JSONResponse({
            "status": "still_pending",
            "remaining": remaining,
            "questions": unanswered,
        })

    result = submit_pending_answers(job)
    if result["status"] == "applied":
        mark_applied(job_id, result["application_id"], DB_PATH)
        threading.Thread(
            target=send_approval_alert,
            args=(job, True, result["application_id"], []),
            daemon=True,
        ).start()
        return JSONResponse({"status": "applied", "application_id": result["application_id"]})

    return JSONResponse({"status": result["status"], "note": "Submission failed — try applying manually"})


@app.post("/api/reject/{job_id}")
async def api_reject(job_id: int):
    job = get_job(job_id, DB_PATH)
    if not job:
        raise HTTPException(404, "Job not found")
    set_approval(job_id, "rejected", DB_PATH)
    return JSONResponse({"status": "rejected"})


@app.post("/api/run")
async def api_run(request: Request):
    import requests as req
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    mode = body.get("mode", "full")
    if not GITHUB_TOKEN:
        raise HTTPException(400, "GITHUB_DASHBOARD_TOKEN not set in .env")
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/agent.yml/dispatches"
    resp = req.post(
        url,
        json={"ref": "main", "inputs": {"mode": mode}},
        headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"},
        timeout=10,
    )
    if resp.status_code == 204:
        return JSONResponse({"status": "triggered", "mode": mode})
    raise HTTPException(resp.status_code, f"GitHub API error: {resp.text}")


@app.get("/job/{job_id}/resume")
async def serve_resume(job_id: int):
    from fastapi.responses import RedirectResponse
    job = get_job(job_id, DB_PATH)
    if not job:
        raise HTTPException(404, "Job not found")

    pdf_path = job.get("pdf_path")
    if not pdf_path:
        raise HTTPException(404, "Resume not available yet")

    filename = f"{job['company']}_{job['title']}.pdf".replace(" ", "_")

    # GCS: redirect to a short-lived signed URL
    if is_gcs_uri(pdf_path):
        signed_url = get_signed_url(pdf_path)
        return RedirectResponse(url=signed_url)

    # Local filesystem fallback (SQLite / dev mode)
    if not os.path.exists(pdf_path):
        raise HTTPException(404, "PDF file not found")
    return FileResponse(pdf_path, media_type="application/pdf", filename=filename)


# ── Serve React frontend ───────────────────────────────────────────────────────
# Mount AFTER all API routes so /api/... is never shadowed.

if _FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")
else:
    logger.warning("Frontend directory not found at %s — serving API only", _FRONTEND)
