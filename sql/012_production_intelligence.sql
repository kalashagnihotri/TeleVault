-- Phase 6.5H: Final Production Intelligence Layer

CREATE TABLE IF NOT EXISTS image_embeddings (
    media_id INTEGER PRIMARY KEY,
    embedding_blob BLOB NOT NULL,
    dimension INTEGER NOT NULL DEFAULT 512,
    model_identity TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    FOREIGN KEY(media_id) REFERENCES media(id)
);

CREATE TABLE IF NOT EXISTS memory_overrides (
    memory_id TEXT PRIMARY KEY,
    original_ai_title TEXT NOT NULL,
    user_title TEXT,
    user_description TEXT,
    cover_media_id INTEGER,
    is_pinned INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(cover_media_id) REFERENCES media(id)
);

CREATE TABLE IF NOT EXISTS video_metadata (
    media_id INTEGER PRIMARY KEY,
    duration_seconds REAL NOT NULL DEFAULT 0.0,
    fps REAL NOT NULL DEFAULT 30.0,
    width INTEGER,
    height INTEGER,
    key_frames_json TEXT NOT NULL DEFAULT '[]',
    audio_codec TEXT,
    video_codec TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(media_id) REFERENCES media(id)
);

CREATE TABLE IF NOT EXISTS worker_nodes (
    worker_id TEXT PRIMARY KEY,
    node_name TEXT NOT NULL,
    ip_address TEXT,
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'ONLINE',
    last_heartbeat_at TEXT NOT NULL,
    current_job_id TEXT,
    processed_tasks_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS document_text (
    media_id INTEGER PRIMARY KEY,
    extracted_text TEXT NOT NULL,
    merchant_name TEXT,
    amount REAL,
    currency TEXT DEFAULT 'USD',
    document_date TEXT,
    category TEXT DEFAULT 'General Document',
    confidence REAL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(media_id) REFERENCES media(id)
);

CREATE TABLE IF NOT EXISTS plugins_registry (
    plugin_name TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    description TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    installed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_embeddings_model ON image_embeddings(model_identity);
CREATE INDEX IF NOT EXISTS idx_video_meta_duration ON video_metadata(duration_seconds);
CREATE INDEX IF NOT EXISTS idx_worker_nodes_status ON worker_nodes(status, last_heartbeat_at);
CREATE INDEX IF NOT EXISTS idx_doc_merchant ON document_text(merchant_name);
CREATE INDEX IF NOT EXISTS idx_doc_category ON document_text(category);
