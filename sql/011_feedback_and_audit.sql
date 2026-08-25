-- Phase 6.5G: Feedback, Audit Trail, Preferences, and Perceptual Hashes

CREATE TABLE IF NOT EXISTS face_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER NOT NULL,
    face_id INTEGER,
    action TEXT NOT NULL CHECK(action IN ('CONFIRM', 'REJECT', 'MERGE', 'IGNORE')),
    old_prediction TEXT,
    new_identity TEXT,
    person_id INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(media_id) REFERENCES media(id),
    FOREIGN KEY(person_id) REFERENCES people(person_id)
);

CREATE TABLE IF NOT EXISTS scene_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER NOT NULL,
    old_prediction TEXT,
    new_label TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(media_id) REFERENCES media(id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT,
    before_state TEXT,
    after_state TEXT,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_preferences (
    preference_key TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    affinity_score REAL NOT NULL DEFAULT 0.0,
    interaction_count INTEGER NOT NULL DEFAULT 0,
    last_interacted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS perceptual_hashes (
    media_id INTEGER PRIMARY KEY,
    dhash TEXT NOT NULL,
    phash TEXT NOT NULL,
    near_duplicate_cluster_id TEXT,
    is_primary INTEGER NOT NULL DEFAULT 1,
    computed_at TEXT NOT NULL,
    FOREIGN KEY(media_id) REFERENCES media(id)
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_events(action);
CREATE INDEX IF NOT EXISTS idx_face_feedback_media ON face_feedback(media_id);
CREATE INDEX IF NOT EXISTS idx_scene_feedback_media ON scene_feedback(media_id);
CREATE INDEX IF NOT EXISTS idx_perceptual_cluster ON perceptual_hashes(near_duplicate_cluster_id);
