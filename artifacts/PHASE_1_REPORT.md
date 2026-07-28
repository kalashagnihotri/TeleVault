# Phase 1 Report

## Goal Accomplished
Implemented Phase 1: Local queue and exact duplicates. 
The system can now reliably discover files in the configured local queue, calculate their full-file SHA-256 hashes, and reserve those hashes in the SQLite database to prevent duplicates. It safely handles interruptions (restarts) and duplicate files seamlessly.

## Components Implemented

### Configuration (`src/config.py`)
- Added strongly-typed dataclasses (e.g., `AppConfig`, `QueueConfig`, `TelegramConfig`).
- Implemented `load_config` which reads from `config/config.yaml` using PyYAML and pulls secrets from `.env` via `python-dotenv`.
- Ensures missing values gracefully fall back or initialize without crashing the early phases.

### Structured Logging with Redaction (`src/logger.py`)
- Created a standard Python `logging` setup that writes to the console and `logs/app.log`.
- Implemented a custom `RedactingFormatter` that searches log messages for active secrets (bot token, API hash) and aggressively replaces them with `***REDACTED***` to ensure safety.

### Atomic Hash Reservation (`src/database.py`)
- Added `reserve_media()`, which executes an atomic `INSERT ... ON CONFLICT DO NOTHING` to guarantee that duplicate concurrent files (or rapid scanner restarts) will never result in duplicate tracking records for the same exact file hash.

### Processing State Machine (`src/scanner.py`)
- The `QueueScanner` iterates through `incoming_images` and `incoming_videos`.
- Validates file stability utilizing the pre-existing `wait_until_stable` module.
- Hashes each file, calls `reserve_media`, and safely transitions state or logs duplicate warnings if a collision occurs.

### Main Wiring (`src/main.py`)
- Updated the CLI entry point to accept `--dry-run` properly.
- Ties the configuration, logger, and database together and starts a single `scan_once()` pass over the queue.

## Tests Added and Passing
- `tests/test_database.py`: **Duplicate race test**. Uses 10 simultaneous threads to attempt reserving the exact same hash, asserting that only 1 thread succeeds while the others fail gracefully.
- `tests/test_scanner.py`: **Restart tests**. Ensures the scanner can run against the same incoming queue repeatedly without throwing errors or causing duplicate reservations.

## Validation Results
- The system correctly runs in `--dry-run` mode (`python -m src.main --dry-run`).
- It iterates over the target folders but omits database insertions.
- `CHANGELOG.md` and `TASKS.md` have been updated to reflect the completion of Phase 1.
