# Active resume

Put your current resume here as `resume.pdf` (or `resume.docx`). JobLens infers
both the candidate profile *and* the job-search keywords directly from it — no
separate profile.json to hand-maintain.

To switch who/what you're searching for, just replace this file:

```bash
cp ~/resumes/flutter-resume.pdf   data/user/resume.pdf   # Flutter/mobile roles
cp ~/resumes/ai-engineer.pdf      data/user/resume.pdf   # AI/ML roles
cp ~/resumes/friend-comms-pr.pdf  data/user/resume.pdf   # Comms/PR roles
```

No restart, no config edit, no code change — the next discovery/analyze/tailor
call detects the file changed and re-infers automatically. See the "Switching
who you're searching for" section of the top-level README for details,
including the honest caveat about the free/no-API-key mock mode vs. a real LLM
provider.

`.resume_profile_cache.json` (appears here automatically after the first run)
is a generated cache, not something you edit. Delete it any time to force a
fresh re-parse.
