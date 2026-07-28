# Implementation Tasks

## Phase 0 — Workspace and safeguards

- [x] Copy `.env.example` to `.env`
- [x] Copy `config/config.example.yaml` to `config/config.yaml`
- [x] Confirm `.gitignore`
- [ ] Create test Telegram group
- [ ] Create temporary test Drive folder
- [x] Run repository audit

## Phase 1 — Local queue and exact duplicates

- [x] Configuration loader
- [x] Structured logging with redaction
- [x] SQLite migrations
- [x] Stable-file detection
- [x] Streaming SHA-256
- [x] Atomic hash reservation
- [x] Processing state machine
- [x] Dry-run report
- [x] Restart tests
- [x] Duplicate race test

Exit condition: files can be discovered, hashed, reserved, and safely resumed without uploads.

## Phase 2 — Metadata and routing

- [x] Image EXIF extraction
- [x] Video ffprobe extraction
- [x] No-GPS → Misc
- [x] Custom offline place matching
- [x] Optional local city dataset
- [x] Topic routing rules
- [x] Caption builder
- [x] Metadata corruption tests

Exit condition: each media file has deterministic metadata, caption, and proposed topic.

## Phase 3 — Telegram archive

- [x] Bot/group/topic validation
- [x] Preview photo upload
- [x] Original document upload
- [x] Reply linkage
- [x] Telegram ID persistence
- [x] Retry and uncertain-timeout reconciliation
- [x] Hosted API tests for small files
- [x] Local Bot API configuration
- [x] Large-file test
- [x] Cleanup eligibility flag

Exit condition: originals are archived without duplicates and cleanup remains disabled by default.

## Phase 4 — Cleanup lifecycle

- [x] Configurable safety delay
- [x] Recheck Telegram record before cleanup
- [x] Move to Completed or delete staging copy
- [x] Cleanup dry-run
- [x] Crash-before-delete tests
- [x] Manual restore instructions

Exit condition: temporary files are removed only after safe confirmation.

## Phase 5 — Face enrollment and matching

- [x] Reference folder scanner
- [x] Face quality checks
- [x] Local embedding database
- [x] Conservative threshold
- [x] Second-best margin
- [x] Multi-person result
- [x] Unknown fallback
- [x] Review workflow
- [x] False-positive tests

## Phase 6 — Scene categories

- [ ] Small local classifier interface
- [ ] Label mapping
- [ ] Morning-view time + scene rule
- [ ] Mountains
- [ ] River
- [ ] Lake
- [ ] Person
- [ ] Screenshot/document
- [ ] Unknown fallback

## Phase 7 — Three-pass video processing

- [ ] Pass 1 evenly spaced frames
- [ ] Pass 2 scene-change and face-priority frames
- [ ] Pass 3 broader diverse sampling
- [ ] Reuse earlier results
- [ ] Stop-on-confidence logic
- [ ] Thumbnail selection
- [ ] Temporary frame cleanup
- [ ] Long and corrupt video tests

## Phase 8 — Windows automation

- [ ] Task Scheduler setup
- [ ] Start when laptop wakes
- [ ] Network availability retry
- [ ] Single-instance lock
- [ ] Log rotation
- [ ] Health report
- [ ] Database backup
