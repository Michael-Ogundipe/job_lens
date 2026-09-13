import os
import json
from typing import Any
import httpx


def _threshold() -> int:
    return int(os.getenv("JOB_RELEVANCE_THRESHOLD", "70"))


def _provider() -> str:
    """Resolve auto to a usable provider without making configuration brittle."""
    requested = os.getenv("LLM_PROVIDER", "auto").strip().lower()
    if requested == "auto":
        return "openai" if os.getenv("OPENAI_API_KEY", "").strip() else "mock"
    return requested


def _skill_matches(job: dict, resume: dict) -> list[str]:
    text = f"{job.get('title','')} {job.get('description','')}".lower()
    return [s for s in resume.get("skills", []) if s and str(s).lower() in text]


def _mock_relevance(job: dict, resume: dict) -> dict:
    matches = _skill_matches(job, resume)
    score = min(95, 45 + len(matches) * 10)
    job_title = str(job.get("title", "")).lower()
    role_terms = [resume.get("headline", "")] + list(resume.get("target_job_titles", []) or [])
    if any(t and str(t).lower() in job_title for t in role_terms):
        score = min(100, score + 10)
    relevant = score >= _threshold()
    return {
        "relevant": relevant,
        "score": score,
        "matching_skills": matches[:10],
        "missing_skills": [],
        "strengths": ["Demonstrated overlap with the job requirements."] if matches else [],
        "concerns": [] if relevant else ["Limited evidence of direct skill overlap in the current resume."],
        "reason": "Demo relevance scoring based on resume/job overlap. Configure an LLM provider for semantic analysis.",
    }


def _truthful_mock_tailor(job: dict, resume: dict) -> dict:
    profile = json.loads(json.dumps(resume))
    title = job.get("title", "")
    job_text = f"{title} {job.get('description','')}".lower()
    skills = profile.get("skills", [])
    profile["skills"] = sorted(skills, key=lambda s: (str(s).lower() not in job_text, str(s).lower()))
    summary = profile.get("summary", "").strip()
    if title:
        profile["summary"] = f"{summary} Targeted for {title} opportunities, emphasizing the candidate's existing experience and skills.".strip()
    profile["target_role"] = title
    profile["tailoring_note"] = "Only existing resume facts were reordered or reworded; no new experience or qualifications were added."
    return profile


SYSTEM_PROMPT = """You are JobLens, a truthful recruitment assistant.
Never invent or imply experience, employers, degrees, certifications, technologies, years, achievements, metrics, responsibilities, or job titles that are not supported by the resume.
For profile extraction, only extract facts explicitly present in the resume. Target job titles must be reasonable search variants grounded in the candidate's stated/current/recent professional field and seniority; do not invent a career change.
For relevance, distinguish actual role fit from incidental keyword mentions.
For tailoring, preserve factual meaning and all employment/education history; you may reorder and rewrite existing content for relevance.
Return JSON only."""


def _openai_json(instruction: str) -> dict:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "90"))
    payload = {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": instruction},
        ],
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        return json.loads(content)


def analyze_relevance(job: dict, resume: dict) -> dict:
    provider = _provider()
    if provider == "mock":
        return _mock_relevance(job, resume)
    if provider == "openai":
        result = _openai_json(
            f"JOB:\n{json.dumps(job, ensure_ascii=False)}\n\nRESUME:\n{json.dumps(resume, ensure_ascii=False)}\n\n"
            "Return JSON with: relevant (boolean), score (0-100), matching_skills (array), missing_skills (array), "
            "strengths (array), concerns (array), reason (string). Score semantic fit, not mere keyword overlap. "
            "A role should be relevant only when the candidate's actual experience/skills reasonably support it."
        )
        result["score"] = max(0, min(100, int(result.get("score", 0))))
        result["relevant"] = bool(result.get("relevant", False)) and result["score"] >= _threshold()
        return result
    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def tailor_resume(job: dict, resume: dict) -> dict:
    provider = _provider()
    if provider == "mock":
        return _truthful_mock_tailor(job, resume)
    if provider == "openai":
        result = _openai_json(
            f"JOB:\n{json.dumps(job, ensure_ascii=False)}\n\nRESUME:\n{json.dumps(resume, ensure_ascii=False)}\n\n"
            "Return a complete tailored resume profile using only facts from the source resume. Preserve every employer, "
            "role, date, education entry, numeric metric and factual claim. You may reorder skills and bullets and rewrite "
            "wording for relevance. Include name, headline, contact, summary, skills, experience, education, soft_skills, "
            "target_role, tailoring_note. Do not add qualifications."
        )
        result["target_role"] = job.get("title", "")
        result["tailoring_note"] = "Tailored using only facts present in the source resume."
        return result
    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def infer_profile(raw_text: str) -> dict:
    """Format-agnostic resume extraction for arbitrary industries/layouts."""
    provider = _provider()
    if provider == "mock":
        return {}
    if provider == "openai":
        return _openai_json(
            "RESUME TEXT (raw-extracted; formatting may be imperfect):\n"
            f"{raw_text}\n\n"
            "Extract JSON with exactly these fields:\n"
            "name (string), headline (string), contact (object with email/linkedin/github/portfolio), summary (string), "
            "skills (array of strings), experience (array of objects with company/location/role/duration/dates/bullets), "
            "education (array of strings), soft_skills (array of strings), target_job_titles (array of 4-8 specific job "
            "title search variants grounded in the candidate's actual field and seniority).\n\n"
            "Rules: use ONLY facts stated in the resume. Do not invent missing details. Target titles should represent "
            "the candidate's existing professional direction, not an unsupported career change. Prefer specific titles "
            "over generic labels, and include reasonable seniority/title variants that employers commonly use."
        )
    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")
