---
description: Perform a production-readiness check
---

Act as `@qa`, `@security`, and `@devops`.

Verify:
- Tests pass
- Dry-run has no destructive behavior
- Secrets are absent from git
- Database migrations are safe
- Original upload is confirmed before cleanup
- Retry reconciliation prevents duplicate messages
- Large-file path is tested
- Logs are redacted and rotated
- Backup and restore instructions work
- Task Scheduler command is documented

Write `artifacts/RELEASE_CHECK.md`.
Do not declare ready when any data-loss issue remains.
