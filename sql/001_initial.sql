PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256 TEXT NOT NULL UNIQUE,
    short_hash TEXT NOT NULL,
    original_path TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    media_type TEXT NOT NULL CHECK(media_type IN ('image', 'video', 'other')),
    size_bytes INTEGER NOT NULL,
    modified_ns INTEGER NOT NULL,
    state TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    date_taken TEXT,
    has_gps INTEGER NOT NULL DEFAULT 0,
    location_label TEXT NOT NULL DEFAULT 'Misc',
    people_json TEXT NOT NULL DEFAULT '[]',
    labels_json TEXT NOT NULL DEFAULT '[]',
    error_code TEXT,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS telegram_archive (
    media_id INTEGER PRIMARY KEY,
    group_id TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    preview_message_id TEXT,
    original_message_id TEXT,
    telegram_file_id TEXT,
    upload_confirmed_at TEXT,
    FOREIGN KEY(media_id) REFERENCES media(id)
);

CREATE TABLE IF NOT EXISTS processing_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER,
    event_type TEXT NOT NULL,
    event_time TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(media_id) REFERENCES media(id)
);

CREATE INDEX IF NOT EXISTS idx_media_state ON media(state);
CREATE INDEX IF NOT EXISTS idx_media_updated_at ON media(updated_at);
