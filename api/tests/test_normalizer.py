from app.services.normalizer import normalize_job, content_hash

def test_normalize_job():
    job = {
        "company": "  Example   Co ",
        "title": " Senior  Flutter Engineer ",
        "description": " Build apps "
    }
    result = normalize_job(job)
    assert result["company"] == "Example Co"
    assert result["title"] == "Senior Flutter Engineer"
    assert result["content_hash"]

def test_hash_stable():
    assert content_hash("A", "B", "C") == content_hash("A", "B", "C")
