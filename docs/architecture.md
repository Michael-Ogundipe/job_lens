# JobLens Architecture

## Core principle

Discovery sources are not authoritative. The authoritative source is the actual company application/ATS page where possible.

The **active resume is the single source of truth for the candidate side of the pipeline too**. There's no separate hand-maintained profile config: `app/services/resume_service.get_active_profile()` parses whichever file is at `BASE_RESUME_PATH` and infers both the job-role search terms and the structured candidate data from it, caching the result until the file changes. Swapping personas is a file replacement, not a config change.

## Components

### n8n

Coordinates the workflow, makes the stages visible, and triggers it both on demand (Manual Trigger), automatically once a day (Schedule Trigger), and on ad-hoc submission (Manual Job Inbox webhook, for jobs found by hand on LinkedIn or elsewhere) so new postings are picked up every day without a person running it.

### FastAPI

Provides deterministic helper functionality:
- **real job discovery** (`app/services/discovery.py`) across RemoteOK, Remotive, Arbeitnow, and optional per-company Greenhouse/Lever boards — deliberately not LinkedIn, since it has no free API and disallows scraping in its ToS
- **active-resume inference** (`app/services/resume_service.get_active_profile`) — resume parsing + candidate-data/job-role extraction from whichever resume is currently active, with mtime/size-based caching
- normalization
- URL validation
- document generation
- mock data (kept for offline demos/tests at `/api/mock/jobs`)

### PostgreSQL

Persists normalized jobs, analysis, resume profiles and applications.

### LLM

Provides probabilistic tasks:
- relevance evaluation
- resume tailoring
- resume-to-profile extraction (`app/services/llm.infer_profile`) when a real provider is configured — this is what makes candidate-data extraction format-agnostic across industries (e.g. a Communications/PR resume vs. a software resume) rather than tied to one resume template. The mock provider skips this and relies on the regex-based structural parser instead, which is tuned toward reasonably well-structured tech resumes.

Deterministic checks should happen before and after LLM calls.

## Recommended production evolution

1. ~~Add source adapters for Greenhouse and Lever.~~ Done — configure company slugs in `data/user/company_boards.json`. Ashby remains a good next adapter.
2. Add provider implementations for OpenAI/Anthropic (OpenAI implemented, including resume-profile extraction; Anthropic key is wired through `.env` but not yet called).
3. Add robust structured LLM output validation.
4. Store source snapshots for auditability.
5. Add application tracking and reminders.
6. Add a review UI.
7. Add object storage for generated documents.
8. Add monitoring and retry queues.
9. Add rate-limit-aware backoff/caching for the free discovery APIs if run more than a few times a day.
10. If concurrent (not just sequential/swapped) multi-persona search becomes a real need, the cleanest path is a `profile_id`-scoped resume/output/seen-jobs layer rather than one shared active-resume slot — bigger change, deliberately not built until it's actually needed.
