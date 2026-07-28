-- Phase 4: Cleanup state and attempts

ALTER TABLE media ADD COLUMN cleanup_state TEXT NOT NULL DEFAULT 'PENDING';

CREATE TABLE IF NOT EXISTS cleanup_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER NOT NULL,
    mode TEXT NOT NULL,
    source_path TEXT NOT NULL,
    destination_path TEXT,
    attempt_started_at TEXT NOT NULL,
    attempt_finished_at TEXT,
    outcome TEXT,
    error_code TEXT,
    error_message TEXT,
    FOREIGN KEY(media_id) REFERENCES media(id)
);

CREATE INDEX IF NOT EXISTS idx_cleanup_attempts_media_id ON cleanup_attempts(media_id);
