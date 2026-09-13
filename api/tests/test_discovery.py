import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.services import discovery


def _now():
    return datetime.now(timezone.utc)


def make_transport():
    now = _now()
    recent = (now - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S")
    stale = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)

        if "remoteok.com/api" in url:
            return httpx.Response(200, json=[
                {"legal": "notice"},  # RemoteOK's real first element is not a job
                {
                    "id": "1001", "position": "Senior Flutter Engineer", "company": "Remote Flutter Co",
                    "description": "Build Flutter apps with Dart and Firebase.", "tags": ["flutter", "dart"],
                    "url": "https://remoteok.com/remote-jobs/1001", "date": recent, "location": "Worldwide",
                },
                {
                    "id": "1002", "position": "Senior Java Backend Engineer", "company": "Old Corp",
                    "description": "Java and Spring.", "tags": ["java"],
                    "url": "https://remoteok.com/remote-jobs/1002", "date": stale, "location": "Worldwide",
                },
            ])

        if "remotive.com/api/remote-jobs" in url:
            return httpx.Response(200, json={"jobs": [
                {
                    "id": 2001, "title": "Flutter Developer", "company_name": "Remotive Mobile",
                    "description": "Flutter and Riverpod experience wanted.",
                    "url": "https://remotive.com/jobs/2001", "candidate_required_location": "Worldwide",
                    "job_type": "full_time", "publication_date": recent,
                },
            ]})

        if "arbeitnow.com/api/job-board-api" in url:
            recent_ts = int((now - timedelta(hours=3)).timestamp())
            return httpx.Response(200, json={"data": [
                {
                    "slug": "flutter-berlin", "title": "Flutter Mobile Engineer", "company_name": "Arbeit Mobile GmbH",
                    "description": "Dart, Flutter, clean architecture.", "tags": ["flutter"],
                    "url": "https://www.arbeitnow.com/jobs/flutter-berlin", "remote": True,
                    "job_types": ["Full-time"], "created_at": recent_ts,
                },
            ]})

        if "boards-api.greenhouse.io" in url:
            return httpx.Response(200, json={"jobs": [
                {
                    "id": 3001, "title": "Senior Flutter Engineer (Remote)",
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/3001",
                    "content": "<p>Flutter role</p>", "location": {"name": "Remote"},
                    "updated_at": recent + "-00:00",
                },
            ]})

        if "api.lever.co" in url:
            created_ms = int((now - timedelta(hours=2)).timestamp() * 1000)
            return httpx.Response(200, json=[
                {
                    "id": "4001", "text": "Flutter Engineer", "descriptionPlain": "Flutter and Dart role.",
                    "hostedUrl": "https://jobs.lever.co/acme/4001", "applyUrl": "https://jobs.lever.co/acme/4001/apply",
                    "categories": {"location": "Remote", "commitment": "Full-time"}, "createdAt": created_ms,
                },
            ])

        return httpx.Response(404, json={})

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def patched_client(monkeypatch):
    transport = make_transport()
    real_client_cls = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client_cls(*args, **kwargs)

    monkeypatch.setattr(discovery.httpx, "AsyncClient", factory)
    yield


@pytest.mark.asyncio
async def test_fetch_remoteok_filters_by_keyword_and_parses_fields():
    async with discovery.httpx.AsyncClient() as client:
        jobs = await discovery.fetch_remoteok(client, ["flutter"])
    assert len(jobs) == 1
    job = jobs[0]
    assert job["company"] == "Remote Flutter Co"
    assert job["source"] == "remoteok"
    assert job["remote"] is True
    assert job["posted_at"] is not None


@pytest.mark.asyncio
async def test_fetch_remotive_and_arbeitnow():
    async with discovery.httpx.AsyncClient() as client:
        remotive_jobs = await discovery.fetch_remotive(client, ["flutter"])
        arbeitnow_jobs = await discovery.fetch_arbeitnow(client, ["flutter"])
    assert len(remotive_jobs) == 1
    assert remotive_jobs[0]["source"] == "remotive"
    assert len(arbeitnow_jobs) == 1
    assert arbeitnow_jobs[0]["source"] == "arbeitnow"
    assert arbeitnow_jobs[0]["remote"] is True


@pytest.mark.asyncio
async def test_fetch_greenhouse_and_lever_company_boards():
    async with discovery.httpx.AsyncClient() as client:
        gh_jobs = await discovery.fetch_greenhouse(client, "acme", ["flutter"])
        lever_jobs = await discovery.fetch_lever(client, "acme", ["flutter"])
    assert len(gh_jobs) == 1
    assert gh_jobs[0]["source"] == "greenhouse:acme"
    assert len(lever_jobs) == 1
    assert lever_jobs[0]["source"] == "lever:acme"
    assert lever_jobs[0]["application_url"].endswith("/apply")


@pytest.mark.asyncio
async def test_discover_jobs_orchestrates_all_sources_dedupes_and_filters_stale():
    jobs = await discovery.discover_jobs(
        keywords=["flutter"],
        max_age_days=3,
        remote_only=True,
        sources=["remoteok", "remotive", "arbeitnow", "greenhouse", "lever"],
    )
    # The stale Java job (30 days old) and the non-matching keyword must be excluded.
    sources_seen = {j["source"] for j in jobs}
    assert "remoteok" in sources_seen
    assert all("Old Corp" != j["company"] for j in jobs)
    # Results should be sorted most-recent-first.
    posted_dates = [j["posted_at"] for j in jobs]
    assert posted_dates == sorted(posted_dates, reverse=True)


def test_parse_dt_handles_seconds_millis_and_iso_strings():
    now = _now()
    from_seconds = discovery._parse_dt(int(now.timestamp()))
    from_millis = discovery._parse_dt(int(now.timestamp() * 1000))
    from_iso = discovery._parse_dt(now.isoformat())
    assert abs((from_seconds - now).total_seconds()) < 2
    assert abs((from_millis - now).total_seconds()) < 2
    assert abs((from_iso - now).total_seconds()) < 2
    assert discovery._parse_dt(None) is None
    assert discovery._parse_dt("not-a-date") is None


def test_load_default_keywords_falls_back_when_no_profile(monkeypatch):
    def raise_missing(*a, **k):
        raise FileNotFoundError("no resume")
    monkeypatch.setattr("app.services.resume_service.get_active_profile", raise_missing)
    assert discovery.load_default_keywords() == ["software engineer"]


def test_load_default_keywords_reads_active_profile(monkeypatch):
    def fake_profile(*a, **k):
        return {"headline": "Senior Mobile Engineer", "target_job_titles": ["Flutter Engineer", "Mobile Engineer"]}
    monkeypatch.setattr("app.services.resume_service.get_active_profile", fake_profile)
    keywords = discovery.load_default_keywords()
    assert keywords[0] == "Senior Mobile Engineer"
    assert "Flutter Engineer" in keywords


def test_load_default_keywords_adapts_to_a_completely_different_resume(monkeypatch):
    """The same code path should work for a Comms/PR resume with zero changes."""
    def fake_profile(*a, **k):
        return {"headline": "Senior Communications Manager", "target_job_titles": ["PR Manager", "Communications Director"]}
    monkeypatch.setattr("app.services.resume_service.get_active_profile", fake_profile)
    keywords = discovery.load_default_keywords()
    assert "Senior Communications Manager" in keywords
    assert "PR Manager" in keywords
    assert "Flutter" not in " ".join(keywords)
