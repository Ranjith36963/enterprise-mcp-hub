-- 0007_user_profile_versions: append-only snapshot log for user profiles.
--
-- Pillar 1 Batch 1.8 (plan §4.8). Every `save_profile()` writes the
-- current CV + preferences blob as a new row here in addition to the
-- upsert on `user_profiles`. `user_profiles` stays the mutable tip;
-- `user_profile_versions` is the history trail — lets users see how
-- their CV parsing evolved, and lets support re-parse an older upload
-- without having the original file.
--
-- Size: each row is a CV + prefs JSON blob, typically ≲5 KB. Plan §8
-- risk table gives a retention heuristic: keep last 10 per user. Not
-- enforced in SQL — implemented in `storage.py` on each write.
--
-- `source_action` is a free-form audit label: "cv_upload",
-- "linkedin_upload", "github_refresh", "user_edit", "legacy_hydrate".

CREATE TABLE IF NOT EXISTS user_profile_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    source_action TEXT NOT NULL DEFAULT 'user_edit',
    cv_data TEXT,
    preferences TEXT
);

CREATE INDEX IF NOT EXISTS idx_user_profile_versions_user_created
    ON user_profile_versions(user_id, created_at DESC);
