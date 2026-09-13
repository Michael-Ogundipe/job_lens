from datetime import datetime
from typing import Optional
from pydantic import BaseModel, HttpUrl, Field

class Job(BaseModel):
    external_id: str
    source: str
    source_url: Optional[str] = None
    application_url: Optional[str] = None
    company: str
    company_url: Optional[str] = None
    title: str
    description: str
    location: Optional[str] = None
    remote: bool = False
    employment_type: Optional[str] = None
    posted_at: Optional[datetime] = None

class ValidationResult(BaseModel):
    is_active: bool
    status: str
    confidence: float = Field(ge=0, le=1)
    reason: str
