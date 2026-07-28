# Changelog

## Unreleased

- Completed Phase 3: Safe Telegram uploads
  - Fixed original document `caption` TypeError bug in `TelegramClient` and added automated recovery
  - Repaired legacy string routes in `telegram_archive.topic_id` via `sql/003_route_key.sql` and data repair routine
  - Resolved dynamic numeric `group_id` and `topic_id` resolution at upload time
  - Migrated main routine to `asyncio` (`src/main.py`)
  - Added async `ArchiveUploader` with size preflighting (`src/uploader.py`)
  - Added robust database schema migration tracker (`src/database.py`)
  - Added preview generation fallbacks (`src/preview.py`)
  - Validated API payload formats (`src/telegram_client.py`)
- Completed Phase 2: Metadata and routing
  - Image EXIF extraction using Pillow (`src/metadata_image.py`)
  - Video metadata extraction using ffprobe (`src/metadata_video.py`)
  - Added deterministic Telegram routing rules (`src/routing.py`)
  - Added deterministic caption builder (`src/captions.py`)
  - Added offline custom place matching via `config/places.json` (`src/places.py`)
- Completed Phase 1: Local queue and exact duplicates
  - Implemented typed configuration loader (`src/config.py`)
  - Added structured logging with automatic secret redaction (`src/logger.py`)
  - Added atomic hash reservation in SQLite database (`src/database.py`)
  - Added queue processing state machine for dry runs (`src/scanner.py`)
- Initial planning and Antigravity workspace kit.
