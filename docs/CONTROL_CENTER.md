# Control Center Operations & API Reference

## Overview
The **Control Center** is a FastAPI-powered management interface and React single-page application for monitoring pipelines, managing face/scene intelligence, reliving memories, and running maintenance tasks.

---

## Key REST API Endpoints

### 1. Observability & Metrics
- `GET /api/metrics/pipeline`: Stage latencies (avg, p50, p95) and total throughput.
- `GET /api/metrics/failures`: Root-cause failure counters.
- `GET /api/metrics/retries`: Active retry queue.

### 2. Data Integrity & Health Scanner
- `POST /api/integrity/scan`: Triggers deep archive health scan.
- `GET /api/integrity/report`: Returns the latest integrity report.

### 3. Face & Scene Intelligence
- `GET /api/faces/unknown_clusters`: Clusters of unidentified faces for user review.
- `POST /api/faces/clusters/create_person`: Enrolls a new person from a cluster.
- `POST /api/faces/merge_identities`: Merges duplicate identities.
- `GET /api/scenes/{media_id}/confidence`: Exposes per-label confidence scores.
- `POST /api/scenes/reprocess`: Batch reprocessing of pending/failed scenes.

### 4. Memory Engine & Highlights
- `GET /api/archive/memories`: Clustered life events and narrative stories.
- `GET /api/archive/highlights`: Similarity-suppressed top highlights.
- `POST /api/archive/chat`: Conversational memory Q&A.
- `GET /api/archive/quality`: 100-point AI-readiness scoreboard.

### 5. Media Delivery & Thumbnails
- `GET /api/media/{id}/thumbnail`: 120px cached thumbnail.
- `GET /api/media/{id}/preview`: 600px cached preview.
- `GET /api/media/{id}/raw`: Full original media stream.

### 6. Disaster Recovery & Maintenance
- `POST /api/maintenance/restore/test`: Dry-run restore test in isolated temp DB.
- `POST /api/maintenance/export`: Standalone archive JSON export.
- `GET /api/system/security_audit`: Automated secret leak detection scanner.
