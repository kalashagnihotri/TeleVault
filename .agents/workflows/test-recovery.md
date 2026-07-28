---
description: Test crash, retry, and duplicate recovery
---

Act as `@qa`.

Test at minimum:
- Crash after hash reservation
- Crash during metadata extraction
- Crash before preview upload
- Timeout after preview upload
- Timeout after original upload
- Crash before database commit
- Restart with `UPLOADING` state
- Same SHA-256 arriving under another filename
- Corrupt image
- Corrupt video
- Missing ffprobe
- Database locked
- Drive file still syncing

Create `artifacts/RECOVERY_TEST_REPORT.md`.
Do not delete test evidence until the report is written.
