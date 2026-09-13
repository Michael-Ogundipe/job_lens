from pathlib import Path
import os
import json as _json
import re
from typing import Any
from pypdf import PdfReader
from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from xml.sax.saxutils import escape

SECTION_NAMES = {
    "experience summary": "summary",
    "technical skills": "skills",
    "professional experience": "experience",
    "education": "education",
    "soft skills summary": "soft_skills",
}

ACTIVE_RESUME_ENV = "BASE_RESUME_PATH"
DEFAULT_ACTIVE_RESUME_PATH = "/data/user/resume.pdf"

def _clean_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]

def _extract_bullets(lines: list[str], start: int, end: int) -> list[str]:
    out = []
    for line in lines[start:end]:
        line = re.sub(r"^[●•▪-]\s*", "", line).strip()
        if line:
            out.append(line)
    return out

def _parse_skills(lines: list[str], start: int, end: int) -> list[str]:
    skills = []
    for line in lines[start:end]:
        line = re.sub(r"^[●•▪-]\s*", "", line).strip()
        if ":" in line:
            values = line.split(":", 1)[1]
            skills.extend([x.strip() for x in values.split(",") if x.strip()])
    return skills

def _parse_experience(lines: list[str], start: int, end: int) -> list[dict[str, Any]]:
    entries = []
    company_re = re.compile(r"^(?P<company>.+?)\s+-\s+(?P<location>.+)$")
    role_re = re.compile(r"^(?P<role>.+?),\s*(?P<duration>[^()]+)?\s*\((?P<dates>[^)]+)\)$")
    i = start
    while i < end:
        m = company_re.match(lines[i])
        if not m or i + 1 >= end:
            i += 1
            continue
        role_line = lines[i + 1]
        rm = role_re.match(role_line)
        if not rm:
            i += 1
            continue
        bullets = []
        j = i + 2
        while j < end and not company_re.match(lines[j]):
            if re.match(r"^[●•▪-]\s*", lines[j]):
                bullets.append(re.sub(r"^[●•▪-]\s*", "", lines[j]).strip())
            j += 1
        entries.append({
            "company": m.group("company").strip(),
            "location": m.group("location").strip(),
            "role": rm.group("role").strip(),
            "duration": (rm.group("duration") or "").strip(),
            "dates": rm.group("dates").strip(),
            "bullets": bullets,
        })
        i = j
    return entries

def parse_resume(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Resume not found: {p}")
    if p.suffix.lower() == ".pdf":
        reader = PdfReader(str(p))
        raw = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif p.suffix.lower() == ".docx":
        doc = Document(str(p))
        raw = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    else:
        raw = p.read_text(errors="ignore")

    # PDF extraction can put every word on its own line. Rebuild readable text
    # while preserving bullet boundaries so the structured parser remains useful.
    text = re.sub(r"\s+", " ", raw.replace("\n", " ")).strip()
    text = text.replace(" ● ", "\n● ").replace(" ●", "\n●")
    text = text.replace("•", "●")

    def between(a: str, b: str | None = None) -> str:
        m = re.search(re.escape(a) + r"\s*(.*?)(?:\s+" + re.escape(b) + r"\s*|$)" if b else re.escape(a) + r"\s*(.*)$", text, re.I | re.S)
        return m.group(1).strip() if m else ""

    header = re.search(r"^(.*?)\s+Email\s*:\s*([^\s]+)(?:\s+LinkedIn\s*:\s*([^\s]+))?(?:\s+Github\s*:\s*([^\s]+))?(?:\s+Portfolio\s*:\s*([^\s]+))?", text, re.I)
    if header:
        header_words = header.group(1).strip().split()
        name = " ".join(header_words[:2])
        headline = " ".join(header_words[2:])
        contact = {"email": header.group(2) or "", "linkedin": header.group(3) or "", "github": header.group(4) or "", "portfolio": header.group(5) or ""}
    else:
        name, headline, contact = "", "", {"email":"", "linkedin":"", "github":"", "portfolio":""}

    summary = between("Experience Summary", "Technical Skills")
    skills_text = between("Technical Skills", "Professional Experience")
    experience_text = between("Professional Experience", "Education")
    education_text = between("Education", "Soft Skills Summary")
    soft_text = between("Soft Skills Summary")

    skills = []
    for part in re.findall(r"●\s*([^:]+):\s*(.*?)(?=\s+●|$)", skills_text, re.I | re.S):
        skills.extend([x.strip() for x in part[1].split(",") if x.strip()])

    experience = []
    company_pattern = re.compile(
        r"(?P<company>[A-Za-z0-9&'(). -]+?)\s+-\s+(?P<location>[^\n]+?)\s+"
        r"(?P<role>[^\n,(]+?),\s*(?P<duration>[^()]+?)\s*\((?P<dates>[^)]+)\)"
        r"(?P<bullets>.*?)(?=(?:[A-Za-z0-9&'(). -]+?)\s+-\s+[^\n]+?\s+[^\n,(]+?,\s*[^()]+?\s*\([^)]*\)|$)",
        re.I | re.S,
    )
    for m in company_pattern.finditer(experience_text):
        bullets = [b.strip() for b in re.findall(r"●\s*(.*?)(?=\s+●|$)", m.group("bullets"), re.S) if b.strip()]
        experience.append({
            "company": re.sub(r"\s+", " ", m.group("company")).strip(),
            "location": re.sub(r"\s+", " ", m.group("location")).strip(),
            "role": re.sub(r"\s+", " ", m.group("role")).strip(),
            "duration": re.sub(r"\s+", " ", m.group("duration")).strip(),
            "dates": re.sub(r"\s+", " ", m.group("dates")).strip(),
            "bullets": [re.sub(r"\s+", " ", b).strip() for b in bullets],
        })

    education = [re.sub(r"\s+", " ", x).strip() for x in re.findall(r"●\s*(.*?)(?=\s+●|$)", education_text, re.S) if x.strip()]
    soft = [re.sub(r"\s+", " ", x).strip() for x in re.findall(r"●\s*(.*?)(?=\s+●|$)", soft_text, re.S) if x.strip()]

    return {
        "name": name,
        "headline": headline,
        "contact": contact,
        "summary": re.sub(r"\s+", " ", summary).strip(),
        "skills": skills,
        "experience": experience,
        "education": education,
        "soft_skills": soft,
        "raw_text": raw,
        "source_path": str(p),
    }

def _infer_target_job_titles(profile: dict) -> list[str]:
    """Best-effort search-term inference used when no LLM is configured (or as a
    fallback for anything the LLM path didn't return). Prefers the candidate's
    own stated headline plus the roles they've actually held, most recent first,
    over any hardcoded assumption about what industry this resume is in."""
    titles: list[str] = []
    if profile.get("headline"):
        titles.append(profile["headline"])
    for exp in profile.get("experience", []):
        role = (exp.get("role") or "").strip()
        if role and role.lower() not in [t.lower() for t in titles]:
            titles.append(role)
    return titles[:6]


def _build_profile_from_resume(path: Path) -> dict:
    """Parse the resume, then infer candidate data + target job-role search
    terms from it. With LLM_PROVIDER set to a real provider this uses the LLM
    for format-agnostic extraction (works for any industry/layout). Without
    one, it falls back to the heuristic section parser above, which works
    best on reasonably well-structured resumes."""
    parsed = parse_resume(str(path))
    provider = os.getenv("LLM_PROVIDER", "auto").lower()
    profile = dict(parsed)
    if provider in {"openai", "anthropic", "auto"} and os.getenv("OPENAI_API_KEY", "").strip():
        from app.services.llm import infer_profile
        try:
            inferred = infer_profile(parsed.get("raw_text", ""))
        except Exception:
            inferred = {}
        for key, value in (inferred or {}).items():
            if value:
                profile[key] = value
    if not profile.get("target_job_titles"):
        profile["target_job_titles"] = _infer_target_job_titles(profile)
    profile.pop("raw_text", None)
    return profile


def get_active_profile(force_refresh: bool = False) -> dict:
    """The single derived source of truth: whichever resume is currently sitting
    at BASE_RESUME_PATH. Swapping that file (Flutter resume -> AI resume ->
    a friend's Comms/PR resume) is the entire "switch persona" workflow -- no
    other config to touch. Results are cached next to the resume, keyed off its
    mtime/size, so an unchanged resume doesn't get re-parsed (or re-billed
    against an LLM) on every request; touching/replacing the file invalidates
    the cache automatically.
    """
    path = Path(os.getenv(ACTIVE_RESUME_ENV, DEFAULT_ACTIVE_RESUME_PATH))
    if not path.exists():
        raise FileNotFoundError(
            f"No active resume found at {path}. Add one (PDF or DOCX) to get started."
        )
    stat = path.stat()
    provider_fingerprint = f"{os.getenv("LLM_PROVIDER", "auto").lower()}:{bool(os.getenv("OPENAI_API_KEY", "").strip())}:{os.getenv("LLM_MODEL", "gpt-4o-mini")}"
    fingerprint = f"{path}:{stat.st_mtime_ns}:{stat.st_size}:{provider_fingerprint}"
    cache_path = path.parent / ".resume_profile_cache.json"

    if not force_refresh and cache_path.exists():
        try:
            cached = _json.loads(cache_path.read_text())
            if cached.get("fingerprint") == fingerprint:
                return cached["profile"]
        except Exception:
            pass

    profile = _build_profile_from_resume(path)
    try:
        cache_path.write_text(_json.dumps({"fingerprint": fingerprint, "profile": profile}, default=str))
    except Exception:
        pass  # caching is a performance optimization, not a correctness requirement
    return profile


def _style_docx(doc: Document):
    styles = doc.styles
    styles["Normal"].font.name = "Aptos"
    styles["Normal"].font.size = __import__("docx").shared.Pt(10)

def generate_docx(profile: dict, output_path: str) -> str:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    _style_docx(doc)
    doc.add_heading(profile.get("name", "Candidate"), 0)
    doc.add_paragraph(profile.get("target_role") or profile.get("headline", ""))
    contact = profile.get("contact", {})
    contact_line = " | ".join(v for v in [contact.get("email"), contact.get("linkedin"), contact.get("github"), contact.get("portfolio")] if v)
    if contact_line:
        doc.add_paragraph(contact_line)
    if profile.get("summary"):
        doc.add_heading("Professional Summary", 1)
        doc.add_paragraph(profile["summary"])
    if profile.get("skills"):
        doc.add_heading("Technical Skills", 1)
        doc.add_paragraph(", ".join(profile["skills"]))
    if profile.get("experience"):
        doc.add_heading("Professional Experience", 1)
        for exp in profile["experience"]:
            doc.add_heading(f'{exp["company"]} - {exp["location"]}', 2)
            doc.add_paragraph(f'{exp["role"]} ({exp["dates"]})')
            for bullet in exp.get("bullets", []):
                doc.add_paragraph(bullet, style="List Bullet")
    if profile.get("education"):
        doc.add_heading("Education", 1)
        for item in profile["education"]:
            doc.add_paragraph(item, style="List Bullet")
    if profile.get("soft_skills"):
        doc.add_heading("Soft Skills", 1)
        for item in profile["soft_skills"]:
            doc.add_paragraph(item, style="List Bullet")
    doc.save(out)
    return str(out)

def generate_pdf(profile: dict, output_path: str) -> str:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("Title2", parent=styles["Title"], fontSize=20, leading=24, spaceAfter=4)
    heading = ParagraphStyle("Heading2", parent=styles["Heading2"], fontSize=12, leading=15, spaceBefore=10, spaceAfter=5)
    body = ParagraphStyle("Body2", parent=styles["BodyText"], fontSize=9.5, leading=13, spaceAfter=4)
    doc = SimpleDocTemplate(str(out), pagesize=A4, rightMargin=42, leftMargin=42, topMargin=36, bottomMargin=36)
    story = [Paragraph(escape(profile.get("name", "Candidate")), title)]
    if profile.get("target_role") or profile.get("headline"):
        story.append(Paragraph(escape(profile.get("target_role") or profile.get("headline", "")), body))
    contact = profile.get("contact", {})
    contact_line = " | ".join(v for v in [contact.get("email"), contact.get("linkedin"), contact.get("github"), contact.get("portfolio")] if v)
    if contact_line:
        story.append(Paragraph(escape(contact_line), body))
    if profile.get("summary"):
        story += [Paragraph("Professional Summary", heading), Paragraph(escape(profile["summary"]), body)]
    if profile.get("skills"):
        story += [Paragraph("Technical Skills", heading), Paragraph(escape(", ".join(profile["skills"])), body)]
    if profile.get("experience"):
        story.append(Paragraph("Professional Experience", heading))
        for exp in profile["experience"]:
            story.append(Paragraph(escape(f'{exp["company"]} - {exp["location"]}'), heading))
            story.append(Paragraph(escape(f'{exp["role"]} ({exp["dates"]})'), body))
            story.append(ListFlowable([ListItem(Paragraph(escape(b), body)) for b in exp.get("bullets", [])], bulletType="bullet", leftIndent=16))
    if profile.get("education"):
        story.append(Paragraph("Education", heading))
        story.append(ListFlowable([ListItem(Paragraph(escape(x), body)) for x in profile["education"]], bulletType="bullet", leftIndent=16))
    if profile.get("soft_skills"):
        story.append(Paragraph("Soft Skills", heading))
        story.append(ListFlowable([ListItem(Paragraph(escape(x), body)) for x in profile["soft_skills"]], bulletType="bullet", leftIndent=16))
    doc.build(story)
    return str(out)
