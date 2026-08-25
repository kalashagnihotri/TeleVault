# Troubleshooting & Diagnostics Guide

## Common Diagnostics & Resolutions

### 1. Database Locked / Busy Errors (`sqlite3.OperationalError: database is locked`)
- **Cause**: Long-running synchronous writes or missing WAL mode.
- **Resolution**:
  - Verify WAL mode is active: `PRAGMA journal_mode;` should return `wal`.
  - Check `GET /api/database/audit` for index and lock status.

### 2. Telegram Upload Timeouts or Rate Limits
- **Cause**: Network jitter or Telegram Bot API flood limits.
- **Resolution**:
  - The pipeline automatically backs off and records retry status in `GET /api/metrics/retries`.
  - For files exceeding 50 MB, ensure local Bot API server or MTProto upload mode is enabled.

### 3. Face Recognition Mismatches or Unknown Clusters
- **Cause**: Person enrolled with insufficient reference photos or extreme lighting angles.
- **Resolution**:
  - Open **Archive Explorer $\rightarrow$ Face Review Queue**.
  - Review clusters via `GET /api/faces/unknown_clusters`.
  - Merge duplicate names with `POST /api/faces/merge_identities`.

### 4. Zero-Byte or Corrupted Ingestion Files
- **Cause**: File transfer interrupted before upload completed.
- **Resolution**:
  - Trigger **Archive Health Scan** via `POST /api/integrity/scan`.
  - Review flagged files in the integrity report.
  - Delete or re-upload from source queue.

### 5. Automated Security Audit
- Run security audit to verify no credentials leak into logs:
  ```bash
  curl http://localhost:8000/api/system/security_audit
  ```
