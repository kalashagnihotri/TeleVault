CREATE TABLE IF NOT EXISTS people (
    person_id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_slug TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS face_references (
    reference_id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    source_sha256 TEXT NOT NULL,
    source_path TEXT NOT NULL,
    detector_confidence REAL,
    face_width INTEGER,
    face_height INTEGER,
    quality_json TEXT,
    embedding_blob BLOB,
    embedding_dimension INTEGER,
    model_identity TEXT,
    active BOOLEAN NOT NULL DEFAULT 1,
    enrolled_at TEXT NOT NULL,
    rejection_code TEXT,
    rejection_message TEXT,
    FOREIGN KEY(person_id) REFERENCES people(person_id)
);

CREATE TABLE IF NOT EXISTS face_calibrations (
    calibration_id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_identity TEXT NOT NULL,
    reference_set_hash TEXT NOT NULL,
    accept_threshold REAL NOT NULL,
    review_threshold REAL NOT NULL,
    minimum_margin REAL NOT NULL,
    positive_pair_count INTEGER NOT NULL,
    negative_pair_count INTEGER NOT NULL,
    generated_at TEXT NOT NULL,
    report_json TEXT,
    active BOOLEAN NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS face_analysis_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER NOT NULL,
    analysis_key TEXT NOT NULL,
    analysis_version INTEGER NOT NULL,
    model_identity TEXT NOT NULL,
    reference_set_hash TEXT NOT NULL,
    calibration_id INTEGER,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    outcome TEXT,
    detected_face_count INTEGER,
    accepted_match_count INTEGER,
    unknown_face_count INTEGER,
    error_code TEXT,
    error_message TEXT,
    FOREIGN KEY(media_id) REFERENCES media(id),
    FOREIGN KEY(calibration_id) REFERENCES face_calibrations(calibration_id),
    UNIQUE(media_id, analysis_key, analysis_version)
);

CREATE TABLE IF NOT EXISTS media_faces (
    media_face_id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER NOT NULL,
    attempt_id INTEGER NOT NULL,
    face_index INTEGER NOT NULL,
    bounding_box_json TEXT,
    landmarks_json TEXT,
    detector_confidence REAL,
    quality_json TEXT,
    embedding_blob BLOB,
    embedding_dimension INTEGER,
    model_identity TEXT,
    best_person_id INTEGER,
    best_score REAL,
    second_best_person_id INTEGER,
    second_best_score REAL,
    score_margin REAL,
    supporting_reference_count INTEGER,
    decision TEXT,
    analyzed_at TEXT NOT NULL,
    FOREIGN KEY(media_id) REFERENCES media(id),
    FOREIGN KEY(attempt_id) REFERENCES face_analysis_attempts(attempt_id),
    FOREIGN KEY(best_person_id) REFERENCES people(person_id),
    FOREIGN KEY(second_best_person_id) REFERENCES people(person_id)
);

-- Separate face-analysis state inside the media table, independent from normal 'state'
ALTER TABLE media ADD COLUMN face_state TEXT NOT NULL DEFAULT 'PENDING';
