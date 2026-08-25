-- Phase 6.5I: Local Location Intelligence and MapLibre Integration

CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    country TEXT,
    state TEXT,
    city TEXT,
    place_name TEXT,
    osm_id TEXT,
    source TEXT,
    confidence INTEGER,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_location_coordinates ON locations(latitude, longitude);

CREATE TABLE IF NOT EXISTS location_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    radius REAL DEFAULT 0.05,
    custom_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_location_aliases_coords ON location_aliases(latitude, longitude);

-- Add explicit latitude and longitude coordinates to media table
ALTER TABLE media ADD COLUMN latitude REAL;
ALTER TABLE media ADD COLUMN longitude REAL;

