# JobLens

AI-powered job discovery and resume tailoring, orchestrated with n8n.

## Full pipeline

```
                    Active resume
                 data/user/resume.pdf
                         │
               ┌─────────┴─────────┐
               ↓                   ↓
        Infer job roles      Candidate data
               ↓                   ↓
               └─────────┬─────────┘
                         ↓
                   Job Discovery
                         ↓
                   AI Relevance
                         ↓
                  Resume Tailoring
                         ↓
                   DOCX + PDF
```

Everything — the search keywords *and* the candidate profile used for scoring/tailoring — is derived from the one active resume file. There's no separate profile config to keep in sync with it.

## Switching who you're searching for

Whoever's resume is sitting at `data/user/resume.pdf` is who JobLens searches and tailors for. To switch, just replace that file:

```bash
cp ~/resumes/flutter-resume.pdf   data/user/resume.pdf   # → Flutter/mobile roles
cp ~/resumes/ai-engineer.pdf      data/user/resume.pdf   # → AI/ML roles
cp ~/resumes/friend-comms-pr.pdf  data/user/resume.pdf   # → Communications/PR roles
```

No restart, no config edit, no code change. The next API call detects the file changed (by modified time + size) and re-infers automatically — both the job-title search terms and the structured candidate data used for relevance scoring and tailoring. Results are cached at `data/user/.resume_profile_cache.json` next to it so an unchanged resume isn't re-parsed on every request.

This is single-instance, single-active-persona at a time by design — it's the same one running pipeline, just pointed at whichever resume is currently in that slot. If you want two personas discoverable *simultaneously* (e.g. running both a Flutter and an AI-engineer search on the same daily schedule, side by side) that's a bigger change — a second `docker compose` stack per resume is the simplest way to get there without touching the code, since it's just a different `BASE_RESUME_PATH` bind-mount per stack.

**No external AI/API key is required:** this version uses the local resume parser and rule-based discovery/validation. The n8n workflow sends validated jobs to Google Sheets for review instead of calling an LLM.


## Job discovery: not just LinkedIn

LinkedIn has no free public jobs API and its Terms of Service prohibit automated scraping, so JobLens doesn't do that. Instead it aggregates real, currently-open postings from open job-board APIs (no key required), plus optionally direct company ATS boards — which is often where LinkedIn/Indeed postings are mirrored from in the first place:

- **RemoteOK** — https://remoteok.com/api
- **Remotive** — https://remotive.com/api/remote-jobs
- **Arbeitnow** — https://www.arbeitnow.com/api/job-board-api
- **Greenhouse** (per company) — `boards-api.greenhouse.io/v1/boards/{slug}/jobs`
- **Lever** (per company) — `api.lever.co/v0/postings/{slug}`

Add specific companies you're targeting by editing `data/user/company_boards.json` (shared across whichever resume is active — it's "companies I always want checked," not persona-specific):

```json
{
  "greenhouse": ["stripe", "airbnb"],
  "lever": ["netflix"]
}
```

(Find a company's slug from its own careers page URL, e.g. `boards.greenhouse.io/stripe` → `stripe`, `jobs.lever.co/netflix` → `netflix`.)

Call the API directly to see what it finds:

```bash
curl "http://localhost:8000/api/discover/jobs?max_age_days=3&remote_only=false"
```

Query parameters:
- `keywords` — comma-separated search terms. Defaults to job titles inferred from the active resume.
- `max_age_days` — only include jobs posted within this many days (default `3`; `0` disables the filter). This is what keeps results "recent."
- `remote_only` — `true`/`false` (default `false`).
- `sources` — comma-separated subset of `remoteok,remotive,arbeitnow,greenhouse,lever` (default: all).
- `exclude_seen` — default `true`. Skips jobs already stored in Postgres so the daily run doesn't re-tailor a job it already processed yesterday.

## What about LinkedIn specifically?

JobLens doesn't automate LinkedIn: it has no free public jobs API, and automating access to it (logging in, scraping pages) risks getting your account permanently banned — LinkedIn actively detects and enforces this. That risk isn't worth a feature that would also break every time they change their page markup.

Instead there's a **Manual Job Inbox** — a webhook in the n8n workflow that lets you drop a job you found yourself (on LinkedIn or anywhere else) straight into the same pipeline: normalize → validate → prepare → Google Sheets. You did the browsing; the automation adds the job to the inbox.

```bash
curl -X POST http://localhost:5678/webhook/manual-job \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Senior Flutter Engineer",
    "company": "Acme Corp",
    "application_url": "https://www.linkedin.com/jobs/view/1234567890",
    "description": "Paste the job description here for better relevance scoring.",
    "location": "Remote",
    "remote": true,
    "source": "linkedin"
  }'
```

The webhook waits for the pipeline to finish and returns the processed job, so this also works nicely from an iOS/Android Shortcut wired to LinkedIn's share sheet, or a browser bookmarklet — paste the job and send it to the JobLens inbox. Only `title` and `company` are required; everything else defaults sensibly.

## Running it every day

The n8n workflow (`n8n/joblens-workflow.json`) has two triggers feeding the same discovery pipeline:
- **Manual Trigger** — run it on demand from the n8n UI.
- **Daily Schedule (8am)** — a Schedule Trigger node that fires once a day. Edit its time in the node's parameters, or duplicate it to run more often.

After importing the workflow, click into "Daily Schedule (8am)" and toggle the workflow **Active** (top-right in n8n) so the schedule actually runs unattended.

### Start

```bash
cp .env.example .env   # then edit passwords/secrets as you like
docker compose up -d --build
```

Open n8n at `http://localhost:5678` (login: the `N8N_BASIC_AUTH_USER`/`N8N_BASIC_AUTH_PASSWORD` from `.env`), import `n8n/joblens-workflow.json`, and either run it manually or activate it for the daily schedule.

The API is also directly reachable at `http://localhost:8000` (see `/docs` for interactive Swagger UI) if you want to test endpoints without n8n. `GET /api/job/profile` (or `/api/resume/current`) shows exactly what was inferred from the active resume — check this first after swapping personas. Add `?refresh=true` to force re-inference immediately instead of waiting for the cache to notice the file changed.

### Google Sheets

The workflow does not require OpenAI, Anthropic, or any other LLM API key. After discovery and active-job validation, jobs are transformed into a clean row and appended to a Google Sheet.

The imported `Add Jobs to Google Sheets` node uses these columns:

```text
Job Title | Company | Location | Remote | Employment | Source | Posted | Application | Job Description | Status
```

After importing the workflow, connect your Google Sheets OAuth credential, replace `REPLACE_WITH_GOOGLE_SHEET_ID` with your spreadsheet ID, and make sure the target tab is named `Jobs` (or change the node to your tab name).

### Outputs

Google Sheets is the primary JobLens inbox for this version. PostgreSQL remains available for the app's existing persistence/API, but the n8n discovery workflow no longer sends jobs through the LLM or resume-generation stages.

### Tests

```bash
cd api
pip install -r requirements.txt
pytest -q
```

This runs entirely offline — discovery tests use mocked HTTP responses shaped like each real API's documented schema, so no network access or API keys are needed to verify the logic.
