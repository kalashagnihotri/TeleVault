# Ingestion & Processing Pipeline Guide

## Pipeline Lifecycle

```
[ Incoming Media ]
        |
        v
1. Byte Stability Check (60s quiet window)
        |
        v
2. Canonical SHA-256 Hashing & Deduplication
        |
        v
3. Metadata Extraction (EXIF dates, GPS coordinates, dimensions)
        |
        v
4. Face Recognition (YuNet Detection + SFace Embedding Matching)
        |
        v
5. Scene Classification (Places365 + Heuristic Rules)
        |
        v
6. Policy-Based Topic Routing & Rich Caption Generation
        |
        v
7. Two-Phase Telegram Archival (Preview Photo + Raw Document)
        |
        v
8. Atomic Database Confirmation & Safe Cleanup
```

---

## Processing Stages & Observability Latencies

| Pipeline Stage | Expected Latency | Metrics Key | Failure Reasons |
|---|---|---|---|
| **Metadata Extraction** | 40 – 120 ms | `metadata_ms` | Corrupted EXIF header, unsupported format |
| **Face Analysis** | 750 – 1100 ms | `face_ms` | Missing ONNX weights, face blur, out of memory |
| **Scene Analysis** | 1800 – 2300 ms | `scene_ms` | Places365 model missing, invalid image dimensions |
| **Telegram Upload** | 2800 – 3600 ms | `upload_ms` | Telegram timeout, rate limit, token invalid |

---

## Retry Intelligence & Failure Handling

When a transient network error or rate limit occurs:
- The item is scheduled in the retry queue (`schedule_retry()`).
- Exponential backoff is applied (e.g. 30s, 60s, 120s, up to 5 attempts).
- Non-destructive queue isolation moves permanently unrecoverable items to `failed/` without touching source archives.
