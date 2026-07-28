# Project Audit Report

## Current Phase
The project is currently transitioning from **Phase 0** (Workspace and safeguards) to **Phase 1** (Local queue and exact duplicates).

## Completed Items
- **Phase 0**: `.gitignore` is confirmed and correctly ignores sensitive files (like `.env`, `config.yaml`, data directories).
- **Phase 1 (Partial)**: 
  - Stable-file detection is implemented in `src/file_stability.py`.
  - Streaming SHA-256 generation is implemented in `src/hashing.py`.
  - SQLite database wrapper is present in `src/database.py`, along with initial migration logic (`sql/001_initial.sql`).

## Missing Items
- **Phase 0**:
  - `config/config.yaml` and `.env` have not been copied from their examples.
  - Test Telegram group and temporary Drive folder setup.
- **Phase 1**:
  - Configuration loader.
  - Structured logging with redaction.
  - Atomic hash reservation (currently only `hash_exists` read check is implemented).
  - Processing state machine.
  - Dry-run report generation.
  - Testing: Restart tests and duplicate race tests.

## Data-Loss Risks
- **No State Machine Yet**: File processing state is currently untracked. If a crash occurs, there is no resume mechanism.
- **Incomplete Stability Enforcement**: We must ensure `wait_until_stable` is invoked before any file is hashed or uploaded, otherwise corrupted/partial files may be processed and permanently marked as handled.

## Duplicate Risks
- **Race Condition in Database**: `database.py` currently checks `hash_exists` using a `SELECT` statement. This is not atomic. To prevent duplicates safely, hash reservation must use atomic `INSERT ... ON CONFLICT` or similar constraint-based reservations.

## Security Risks
- **Missing Log Redaction**: Since structured logging with redaction is missing, any debug logs added in the near future might leak tokens, APIs, or personal GPS data.
- **Secrets Management**: Setup scripts or manual runs might fail safely if `.env` is absent, but we need to ensure the system strictly enforces the absence of fallback secrets in code.

## Recommended Next Task
1. **Complete Phase 0**: Copy `.env.example` to `.env` and `config/config.example.yaml` to `config/config.yaml`.
2. **Phase 1 Initialization**: Implement the Configuration loader and Structured logging with redaction.
3. **Fix Atomic Hash Reservation**: Update `database.py` to support atomic reservation of SHA-256 hashes before building the main processing state machine.
