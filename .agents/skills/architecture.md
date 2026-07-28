# Skill: Architecture

## Objective
Protect the approved local-first design.

## Invariants
- Android uploads to temporary Google Drive.
- Windows laptop processes media.
- SQLite is the source of truth for processing state.
- Telegram is the archive target.
- Original files are documents.
- Recognition is optional enrichment.
- Exact duplicate protection uses SHA-256.
- Cleanup happens only after committed upload confirmation.

## Required outputs
Architecture changes must update:
- `docs/01_ARCHITECTURE.md`
- `DECISIONS.md`
- Relevant tests
