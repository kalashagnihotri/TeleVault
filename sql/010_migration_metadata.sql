-- Migration 010: Database Migration Registry, Rollback Metadata & High-Scale Indexing

CREATE TABLE IF NOT EXISTS migration_registry (
    version TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    purpose TEXT NOT NULL,
    rollback_available INTEGER NOT NULL DEFAULT 0,
    rollback_sql TEXT,
    applied_at TEXT NOT NULL
);

-- Populate initial migration tracking
INSERT OR IGNORE INTO migration_registry (version, name, purpose, rollback_available, rollback_sql, applied_at)
VALUES 
    ('001', '001_initial.sql', 'Core schema: media, telegram_archive, queue_state', 0, NULL, CURRENT_TIMESTAMP),
    ('006', '006_faces.sql', 'Face analysis: people, media_faces, face_attempts', 0, NULL, CURRENT_TIMESTAMP),
    ('008', '008_scenes.sql', 'Scene analysis labels and heuristic columns', 0, NULL, CURRENT_TIMESTAMP),
    ('010', '010_migration_metadata.sql', 'Migration rollback registry and 100k scale indexing', 1, 'DROP TABLE IF EXISTS migration_registry;', CURRENT_TIMESTAMP);

-- High-scale compound indexes for 100k+ records
CREATE INDEX IF NOT EXISTS idx_media_state_date ON media(state, date_taken);
CREATE INDEX IF NOT EXISTS idx_archive_route_key ON telegram_archive(route_key);
CREATE INDEX IF NOT EXISTS idx_media_location_date ON media(location_label, date_taken);
