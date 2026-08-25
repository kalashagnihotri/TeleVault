# Database Architecture & Optimization Guide

## Overview
TeleVault utilizes SQLite in **WAL (Write-Ahead Logging)** mode with strict foreign key constraints and compound indexing designed to effortlessly support **100,000+** media assets.

---

## Schema Design

### Primary Tables
- **`media`**: Core asset metadata table (`id`, `sha256`, `original_filename`, `media_type`, `size_bytes`, `state`, `face_state`, `scene_state`, `labels_json`, `date_taken`, `location_label`).
- **`telegram_archive`**: Confirmed upload state (`media_id`, `group_id`, `topic_id`, `preview_message_id`, `original_message_id`, `upload_confirmed_at`).
- **`people`**: Enrolled known individuals (`person_id`, `person_slug`, `display_name`, `active`).
- **`media_faces`**: Face detections, bounding boxes, embeddings, and match decisions (`media_face_id`, `media_id`, `attempt_id`, `detector_confidence`, `best_person_id`, `best_score`, `decision`).
- **`face_analysis_attempts`**: Audit trail of face analysis runs (`attempt_id`, `media_id`, `outcome`, `detected_face_count`, `accepted_match_count`).
- **`processing_events`**: Chronological event log for ingestion, analysis, and error recovery.
- **`migration_registry`**: Versioned migration tracking with rollback SQL scripts (`version`, `name`, `purpose`, `rollback_available`, `rollback_sql`).

---

## Optimization & High-Scale Indexing (100k+ Assets)

The following compound indexes guarantee sub-millisecond query performance:
```sql
CREATE INDEX IF NOT EXISTS idx_media_state ON media(state);
CREATE INDEX IF NOT EXISTS idx_media_updated_at ON media(updated_at);
CREATE INDEX IF NOT EXISTS idx_media_state_date ON media(state, date_taken);
CREATE INDEX IF NOT EXISTS idx_archive_route_key ON telegram_archive(route_key);
CREATE INDEX IF NOT EXISTS idx_media_location_date ON media(location_label, date_taken);
```

---

## Migration Runner & Rollbacks

Migrations are placed in `sql/*.sql` and executed sequentially:
- Schema updates are verified and recorded in `schema_migrations` and `migration_registry`.
- Migrations with `rollback_available = 1` can be rolled back on-demand via the Control Center API (`POST /api/database/migrations/{version}/rollback`).
