-- 0010_run_log_observability: observability columns on run_log.
--
-- Tier-A Step-0 pre-flight item #8. Adds five columns to run_log so the
-- pipeline orchestrator can emit a correlation-id per run, per-source error
-- and duration maps, a wall-clock total, and optional user scoping for the
-- multi-user delivery layer (Batch 2).
--
-- Self-bootstrapping schema guard
-- -------------------------------
-- Some test fixtures (e.g. test_auth_routes::temp_db, test_channels_routes,
-- test_feed_service) call `runner.up()` WITHOUT first calling
-- `JobDatabase.init_db()`, so `run_log` may not exist at all. Production
-- always creates the table via init_db() before migrations run, but we want
-- the migration to work from every starting state. The CREATE TABLE IF NOT
-- EXISTS declares the full 11-column shape; the ALTER statements that follow
-- remain the forward path for DBs that already had the legacy 6-column
-- run_log at apply time. When both the CREATE and the ALTERs produce the
-- same column, the migration runner swallows the resulting
-- "duplicate column name" errors (see runner._apply_up_sql).
--
-- run_uuid uniqueness is enforced via a partial unique index (SQLite cannot
-- add a UNIQUE constraint to an existing table via ALTER). The WHERE clause
-- leaves historical NULL rows unaffected so the partial index can be created
-- without a backfill.
--
-- NOT touching: jobs table (rule #1), purge_old_jobs (rule #3), and run_log
-- does not gain user-scoped state — the user_id column is optional
-- per-run metadata only (rule #10 concerns the shared jobs catalog).

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    total_found INTEGER DEFAULT 0,
    new_jobs INTEGER DEFAULT 0,
    sources_queried INTEGER DEFAULT 0,
    per_source TEXT DEFAULT '{}',
    run_uuid TEXT,
    per_source_errors TEXT DEFAULT '{}',
    per_source_duration TEXT DEFAULT '{}',
    total_duration REAL,
    user_id TEXT
);

ALTER TABLE run_log ADD COLUMN run_uuid TEXT;
ALTER TABLE run_log ADD COLUMN per_source_errors TEXT DEFAULT '{}';
ALTER TABLE run_log ADD COLUMN per_source_duration TEXT DEFAULT '{}';
ALTER TABLE run_log ADD COLUMN total_duration REAL;
ALTER TABLE run_log ADD COLUMN user_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_run_log_run_uuid
    ON run_log(run_uuid) WHERE run_uuid IS NOT NULL;
