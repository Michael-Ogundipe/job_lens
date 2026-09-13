CREATE TABLE IF NOT EXISTS jobs (
    id BIGSERIAL PRIMARY KEY,
    external_id TEXT,
    source TEXT NOT NULL,
    source_url TEXT,
    application_url TEXT,
    company TEXT NOT NULL,
    company_url TEXT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    location TEXT,
    remote BOOLEAN DEFAULT FALSE,
    employment_type TEXT,
    posted_at TIMESTAMPTZ,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_verified_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'UNKNOWN',
    validation_reason TEXT,
    validation_confidence NUMERIC(5,4),
    content_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(source, external_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_application_url
ON jobs(application_url)
WHERE application_url IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);

CREATE TABLE IF NOT EXISTS resume_profiles (
    id BIGSERIAL PRIMARY KEY,
    source_path TEXT NOT NULL,
    profile JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS job_analysis (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    relevant BOOLEAN NOT NULL,
    score INTEGER NOT NULL CHECK (score >= 0 AND score <= 100),
    matching_skills JSONB NOT NULL DEFAULT '[]',
    missing_skills JSONB NOT NULL DEFAULT '[]',
    strengths JSONB NOT NULL DEFAULT '[]',
    concerns JSONB NOT NULL DEFAULT '[]',
    reason TEXT,
    raw_response JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_analysis_job_id ON job_analysis(job_id);
CREATE INDEX IF NOT EXISTS idx_job_analysis_score ON job_analysis(score);

CREATE TABLE IF NOT EXISTS applications (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    resume_version TEXT,
    relevance_score INTEGER,
    relevance_analysis JSONB,
    tailored_resume_path TEXT,
    tailored_pdf_path TEXT,
    application_url TEXT,
    status TEXT NOT NULL DEFAULT 'RESUME_TAILORED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(job_id)
);
