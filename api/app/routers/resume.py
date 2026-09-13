from fastapi import APIRouter, HTTPException, Query
from app.services.resume_service import parse_resume, generate_docx, generate_pdf, get_active_profile
from app.services.llm import tailor_resume
from app.services.database import save_job, save_analysis, save_application
from pathlib import Path
import os

router = APIRouter()

@router.post("/parse")
def parse(payload: dict):
    return parse_resume(payload["path"])

@router.get("/current")
def current(refresh: bool = Query(False, description="Force re-inference even if the active resume hasn't changed.")):
    try:
        return get_active_profile(force_refresh=refresh)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
