import logging

from fastapi import APIRouter, Query
from starlette.concurrency import run_in_threadpool

from app.services.discovery import ALL_SOURCES, discover_jobs, load_company_boards, load_default_keywords
from app.services.normalizer import content_hash
from app.services.database import get_seen_hashes

logger = logging.getLogger("joblens.discover")

router = APIRouter()


@router.get("/jobs")
async def discover(
    keywords: str | None = Query(
        None, description="Comma-separated search terms. Defaults to terms derived from your resume profile."
    ),
    max_age_days: int = Query(
        3, ge=0, le=90, description="Only include jobs posted within this many days. 0 disables the freshness filter."
    ),
    remote_only: bool = Query(False, description="Only include remote-eligible postings."),
    sources: str | None = Query(
        None, description=f"Comma-separated subset of: {','.join(ALL_SOURCES)}. Defaults to all."
    ),
    exclude_seen: bool = Query(
        True, description="Skip jobs already stored in the database, so the daily run doesn't re-tailor the same job repeatedly."
    ),
    focus: str | None = Query(None, description="Optional temporary job-search focus, e.g. AI Engineering or Communications. Does not alter the active resume."),
):
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else None
    if focus and focus.strip():
        inferred = load_default_keywords() if kw_list is None else kw_list
        kw_list = [focus.strip()] + [k for k in inferred if k.lower() != focus.strip().lower()]
    src_list = [s.strip() for s in sources.split(",") if s.strip()] if sources else None

    jobs = await discover_jobs(
        keywords=kw_list,
        max_age_days=max_age_days or None,
        remote_only=remote_only,
        sources=src_list,
    )

    for job in jobs:
        job["content_hash"] = content_hash(job.get("company", ""), job.get("title", ""), job.get("description", ""))

    if exclude_seen and jobs:
        hashes = [j["content_hash"] for j in jobs]
        try:
            seen = await run_in_threadpool(get_seen_hashes, hashes)
        except Exception as exc:
            # Best-effort: if the database isn't reachable yet, don't fail discovery over it.
            logger.warning("could not check seen-jobs, returning unfiltered results: %s", exc)
            seen = set()
        jobs = [j for j in jobs if j["content_hash"] not in seen]

    return jobs


@router.get("/keywords")
def default_keywords():
    """What search terms discovery will use if you don't pass ?keywords=."""
    return {"keywords": load_default_keywords()}


@router.get("/config")
def config():
    """Currently configured company ATS boards (Greenhouse/Lever)."""
    return {"sources": list(ALL_SOURCES), "company_boards": load_company_boards()}
