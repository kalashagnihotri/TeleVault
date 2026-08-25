-- Phase 6.5I, 6.5J & Phase 7: Production Reliability, Personal AI & Architecture Evolution

CREATE TABLE IF NOT EXISTS pipeline_execution_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER NOT NULL,
    stage TEXT NOT NULL,
    model_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    result_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'SUCCESS',
    timestamp TEXT NOT NULL,
    FOREIGN KEY(media_id) REFERENCES media(id)
);

CREATE TABLE IF NOT EXISTS memories (
    memory_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    total_photos INTEGER DEFAULT 0,
    cover_media_id INTEGER,
    is_curated INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS models_registry (
    model_name TEXT NOT NULL,
    version TEXT NOT NULL,
    category TEXT NOT NULL,
    sha256 TEXT,
    description TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    registered_at TEXT NOT NULL,
    PRIMARY KEY (model_name, version)
);

CREATE TABLE IF NOT EXISTS config_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    yaml_snapshot TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    reason TEXT,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_priority_queue (
    job_id TEXT PRIMARY KEY,
    media_id INTEGER NOT NULL,
    task_type TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 2,
    payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'QUEUED',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error_message TEXT,
    FOREIGN KEY(media_id) REFERENCES media(id)
);

CREATE TABLE IF NOT EXISTS calendar_events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    location TEXT,
    description TEXT,
    matched_media_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS location_hierarchy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER NOT NULL,
    latitude REAL,
    longitude REAL,
    city TEXT,
    state TEXT,
    country TEXT,
    venue_name TEXT,
    visit_count INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY(media_id) REFERENCES media(id)
);

CREATE TABLE IF NOT EXISTS api_tokens (
    token_id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    scopes_json TEXT NOT NULL DEFAULT '["read", "photos", "memories"]',
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_pipe_hist_media ON pipeline_execution_history(media_id, stage);
CREATE INDEX IF NOT EXISTS idx_pipe_hist_ts ON pipeline_execution_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_queue_status_prio ON job_priority_queue(status, priority, created_at);
CREATE INDEX IF NOT EXISTS idx_cal_dates ON calendar_events(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_loc_city ON location_hierarchy(city, country);
