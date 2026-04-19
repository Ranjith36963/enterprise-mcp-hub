-- 0007_user_profile_versions: reverse migration.
DROP INDEX IF EXISTS idx_user_profile_versions_user_created;
DROP TABLE IF EXISTS user_profile_versions;
