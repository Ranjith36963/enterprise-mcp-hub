-- 0011_score_dimensions: per-dimension score columns on jobs.
--
-- Step-1.5 mini-batch S1.1 (the dim-field bombshell fix).
-- JobResponse already exposes 9 per-dim score slots (role, skill,
-- seniority_score, experience, credentials, location_score, recency,
-- semantic, penalty) defaulted to 0 because Step 1 never persisted the
-- breakdown ScoreBreakdown returns from JobScorer.score(). This migration
-- adds the missing columns; the writer side (insert_job + main.py:run_search)
-- and the read side (_JOBS_ENRICHMENT_JOIN_COLS + _row_to_job_response) land
-- in the same Step-1.5 batch.
--
-- All columns are additive INTEGER DEFAULT 0 so legacy rows stay valid
-- (zero is the Pillar-2-Batch-2.9 "this dimension was not scored" sentinel).
-- Per CLAUDE.md rule #1 the jobs UNIQUE constraint is untouched; per rule
-- #10 no per-user column is added — score breakdown is part of the shared
-- catalog.
--
-- Self-bootstrapping schema guard
-- -------------------------------
-- The ALTER TABLE ADD COLUMN sequence is the forward path for DBs that
-- already had the legacy jobs schema. The fresh-init path runs through
-- JobDatabase._migrate() in database.py, which mirrors this same column
-- list. The migration runner swallows "duplicate column name" errors so
-- both paths converge to the same shape.

ALTER TABLE jobs ADD COLUMN role INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN skill INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN seniority_score INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN experience INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN credentials INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN location_score INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN recency INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN semantic INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN penalty INTEGER DEFAULT 0;
