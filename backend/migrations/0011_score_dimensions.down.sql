-- 0011_score_dimensions: reverse migration.
--
-- DROP COLUMN was added in SQLite 3.35 but our test matrix targets older
-- versions, so the safest reverse is the rebuild-and-rename pattern (mirror
-- of 0010_run_log_observability.down.sql). Recreate the pre-0011 jobs
-- shape, copy the 24 original columns, drop the augmented table, rename.
--
-- IMPORTANT: indexes and the UNIQUE constraint must be recreated on the
-- new table (see below). Per CLAUDE.md rule #1 the UNIQUE constraint shape
-- is preserved exactly.

DROP INDEX IF EXISTS idx_jobs_date_found;
DROP INDEX IF EXISTS idx_jobs_first_seen;
DROP INDEX IF EXISTS idx_jobs_match_score;
DROP INDEX IF EXISTS idx_jobs_staleness_state;
DROP INDEX IF EXISTS idx_jobs_last_seen_at;

CREATE TABLE jobs_old (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT DEFAULT '',
    salary_min REAL,
    salary_max REAL,
    description TEXT DEFAULT '',
    apply_url TEXT NOT NULL,
    source TEXT NOT NULL,
    date_found TEXT NOT NULL,
    match_score INTEGER DEFAULT 0,
    visa_flag INTEGER DEFAULT 0,
    experience_level TEXT DEFAULT '',
    normalized_company TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    posted_at TEXT,
    first_seen_at TEXT,
    last_seen_at TEXT,
    last_updated_at TEXT,
    date_confidence TEXT DEFAULT 'low',
    date_posted_raw TEXT,
    consecutive_misses INTEGER DEFAULT 0,
    staleness_state TEXT DEFAULT 'active',
    UNIQUE(normalized_company, normalized_title)
);

INSERT INTO jobs_old (
    id, title, company, location, salary_min, salary_max, description,
    apply_url, source, date_found, match_score, visa_flag, experience_level,
    normalized_company, normalized_title, first_seen, posted_at,
    first_seen_at, last_seen_at, last_updated_at, date_confidence,
    date_posted_raw, consecutive_misses, staleness_state
)
SELECT
    id, title, company, location, salary_min, salary_max, description,
    apply_url, source, date_found, match_score, visa_flag, experience_level,
    normalized_company, normalized_title, first_seen, posted_at,
    first_seen_at, last_seen_at, last_updated_at, date_confidence,
    date_posted_raw, consecutive_misses, staleness_state
FROM jobs;

DROP TABLE jobs;
ALTER TABLE jobs_old RENAME TO jobs;

CREATE INDEX IF NOT EXISTS idx_jobs_date_found ON jobs(date_found);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen);
CREATE INDEX IF NOT EXISTS idx_jobs_match_score ON jobs(match_score);
CREATE INDEX IF NOT EXISTS idx_jobs_staleness_state ON jobs(staleness_state);
CREATE INDEX IF NOT EXISTS idx_jobs_last_seen_at ON jobs(last_seen_at);
