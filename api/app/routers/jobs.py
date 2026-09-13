from fastapi import APIRouter, HTTPException, Query
from app.models.job import Job
from app.services.normalizer import normalize_job
from app.services.validator import validate_url
from app.services.resume_service import get_active_profile
from app.services.llm import analyze_relevance, tailor_resume
from app.services.database import save_job, save_analysis, save_application
from app.services.resume_service import generate_docx, generate_pdf
from pathlib import Path
import os, uuid

router = APIRouter()

@router.post("/normalize")
def normalize(job: Job):
    return normalize_job(job.model_dump())

@router.post("/validate")
async def validate(payload: dict):
    result = await validate_url(payload.get("application_url"), source=payload.get("source"), external_id=payload.get("external_id"))
    merged = dict(payload.get("job") or payload)
    merged.pop("job", None)
    merged["validation"] = result
    return merged

@router.get("/profile")
def profile(refresh: bool = Query(False, description="Force re-inference even if the active resume hasn't changed.")):
    try:
        return get_active_profile(force_refresh=refresh)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@router.post("/analyze")
def analyze(payload: dict):
    job = payload.get("job", payload)
    resume = payload.get("resume")
    if not resume:
        try:
            resume = get_active_profile()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
    analysis = analyze_relevance(job, resume)
    return {"job": job, "resume": resume, "analysis": analysis}

@router.post("/tailor")
def tailor(payload: dict):
    job = payload["job"]
    resume = payload.get("resume")
    if not resume:
        try:
            resume = get_active_profile()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
    analysis = payload.get("analysis", {})
    tailored = tailor_resume(job, resume)
    return {"job": job, "resume": resume, "analysis": analysis, "tailored": tailored}

@router.post("/generate")
def generate(payload: dict):
    job = payload["job"]
    analysis = payload.get("analysis", {})
    tailored = payload["tailored"]
    safe_company = "".join(c for c in job.get("company", "company") if c.isalnum() or c in "-_ ").strip().replace(" ", "-")[:50]
    safe_title = "".join(c for c in job.get("title", "role") if c.isalnum() or c in "-_ ").strip().replace(" ", "-")[:60]
    stem = f"{safe_company}-{safe_title}-{uuid.uuid4().hex[:8]}"
    outdir = Path(os.getenv("OUTPUT_DIR", "/data/generated"))
    docx_path = generate_docx(tailored, str(outdir / f"{stem}.docx"))
    pdf_path = generate_pdf(tailored, str(outdir / f"{stem}.pdf"))
    return {"job": job, "analysis": analysis, "tailored": tailored, "docx_path": docx_path, "pdf_path": pdf_path}

@router.post("/save")
def save(payload: dict):
    job = payload["job"]
    validation = job.get("validation", {})
    job_id = save_job(job, validation)
    analysis = payload.get("analysis", {})
    save_analysis(job_id, analysis)
    if payload.get("docx_path") and payload.get("pdf_path"):
        save_application(job_id, job, analysis, payload["docx_path"], payload["pdf_path"])
    return {"saved": True, "job_id": job_id, "application_url": job.get("application_url"), "status": "RESUME_TAILORED" if payload.get("docx_path") else "ANALYZED"}
