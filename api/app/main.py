from fastapi import FastAPI
from app.routers import jobs, resume, mock, discover

app = FastAPI(title="JobLens API", version="0.3.0")
app.include_router(jobs.router, prefix="/api/job", tags=["jobs"])
app.include_router(resume.router, prefix="/api/resume", tags=["resume"])
app.include_router(discover.router, prefix="/api/discover", tags=["discover"])
app.include_router(mock.router, prefix="/api/mock", tags=["mock"])

@app.get("/health")
def health():
    return {"status": "ok", "service": "joblens-api", "version": "0.3.0"}
