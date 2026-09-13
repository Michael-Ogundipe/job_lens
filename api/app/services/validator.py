import httpx
from urllib.parse import urlparse

CLOSED_MARKERS = ("job is no longer available","position has been filled","position is closed","this job has expired","no longer accepting applications","job not found")

async def validate_url(url: str | None, timeout: float = 10.0, source: str | None = None, external_id: str | None = None) -> dict:
    if source == "demo":
        if external_id == "demo-expired-004":
            return {"is_active": False,"status":"EXPIRED","confidence":1.0,"reason":"Demo fixture is intentionally expired."}
        if url:
            return {"is_active": True,"status":"ACTIVE","confidence":1.0,"reason":"Demo fixture marks this application URL as active."}
    if not url:
        return {"is_active": False,"status":"UNKNOWN","confidence":0.2,"reason":"No application URL supplied."}
    parsed = urlparse(url)
    if parsed.scheme not in {"http","https"} or not parsed.netloc:
        return {"is_active": False,"status":"UNKNOWN","confidence":0.1,"reason":"Invalid HTTP(S) application URL."}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={"User-Agent":"JobLens/0.2"}) as client:
            response = await client.get(url)
        text = response.text.lower()[:500_000]
        if response.status_code == 404:
            return {"is_active":False,"status":"NOT_FOUND","confidence":0.98,"reason":"Application URL returned HTTP 404."}
        if response.status_code >= 400:
            return {"is_active":False,"status":"UNKNOWN","confidence":0.6,"reason":f"Application URL returned HTTP {response.status_code}."}
        if any(marker in text for marker in CLOSED_MARKERS):
            return {"is_active":False,"status":"CLOSED","confidence":0.9,"reason":"Page contains an explicit closed/expired marker."}
        return {"is_active":True,"status":"ACTIVE","confidence":0.75,"reason":"Application page responded successfully without a known closed marker."}
    except Exception as exc:
        return {"is_active":False,"status":"UNKNOWN","confidence":0.1,"reason":f"Validation request failed: {type(exc).__name__}."}
