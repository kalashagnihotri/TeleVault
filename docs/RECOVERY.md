# Disaster Recovery, Restore Verification & Data Export

## Non-Negotiable Recovery Principles
1. **Never delete source files before Telegram confirms upload** and the SQLite transaction commits.
2. **Backups must be validated with simulated restores** (`verify_restore_dryrun`).
3. **Standalone exports guarantee lifetime data independence** from Telegram Cloud.

---

## Automated Restore Verification Workflow

```
Active SQLite Database (data/archive.sqlite3)
                   |
                   v
1. Online Atomic Snapshot (`sqlite3.backup()`)
                   |
                   v
2. Restore into Isolated Temp DB (`data/temp_restore_verify.sqlite3`)
                   |
                   v
3. Execute `PRAGMA integrity_check`
                   |
                   v
4. Reconcile Exact Table Row Counts (media, telegram_archive, people, media_faces)
                   |
                   v
5. Verify 0 Discrepancies & Clean Up Temporary Files
```

To run a 1-click restore verification test:
```bash
curl -X POST http://localhost:8000/api/maintenance/restore/test
```

---

## Standalone Archive Export

To export your full media vault independent of Telegram:
```bash
curl -X POST http://localhost:8000/api/maintenance/export
```
This generates a complete JSON manifest under `data/exports/vault_export_<timestamp>.json` containing all media records, people identities, recognized tags, and life event memories.
