import hashlib
import re

def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip()).lower()

def content_hash(company: str, title: str, description: str) -> str:
    raw = f"{company.strip().lower()}|{normalize_title(title)}|{description.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def normalize_job(job: dict) -> dict:
    result = dict(job)
    result["title"] = re.sub(r"\s+", " ", str(job["title"]).strip())
    result["company"] = re.sub(r"\s+", " ", str(job["company"]).strip())
    result["description"] = str(job.get("description", "")).strip()
    result["content_hash"] = content_hash(
        result["company"], result["title"], result["description"]
    )
    return result
