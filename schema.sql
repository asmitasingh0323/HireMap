CREATE TABLE IF NOT EXISTS jobs (
    id              SERIAL PRIMARY KEY,
    title           TEXT NOT NULL,
    company         TEXT,
    location        TEXT,
    skills          TEXT,
    salary_min      NUMERIC,
    salary_max      NUMERIC,
    job_type        TEXT,
    experience_level TEXT,
    posted_date     DATE,
    source          TEXT NOT NULL,
    fingerprint     TEXT UNIQUE NOT NULL,
    search_id       TEXT,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_search_id ON jobs(search_id);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);