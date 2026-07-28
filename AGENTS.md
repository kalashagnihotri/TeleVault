# Repository Agent Instructions

This file is a short compatibility entry point. The authoritative Antigravity agent definitions are in `.agents/agents.md`.

## Non-negotiable rules

1. Backup correctness is more important than recognition quality.
2. Recognition failure must never prevent upload.
3. Never delete a source file before Telegram confirms the original document upload and the database transaction commits.
4. Exact duplicate prevention uses full-file SHA-256 and a unique database constraint.
5. Perceptual similarity must never automatically suppress an upload.
6. Never expose secrets in code, logs, tests, screenshots, artifacts, or commits.
7. Never silently change Telegram topic routing rules.
8. All destructive actions must support dry-run mode.
9. Work phase-by-phase according to `TASKS.md`.
10. Read only the documents needed for the current task; avoid loading the entire repository context without reason.
