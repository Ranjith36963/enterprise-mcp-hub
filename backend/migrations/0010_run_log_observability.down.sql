-- 0010_run_log_observability: reverse migration.
--
-- SQLite cannot DROP COLUMN on a table with indexes referencing it in all
-- versions the test matrix covers (DROP COLUMN was added in 3.35; partial
-- unique index complicates the drop). Safest reverse is rebuild-and-rename:
-- create the pre-0010 run_log shape, copy the six original columns, drop
-- the new table, rename.

DROP INDEX IF EXISTS idx_run_log_run_uuid;

CREATE TABLE run_log_old (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    total_found INTEGER DEFAULT 0,
    new_jobs INTEGER DEFAULT 0,
    sources_queried INTEGER DEFAULT 0,
    per_source TEXT DEFAULT '{}'
);

INSERT INTO run_log_old (id, timestamp, total_found, new_jobs, sources_queried, per_source)
SELECT id, timestamp, total_found, new_jobs, sources_queried, per_source
FROM run_log;

DROP TABLE run_log;
ALTER TABLE run_log_old RENAME TO run_log;
