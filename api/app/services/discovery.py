"""Real, multi-source job discovery.

JobLens deliberately does not scrape LinkedIn: LinkedIn has no free public
jobs API and its Terms of Service prohibit automated scraping/collection.
Instead this module aggregates postings from open, no-key-required job
board APIs, plus (optionally) public company ATS boards. The latter are
often the *canonical* listing anyway -- most aggregators, including
LinkedIn, are just mirroring what a company posted on its own Greenhouse
or Lever board -- so this can actually surface jobs faster and from more
companies than LinkedIn alone.

Sources implemented:
- RemoteOK   https://remoteok.com/api                              (no key)
- Remotive   https://remotive.com/api/remote-jobs                  (no key)
- Arbeitnow  https://www.arbeitnow.com/api/job-board-api           (no key)
- Greenhouse https://boards-api.greenhouse.io/v1/boards/{slug}/jobs (no key, per company)
- Lever      https://api.lever.co/v0/postings/{slug}?mode=json      (no key, per company)

Every result is normalized into the same shape as app.models.job.Job so it
can flow through the existing normalize -> validate -> analyze -> tailor ->
generate -> save pipeline unchanged.

Each fetcher is defensive: if a source is down, rate-limited, or changes
its schema slightly, that source contributes zero jobs instead of failing
the whole discovery run.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

USER_AGENT = "JobLens/0.3 (personal job-search automation; contact via profile)"
DEFAULT_TIMEOUT = 20.0

ALL_SOURCES = ("remoteok", "remotive", "arbeitnow", "greenhouse", "lever")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> Optional[datetime]:
    """Best-effort parse of the many date shapes job APIs use."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            ts = value / 1000 if value > 10**12 else value
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(value, str):
            v = value.strip()
            if v.isdigit():
                return _parse_dt(int(v))
            v = v.replace("Z", "+00:00")
            dt = datetime.fromisoformat(v)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
    except Exception:
        return None
    return None


def _normalize_title(value: str) -> str:
    import re
    value = re.sub(r"[^a-z0-9+#&/ -]+", " ", str(value or "").lower())
    return re.sub(r"\s+", " ", value).strip()


def _title_matches_keywords(title: str, keywords: list[str]) -> bool:
    """Match the job title to resume-derived roles without looking into the body.

    Exact phrase matches catch normal title variants. Token-overlap matching
    handles forms such as 'Senior Software Engineer, Mobile' vs 'Senior Mobile
    Engineer' while avoiding the old problem where an unrelated description
    mentioning a technology caused the job to be discovered.
    """
    if not keywords:
        return True
    title_norm = _normalize_title(title)
    if not title_norm:
        return False
    title_tokens = set(title_norm.replace("/", " ").replace("-", " ").split())
    stop = {"and", "or", "the", "of", "at", "for", "in", "a", "an"}
    title_tokens -= stop
    for keyword in keywords:
        kw = _normalize_title(keyword)
        if not kw:
            continue
        if kw in title_norm or title_norm in kw:
            return True
        kw_tokens = set(kw.replace("/", " ").replace("-", " ").split()) - stop
        if not kw_tokens:
            continue
        overlap = len(title_tokens & kw_tokens) / len(kw_tokens)
        if overlap >= 0.75:
            return True
    return False


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    """Backward-compatible text matcher for callers/tests; discovery uses title matching."""
    if not keywords:
        return True
    text = text.lower()
    return any(str(k).lower() in text for k in keywords if k)


def load_default_keywords() -> list[str]:
    """Derive discovery roles from the currently active resume.

    Optional JOB_SEARCH_FOCUS can temporarily steer a run (e.g. 'AI Engineering')
    without hard-coding a profession into JobLens. The resume remains the source
    of truth and the focus is only an additional hint.
    """
    try:
        from app.services.resume_service import get_active_profile
        profile = get_active_profile()
    except Exception:
        return ["software engineer"]

    keywords: list[str] = []
    focus = os.getenv("JOB_SEARCH_FOCUS", "").strip()
    headline = str(profile.get("headline") or "").strip()
    if headline:
        keywords.append(headline)
    if focus and focus.lower() not in {x.lower() for x in keywords}:
        keywords.append(focus)
    for value in profile.get("target_job_titles") or []:
        value = str(value).strip()
        if value and value.lower() not in {x.lower() for x in keywords}:
            keywords.append(value)
    return keywords[:10] or ["software engineer"]


def load_company_boards() -> dict:
    """User-configurable list of company ATS boards to pull directly.

    See data/user/company_boards.json.example.
    """
    path = Path(os.getenv("COMPANY_BOARDS_PATH", "/data/user/company_boards.json"))
    try:
        data = json.loads(path.read_text())
        return {
            "greenhouse": list(data.get("greenhouse", []) or []),
            "lever": list(data.get("lever", []) or []),
        }
    except Exception:
        return {"greenhouse": [], "lever": []}


async def _get_json(client: httpx.AsyncClient, url: str, params: dict | None = None) -> Any:
    try:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


async def fetch_remoteok(client: httpx.AsyncClient, keywords: list[str]) -> list[dict]:
    data = await _get_json(client, "https://remoteok.com/api")
    if not isinstance(data, list):
        return []
    jobs = []
    for item in data:
        # RemoteOK's first array element is a legal/notice object, not a job.
        if not isinstance(item, dict) or "id" not in item:
            continue
        title = item.get("position") or item.get("title") or ""
        company = item.get("company", "")
        description = item.get("description", "") or ""
        tags = " ".join(item.get("tags") or [])
        if not _title_matches_keywords(title, keywords):
            continue
        slug = item.get("slug") or item.get("id")
        url = item.get("url") or f"https://remoteok.com/remote-jobs/{slug}"
        jobs.append({
            "external_id": str(item.get("id")),
            "source": "remoteok",
            "source_url": url,
            "application_url": item.get("apply_url") or url,
            "company": company,
            "company_url": item.get("company_url"),
            "title": title,
            "description": description,
            "location": item.get("location") or "Remote",
            "remote": True,
            "employment_type": None,
            "posted_at": _parse_dt(item.get("date")),
        })
    return jobs


async def fetch_remotive(client: httpx.AsyncClient, keywords: list[str]) -> list[dict]:
    search = keywords[0] if keywords else None
    data = await _get_json(client, "https://remotive.com/api/remote-jobs", params={"search": search} if search else None)
    if not isinstance(data, dict):
        return []
    jobs = []
    for item in data.get("jobs", []) or []:
        title = item.get("title", "")
        description = item.get("description", "") or ""
        if not _title_matches_keywords(title, keywords):
            continue
        jobs.append({
            "external_id": str(item.get("id")),
            "source": "remotive",
            "source_url": item.get("url"),
            "application_url": item.get("url"),
            "company": item.get("company_name", ""),
            "company_url": item.get("company_logo_url"),
            "title": title,
            "description": description,
            "location": item.get("candidate_required_location") or "Remote",
            "remote": True,
            "employment_type": item.get("job_type"),
            "posted_at": _parse_dt(item.get("publication_date")),
        })
    return jobs


async def fetch_arbeitnow(client: httpx.AsyncClient, keywords: list[str]) -> list[dict]:
    data = await _get_json(client, "https://www.arbeitnow.com/api/job-board-api")
    if not isinstance(data, dict):
        return []
    jobs = []
    for item in data.get("data", []) or []:
        title = item.get("title", "")
        description = item.get("description", "") or ""
        tags = " ".join(item.get("tags") or [])
        if not _title_matches_keywords(title, keywords):
            continue
        remote = bool(item.get("remote"))
        jobs.append({
            "external_id": item.get("slug") or title,
            "source": "arbeitnow",
            "source_url": item.get("url"),
            "application_url": item.get("url"),
            "company": item.get("company_name", ""),
            "company_url": None,
            "title": title,
            "description": description,
            "location": item.get("location") or ("Remote" if remote else ""),
            "remote": remote,
            "employment_type": ",".join(item.get("job_types") or []) or None,
            "posted_at": _parse_dt(item.get("created_at")),
        })
    return jobs


async def fetch_greenhouse(client: httpx.AsyncClient, slug: str, keywords: list[str]) -> list[dict]:
    data = await _get_json(client, f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    if not isinstance(data, dict):
        return []
    jobs = []
    for item in data.get("jobs", []) or []:
        title = item.get("title", "")
        if not _title_matches_keywords(title, keywords):
            continue
        location_name = ((item.get("location") or {}).get("name")) or ""
        jobs.append({
            "external_id": str(item.get("id")),
            "source": f"greenhouse:{slug}",
            "source_url": item.get("absolute_url"),
            "application_url": item.get("absolute_url"),
            "company": slug,
            "company_url": None,
            "title": title,
            "description": (item.get("content") or "")[:6000],
            "location": location_name,
            "remote": "remote" in title.lower() or "remote" in location_name.lower(),
            "employment_type": None,
            "posted_at": _parse_dt(item.get("updated_at")),
        })
    return jobs


async def fetch_lever(client: httpx.AsyncClient, slug: str, keywords: list[str]) -> list[dict]:
    data = await _get_json(client, f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
    if not isinstance(data, list):
        return []
    jobs = []
    for item in data:
        title = item.get("text", "")
        description = item.get("descriptionPlain") or item.get("description") or ""
        if not _title_matches_keywords(title, keywords):
            continue
        categories = item.get("categories", {}) or {}
        location = categories.get("location") or ""
        jobs.append({
            "external_id": item.get("id") or title,
            "source": f"lever:{slug}",
            "source_url": item.get("hostedUrl"),
            "application_url": item.get("applyUrl") or item.get("hostedUrl"),
            "company": slug,
            "company_url": None,
            "title": title,
            "description": description[:6000],
            "location": location,
            "remote": "remote" in location.lower(),
            "employment_type": categories.get("commitment"),
            "posted_at": _parse_dt(item.get("createdAt")),
        })
    return jobs


async def discover_jobs(
    keywords: list[str] | None = None,
    max_age_days: int | None = 3,
    remote_only: bool = False,
    sources: list[str] | None = None,
) -> list[dict]:
    """Fetch, filter, dedupe and freshness-sort jobs from every enabled source."""
    keywords = keywords if keywords is not None else load_default_keywords()
    sources = [s.strip().lower() for s in (sources or ALL_SOURCES) if s.strip()]
    boards = load_company_boards()

    async with httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        tasks: list = []
        if "remoteok" in sources:
            tasks.append(fetch_remoteok(client, keywords))
        if "remotive" in sources:
            tasks.append(fetch_remotive(client, keywords))
        if "arbeitnow" in sources:
            tasks.append(fetch_arbeitnow(client, keywords))
        if "greenhouse" in sources:
            for slug in boards.get("greenhouse", []):
                tasks.append(fetch_greenhouse(client, slug, keywords))
        if "lever" in sources:
            for slug in boards.get("lever", []):
                tasks.append(fetch_lever(client, slug, keywords))

        results = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []

    all_jobs: list[dict] = []
    for r in results:
        if isinstance(r, Exception) or not r:
            continue
        all_jobs.extend(r)

    cutoff = _now() - timedelta(days=max_age_days) if max_age_days else None
    seen_keys: set[str] = set()
    filtered: list[dict] = []
    for job in all_jobs:
        if remote_only and not job.get("remote"):
            continue
        posted_at = job.get("posted_at")
        if cutoff and posted_at and posted_at < cutoff:
            continue
        key = (job.get("application_url") or f"{job.get('company','').lower()}|{job.get('title','').lower()}").strip().lower()
        if key in seen_keys:
            continue
        seen_keys.add(key)
        filtered.append(job)

    filtered.sort(key=lambda j: j.get("posted_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return filtered
