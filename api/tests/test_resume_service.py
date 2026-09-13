import json
from pathlib import Path

import pytest

from app.services import resume_service


SAMPLE_RESUME_TEXT = (
    "Jordan Rivers Senior Communications Manager Email:jordan@example.com\n"
    "Experience Summary\n"
    "Communications leader with 8 years in brand and media relations.\n"
    "Technical Skills\n"
    "● Tools: Cision, Meltwater, Canva\n"
    "Professional Experience\n"
    "Acme Media - New York\n"
    "Senior Communications Manager, 3 years (2021 - Present)\n"
    "● Led press strategy for three national product launches\n"
    "Beta PR - Boston\n"
    "Communications Associate, 2 years (2019 - 2021)\n"
    "● Drafted press releases and pitched media\n"
    "Education\n"
    "● BA Communications, Boston University\n"
    "Soft Skills Summary\n"
    "● Stakeholder management\n"
)


def _write_txt_resume(tmp_path: Path, text: str = SAMPLE_RESUME_TEXT) -> Path:
    # .txt exercises the same structured-parsing path as pdf/docx without needing
    # a real PDF/DOCX fixture on disk.
    path = tmp_path / "resume.txt"
    path.write_text(text)
    return path


def test_infer_target_job_titles_prefers_headline_then_roles():
    profile = {
        "headline": "Senior Communications Manager",
        "experience": [
            {"role": "Senior Communications Manager"},
            {"role": "Communications Associate"},
        ],
    }
    titles = resume_service._infer_target_job_titles(profile)
    assert titles[0] == "Senior Communications Manager"
    assert "Communications Associate" in titles


def test_get_active_profile_infers_from_whatever_resume_is_active(monkeypatch, tmp_path):
    resume_path = _write_txt_resume(tmp_path)
    monkeypatch.setenv("BASE_RESUME_PATH", str(resume_path))
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    profile = resume_service.get_active_profile()

    assert "Communications" in profile["headline"] or any(
        "Communications" in t for t in profile["target_job_titles"]
    )
    assert "raw_text" not in profile
    assert (tmp_path / ".resume_profile_cache.json").exists()


def test_get_active_profile_uses_cache_without_reparsing(monkeypatch, tmp_path):
    resume_path = _write_txt_resume(tmp_path)
    monkeypatch.setenv("BASE_RESUME_PATH", str(resume_path))
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    calls = {"n": 0}
    real_build = resume_service._build_profile_from_resume

    def counting_build(path):
        calls["n"] += 1
        return real_build(path)

    monkeypatch.setattr(resume_service, "_build_profile_from_resume", counting_build)

    first = resume_service.get_active_profile()
    second = resume_service.get_active_profile()

    assert calls["n"] == 1  # second call was served from cache
    assert first == second


def test_get_active_profile_reparses_after_resume_is_replaced(monkeypatch, tmp_path):
    resume_path = _write_txt_resume(tmp_path, SAMPLE_RESUME_TEXT)
    monkeypatch.setenv("BASE_RESUME_PATH", str(resume_path))
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    first = resume_service.get_active_profile()
    assert "Communications" in " ".join(first["target_job_titles"] + [first["headline"]])

    # Swap in a completely different persona's resume at the same path.
    flutter_text = (
        "Alex Chen Senior Flutter Engineer Email:alex@example.com\n"
        "Experience Summary\n"
        "Mobile engineer specializing in Flutter and Dart.\n"
        "Technical Skills\n"
        "● Languages: Flutter, Dart, Swift\n"
        "Professional Experience\n"
        "Mobile Co - Remote\n"
        "Senior Flutter Engineer, 4 years (2020 - Present)\n"
        "● Shipped a cross-platform app used by 1M+ users\n"
        "Education\n"
        "● BSc Computer Science\n"
        "Soft Skills Summary\n"
        "● Communication\n"
    )
    resume_path.write_text(flutter_text)

    second = resume_service.get_active_profile()
    assert "Flutter" in " ".join(second["target_job_titles"] + [second["headline"]])
    assert second != first


def test_get_active_profile_raises_clear_error_when_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("BASE_RESUME_PATH", str(tmp_path / "missing.pdf"))
    with pytest.raises(FileNotFoundError):
        resume_service.get_active_profile()


def test_infer_profile_mock_provider_is_a_noop(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    from app.services.llm import infer_profile
    assert infer_profile("anything") == {}
