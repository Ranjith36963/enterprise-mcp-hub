-- 0008_job_enrichment: reverse migration.
DROP INDEX IF EXISTS idx_job_enrichment_job_id;
DROP TABLE IF EXISTS job_enrichment;
