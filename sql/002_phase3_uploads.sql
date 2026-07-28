ALTER TABLE telegram_archive ADD COLUMN retry_stage TEXT;

CREATE TABLE IF NOT EXISTS upload_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER NOT NULL,
    attempt_type TEXT NOT NULL CHECK(attempt_type IN ('preview', 'original', 'original_only')),
    attempt_started_at TEXT NOT NULL,
    attempt_finished_at TEXT,
    request_filename TEXT,
    request_size INTEGER,
    group_id TEXT,
    topic_id TEXT,
    last_http_status INTEGER,
    outcome TEXT,
    telegram_message_id TEXT,
    error_code TEXT,
    error_message TEXT,
    next_retry_at TEXT,
    uncertain_since TEXT,
    FOREIGN KEY(media_id) REFERENCES media(id)
);

CREATE INDEX IF NOT EXISTS idx_upload_attempts_media_id ON upload_attempts(media_id);
