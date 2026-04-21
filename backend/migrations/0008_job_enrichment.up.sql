-- 0008_job_enrichment: LLM-extracted normalisation fields per job.
--
-- Pillar 2 Batch 2.5. One row per job_id. JSON columns carry the list +
-- nested-model fields (locations / required_skills / preferred_skills /
-- salary / red_flags). See src/services/job_enrichment.py for the save /
-- load helpers and src/services/job_enrichment_schema.py for the Pydantic
-- source-of-truth schema.
--
-- Shared catalog — **no user_id column** (CLAUDE.md rule #10). Per-user
-- state (shortlist, applications) continues to live in user_feed /
-- user_actions. Enrichment is shared across every user because the same
-- job gets the same structured fields regardless of who views it.

CREATE TABLE IF NOT EXISTS job_enrichment (
    job_id INTEGER PRIMARY KEY
        REFERENCES jobs(id) ON DELETE CASCADE,
    title_canonical TEXT NOT NULL,
    category TEXT NOT NULL,
    employment_type TEXT NOT NULL DEFAULT 'unknown',
    workplace_type TEXT NOT NULL DEFAULT 'unknown',
    locations TEXT NOT NULL DEFAULT '[]',
    salary TEXT NOT NULL DEFAULT '{}',
    required_skills TEXT NOT NULL DEFAULT '[]',
    preferred_skills TEXT NOT NULL DEFAULT '[]',
    experience_min_years INTEGER,
    experience_level TEXT NOT NULL DEFAULT 'unknown',
    requirements_summary TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'en',
    employer_type TEXT NOT NULL DEFAULT 'unknown',
    visa_sponsorship TEXT NOT NULL DEFAULT 'unknown',
    seniority TEXT NOT NULL DEFAULT 'unknown',
    remote_region TEXT,
    apply_instructions TEXT,
    red_flags TEXT NOT NULL DEFAULT '[]',
    enriched_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_job_enrichment_job_id
    ON job_enrichment(job_id);
