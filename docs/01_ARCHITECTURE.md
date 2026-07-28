# Architecture

## Data flow

```text
Moto Edge 50 Fusion
  → Google Drive / Incoming
  → Google Drive for Desktop
  → Stable-file detector
  → SHA-256 reservation
  → Metadata extraction
  → Image/video enrichment
  → Topic and caption routing
  → Telegram preview
  → Telegram original document
  → SQLite commit
  → Safety delay
  → Temporary queue cleanup
```

## Main components

### Queue scanner
Finds supported media in the incoming folders. It must wait until file size and modification time remain stable across checks.

### State database
Stores one durable record per SHA-256 and all Telegram results.

### Metadata service
Uses Pillow/EXIF tools for images and ffprobe for videos. Original bytes are never changed.

### Vision service
Runs locally. It may fail without blocking the archive.

### Telegram service
Creates preview and original messages, records IDs, and reconciles uncertain retries.

### Cleanup service
Runs separately from upload. It only handles records that passed all safety checks.

## State machine

```text
DISCOVERED
→ STABILITY_WAIT
→ HASHING
→ RESERVED
→ METADATA
→ ENRICHING
→ READY_TO_UPLOAD
→ PREVIEW_UPLOADING
→ PREVIEW_CONFIRMED
→ ORIGINAL_UPLOADING
→ BACKED_UP
→ CLEANUP_ELIGIBLE
→ CLEANED
```

Side states:

```text
RETRY_WAIT
NEEDS_REVIEW
PERMANENT_MEDIA_ERROR
CONFIGURATION_ERROR
INVARIANT_VIOLATION
```

A permanent recognition error does not equal a permanent media error.

## Fixed topic suggestion

- People
- Family & Groups
- Travel & Nature
- Everyday
- Screenshots & Documents
- Videos
- Misc

Specific people and labels remain searchable in captions.
