"""
Snapshot Service for Control Center.
Generates and manages unified system snapshot bundles:
- Archive database (via atomic SQLite backup API)
- Control Center database (via atomic SQLite backup API)
- Configuration file (config.yaml)
- System and models metadata manifest
"""
from __future__ import annotations

import json
import logging
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import load_config
from src.control_center.services import db_service

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = Path("data/system_snapshots")
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def create_snapshot() -> Dict[str, Any]:
    """Create a unified .zip system snapshot bundle."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_filename = f"snapshot_{ts}.zip"
    snapshot_path = SNAPSHOT_DIR / snapshot_filename
    temp_dir = SNAPSHOT_DIR / f".tmp_{ts}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        config = load_config()
        archive_db_path = Path(config.app.database_path)
        cc_db_path = db_service.DB_PATH
        config_path = Path("config/config.yaml")

        # 1. Backup Archive DB
        archive_backup_path = temp_dir / "archive.sqlite3"
        media_count = 0
        if archive_db_path.exists():
            src_conn = sqlite3.connect(str(archive_db_path))
            dest_conn = sqlite3.connect(str(archive_backup_path))
            src_conn.backup(dest_conn)
            media_row = src_conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='media'").fetchone()
            if media_row and media_row[0]:
                cnt = src_conn.execute("SELECT COUNT(*) FROM media").fetchone()
                media_count = cnt[0] if cnt else 0
            dest_conn.close()
            src_conn.close()

        # 2. Backup Control Center DB
        cc_backup_path = temp_dir / "control_center.sqlite3"
        if cc_db_path.exists():
            src_cc = sqlite3.connect(str(cc_db_path))
            dest_cc = sqlite3.connect(str(cc_backup_path))
            src_cc.backup(dest_cc)
            dest_cc.close()
            src_cc.close()

        # 3. Copy Config
        saved_config_path = temp_dir / "config.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f_in, open(saved_config_path, "w", encoding="utf-8") as f_out:
                f_out.write(f_in.read())

        # 4. Write Manifest
        now_iso = datetime.now(timezone.utc).isoformat()
        manifest_data = {
            "snapshot_id": f"snap-{ts}",
            "created_at": now_iso,
            "version": "6.5C",
            "media_rows": media_count,
            "archive_db_included": archive_db_path.exists(),
            "control_center_db_included": cc_db_path.exists(),
            "config_included": config_path.exists()
        }
        manifest_file = temp_dir / "manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as mf:
            json.dump(manifest_data, mf, indent=2)

        # 5. Zip Bundle
        with zipfile.ZipFile(snapshot_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in temp_dir.iterdir():
                if item.is_file():
                    zf.write(item, arcname=item.name)

        size_bytes = snapshot_path.stat().st_size
        logger.info("System snapshot created: %s (%d bytes)", snapshot_filename, size_bytes)

        # Add notification to DB
        db_service.add_notification(
            level="SUCCESS",
            title="System Snapshot Created",
            message=f"Created backup snapshot {snapshot_filename} ({size_bytes // 1024} KB)."
        )

        return {
            "filename": snapshot_filename,
            "path": str(snapshot_path),
            "size_bytes": size_bytes,
            "created_at": now_iso,
            "manifest": manifest_data
        }

    finally:
        # Cleanup temp directory
        for f in temp_dir.glob("*"):
            f.unlink(missing_ok=True)
        temp_dir.rmdir()


def list_snapshots() -> List[Dict[str, Any]]:
    """List all available system snapshots."""
    if not SNAPSHOT_DIR.exists():
        return []

    snapshots: List[Dict[str, Any]] = []
    for f in sorted(SNAPSHOT_DIR.glob("snapshot_*.zip"), reverse=True):
        try:
            st = f.stat()
            manifest = {}
            # Read manifest from zip
            with zipfile.ZipFile(f, "r") as zf:
                if "manifest.json" in zf.namelist():
                    manifest = json.loads(zf.read("manifest.json").decode("utf-8"))

            snapshots.append({
                "filename": f.name,
                "path": str(f),
                "size_bytes": st.st_size,
                "created_at": manifest.get("created_at") or datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                "manifest": manifest
            })
        except Exception as e:
            logger.warning("Error reading snapshot %s: %s", f.name, e)

    return snapshots


def get_snapshot_file_path(filename: str) -> Optional[Path]:
    """Return verified path to snapshot file for download."""
    p = SNAPSHOT_DIR / Path(filename).name
    if p.exists() and p.is_file():
        return p
    return None
