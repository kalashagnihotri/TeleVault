# Error and Recovery Rules

## Drive file still syncing
State: `STABILITY_WAIT`
Action: retry later without hashing.

## Unsupported or corrupt image
Record metadata error. Attempt original document archive with a basic caption.

## Unsupported or corrupt video
Skip recognition. Attempt original document archive.

## GPU failure
Log warning, switch to CPU, continue.

## Face model failure
Use `Unknown Person`, continue.

## Scene model failure
Use no scene labels, continue.

## ffprobe missing
Configuration error for video enrichment. Images may continue. Videos may still be archived if basic file handling works.

## Telegram rate limit
Respect server retry information. Use capped backoff.

## Telegram timeout before response
Treat as uncertain. Reconcile before retrying.

## Database locked
Retry briefly. If persistent, stop the current worker without deleting files.

## Disk full
Stop processing and cleanup. Preserve queue and database. Raise a high-priority error.

## Original upload fails
Do not clean the Drive file. Preview may remain; retry original safely.

## Cleanup fails
Keep `BACKED_UP` state and retry cleanup later. Never re-upload merely because cleanup failed.

## Hash mismatch after processing
Invariant violation. Stop destructive actions and re-read the file.
