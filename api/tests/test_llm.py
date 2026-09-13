from app.services.llm import analyze_relevance

def test_mock_relevance():
    job = {"title": "Senior Flutter Engineer", "description": "Flutter Dart Firebase"}
    resume = {"skills": ["Flutter", "Dart", "Firebase"]}
    result = analyze_relevance(job, resume)
    assert result["relevant"] is True
    assert result["score"] >= 70
