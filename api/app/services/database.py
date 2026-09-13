import os, json
from datetime import datetime, timezone
import psycopg


def _conn():
    return psycopg.connect(os.getenv("DATABASE_URL", "postgresql://joblens:joblens@postgres:5432/joblens"))

def get_seen_hashes(content_hashes: list[str]) -> set[str]:
    """Which of these content hashes are already stored (so we don't re-tailor them daily)."""
    if not content_hashes:
        return set()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT content_hash FROM jobs WHERE content_hash = ANY(%s)", (content_hashes,))
            return {row[0] for row in cur.fetchall() if row[0]}


def save_job(job: dict, validation: dict | None = None) -> int:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO jobs (external_id,source,source_url,application_url,company,company_url,title,description,location,remote,employment_type,posted_at,last_verified_at,status,validation_reason,validation_confidence,content_hash,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s,%s,%s,%s,NOW())
                ON CONFLICT (source, external_id) DO UPDATE SET source_url=EXCLUDED.source_url, application_url=EXCLUDED.application_url, company=EXCLUDED.company, company_url=EXCLUDED.company_url, title=EXCLUDED.title, description=EXCLUDED.description, location=EXCLUDED.location, remote=EXCLUDED.remote, employment_type=EXCLUDED.employment_type, posted_at=EXCLUDED.posted_at, last_verified_at=NOW(), status=EXCLUDED.status, validation_reason=EXCLUDED.validation_reason, validation_confidence=EXCLUDED.validation_confidence, content_hash=EXCLUDED.content_hash, updated_at=NOW()
                RETURNING id""", (job.get("external_id"),job.get("source"),job.get("source_url"),job.get("application_url"),job.get("company"),job.get("company_url"),job.get("title"),job.get("description",""),job.get("location"),job.get("remote",False),job.get("employment_type"),job.get("posted_at"), (validation or {}).get("status","UNKNOWN"), (validation or {}).get("reason"), (validation or {}).get("confidence"), job.get("content_hash")))
            return cur.fetchone()[0]

def save_analysis(job_id: int, analysis: dict):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO job_analysis (job_id,relevant,score,matching_skills,missing_skills,strengths,concerns,reason,raw_response)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (job_id, bool(analysis.get("relevant")), int(analysis.get("score",0)), json.dumps(analysis.get("matching_skills",[])), json.dumps(analysis.get("missing_skills",[])), json.dumps(analysis.get("strengths",[])), json.dumps(analysis.get("concerns",[])), analysis.get("reason"), json.dumps(analysis)))

def save_application(job_id: int, job: dict, analysis: dict, docx_path: str, pdf_path: str):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO applications (job_id,resume_version,relevance_score,relevance_analysis,tailored_resume_path,tailored_pdf_path,application_url,status,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'RESUME_TAILORED',NOW())
                ON CONFLICT (job_id) DO UPDATE SET relevance_score=EXCLUDED.relevance_score,relevance_analysis=EXCLUDED.relevance_analysis,tailored_resume_path=EXCLUDED.tailored_resume_path,tailored_pdf_path=EXCLUDED.tailored_pdf_path,application_url=EXCLUDED.application_url,status='RESUME_TAILORED',updated_at=NOW()""", (job_id, datetime.now(timezone.utc).isoformat(), int(analysis.get("score",0)), json.dumps(analysis), docx_path, pdf_path, job.get("application_url")))
