# Phase 3 Completion Report: Safe Telegram Uploads

Phase 3 is now complete and verified. The codebase natively supports state-tracked, resumable, duplicate-safe uploads to Telegram.

## Highlights
- **100% Async Core**: Migrated the main entrypoint to `asyncio` to natively stream files over HTTP without blocking other routines.
- **Fail-Safe Previews**: Image previews are resized with Pillow (`<= 1280px`). Video thumbnails are extracted via `ffmpeg` using multiple cascading fallback timestamps (`1s`, `5s`, `0s`) for robustness.
- **Atomic Reliability**: Every start of an upload logs an attempt to `upload_attempts`. Every success or failure atomically completes the attempt and transitions the item to its next state (`PREVIEW_CONFIRMED`, `BACKED_UP`, `NEEDS_REVIEW`, `RETRY_WAIT`).
- **Resilient to Missing Previews**: If generating a preview fails completely, the engine gracefully transitions to sending only the original document with the caption embedded, ensuring the backup continues unhindered.
- **Preflight Boundary Verification**: Enforces hosted API file size limits (`50MB`) and Local Bot API limits strictly, marking oversized files without attempting hopeless network requests.

## Test Coverage
19 regression and feature tests cover all rules, including:
- Migrations from older databases.
- `RETRY_WAIT` only resuming the exact failed stage (Preview vs Original).
- Fallback paths and missing topic errors only stalling the affected record.
- **Strict Payload Validation**: Checks for proper `file_id` and strictly validates optional `message_thread_id` integrity if the Telegram API responds with it.

## Routing Repair & Architecture Fix
Legacy records stored string names in the database's numeric Telegram ID fields, causing upload failures. A new architectural boundary was established:
- The Scanner isolates its responsibility to assigning a string `route_key`.
- The Database purely persists this string `route_key` via schema version `003_route_key.sql`.
- The Uploader handles resolving numeric, dynamic `group_id` and `topic_id` directly from `config.yaml` just-in-time for the API payload.
An idempotent data repair script automatically recovers historically crashed `NEEDS_REVIEW` files and transitions them seamlessly into the active queue on startup.

## Original Document Bug Fix & Recovery
Resolved an issue where `TelegramClient.send_original_document()` rejected the `caption` argument, crashing Phase 3 uploads after the preview had already succeeded. The logic is now robust:
- For standard uploads (preview succeeds), the original document is sent replying to the preview without redundantly re-sending the caption.
- For fallback uploads (preview fails), the original document is sent directly to the topic, attaching the full multipart caption and omitting any reply target.
- A targeted, idempotent recovery routine recovers these specific failed cases from `NEEDS_REVIEW` back to `PREVIEW_CONFIRMED`, carefully ignoring uncertain attempts that might have timed out.

## Migration Stability
A robust `schema_migrations` tracking system has been retrofitted onto the initialization process. It detects partial installations of Phase 2 and Phase 3 schemas, patching any missing columns or tables (e.g., safely adding `upload_attempts`) while suppressing redundant `ALTER TABLE` crashes during repeated startups.

The project is now fully functional for Phase 3!
