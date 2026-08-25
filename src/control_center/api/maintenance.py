"""
Maintenance & Notifications API for Control Center.
"""
from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.control_center.services import snapshot_service, db_service

router = APIRouter()


class SnapshotResponse(BaseModel):
    filename: str
    path: str
    size_bytes: int
    created_at: str
    manifest: Dict[str, Any] = {}


class NotificationItem(BaseModel):
    id: str
    level: str
    title: str
    message: str
    created_at: str
    read: int


@router.get("/maintenance/snapshots", response_model=List[SnapshotResponse])
def list_system_snapshots():
    """List all available full system snapshot bundles."""
    return snapshot_service.list_snapshots()


@router.post("/maintenance/snapshots/create", response_model=SnapshotResponse)
def create_system_snapshot():
    """Create a unified full system snapshot bundle."""
    try:
        return snapshot_service.create_snapshot()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Snapshot creation failed: {e}")


@router.get("/maintenance/snapshots/{filename}/download")
def download_system_snapshot(filename: str):
    """Download a system snapshot zip file."""
    path = snapshot_service.get_snapshot_file_path(filename)
    if not path:
        raise HTTPException(status_code=404, detail="Snapshot file not found.")
    return FileResponse(
        path=path,
        media_type="application/zip",
        filename=filename
    )


@router.get("/notifications", response_model=List[NotificationItem])
def get_notifications(limit: int = 50):
    """Return recent notifications and system event alerts."""
    return db_service.get_notifications(limit=limit)


@router.post("/notifications/{notification_id}/read")
def mark_notification_as_read(notification_id: str):
    """Mark a notification as read."""
    success = db_service.mark_notification_read(notification_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "success"}


# ==============================================================================
# DISASTER RECOVERY, RESTORE VERIFICATION & EXPORT ENDPOINTS (Phase 6.5F)
# ==============================================================================

@router.post("/maintenance/restore/test")
def test_backup_restore(backup_filename: str = None):
    """Perform a dry-run disaster recovery restore test and verify zero data loss."""
    from src.control_center.services import disaster_recovery_service
    try:
        return disaster_recovery_service.verify_restore_dryrun(backup_filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/maintenance/export")
def export_archive_manifest():
    """Export complete archive manifest independent of Telegram."""
    from src.control_center.services import disaster_recovery_service
    try:
        return disaster_recovery_service.export_standalone_archive()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/database/audit")
def audit_database():
    """Audit database indexes, WAL mode, integrity check, and high-scale readiness."""
    from src.config import load_config
    from src.database import ArchiveDatabase
    try:
        config = load_config()
        db = ArchiveDatabase(config.app.database_path)
        return db.audit_database()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/database/migrations")
def get_migration_registry():
    """Get migration registry with rollback metadata."""
    from src.config import load_config
    from src.database import ArchiveDatabase
    try:
        config = load_config()
        db = ArchiveDatabase(config.app.database_path)
        return db.get_migration_registry()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/database/migrations/{version}/rollback")
def rollback_migration(version: str):
    """Roll back a specific migration if supported."""
    from src.config import load_config
    from src.database import ArchiveDatabase
    try:
        config = load_config()
        db = ArchiveDatabase(config.app.database_path)
        return db.rollback_migration(version)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notifications/read_all")
def mark_all_notifications_as_read():
    """Mark all notifications as read."""
    count = db_service.mark_all_notifications_read()
    return {"status": "ok", "updated": count}
