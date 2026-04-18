-- 0005_user_channels: per-user notification channel configuration.
-- Credentials encrypted with Fernet (blueprint §1 + decisions doc §D10).
--
-- channel_type values map to Apprise URL schemes:
--   email    -> mailtos://user:pass@smtp.gmail.com?to=dest
--   slack    -> slack://tokenA/tokenB/tokenC
--   discord  -> discord://webhook_id/webhook_token
--   telegram -> tgram://bot_token/chat_id
--   webhook  -> json://host/path

CREATE TABLE IF NOT EXISTS user_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel_type TEXT NOT NULL,
    display_name TEXT NOT NULL,
    credential_encrypted BLOB NOT NULL,
    key_version INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_channels_user ON user_channels(user_id, enabled);
