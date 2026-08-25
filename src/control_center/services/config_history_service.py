"""Git-like Configuration Versioning Service for Phase 6.5I.

Maintains immutable YAML configuration snapshots, hashes, textual diff generation, and rollback capabilities.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class ConfigHistoryService:
    def __init__(self, db_path: Path, config_file_path: Path) -> None:
        self.db_path = db_path
        self.config_file_path = config_file_path
        self._ensure_initial_snapshot()

    def _ensure_initial_snapshot(self) -> None:
        """Capture initial snapshot if none exists."""
        with sqlite3.connect(self.db_path) as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM config_versions").fetchone()[0]
            if cnt == 0 and self.config_file_path.exists():
                text = self.config_file_path.read_text(encoding="utf-8")
                self.record_snapshot(text, changed_by="system", reason="Initial configuration baseline")

    def record_snapshot(self, yaml_content: str, changed_by: str = "user", reason: Optional[str] = None) -> int:
        """Save a new version snapshot."""
        cfg_hash = hashlib.sha256(yaml_content.encode("utf-8")).hexdigest()[:16]
        now_iso = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO config_versions (yaml_snapshot, config_hash, changed_by, reason, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (yaml_content, cfg_hash, changed_by, reason or "Configuration update", now_iso),
            )
            v_id = cur.lastrowid or 0
        logger.info("Recorded configuration version #%d (hash=%s by %s)", v_id, cfg_hash, changed_by)
        return v_id

    def list_versions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return list of configuration versions."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, config_hash, changed_by, reason, timestamp, LENGTH(yaml_snapshot) as size_bytes FROM config_versions ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_version(self, version_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve full snapshot for a specific version."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            r = conn.execute(
                "SELECT id, yaml_snapshot, config_hash, changed_by, reason, timestamp FROM config_versions WHERE id = ?",
                (version_id,),
            ).fetchone()
        return dict(r) if r else None

    def compare_versions(self, v_old_id: int, v_new_id: int) -> Dict[str, Any]:
        """Compute textual unified diff between two configuration versions."""
        v_old = self.get_version(v_old_id)
        v_new = self.get_version(v_new_id)
        if not v_old or not v_new:
            raise ValueError("One or both configuration versions not found.")

        old_lines = v_old["yaml_snapshot"].splitlines(keepends=True)
        new_lines = v_new["yaml_snapshot"].splitlines(keepends=True)
        diff = list(difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"v{v_old_id} ({v_old['timestamp'][:16]})",
            tofile=f"v{v_new_id} ({v_new['timestamp'][:16]})",
            n=3,
        ))

        return {
            "v_old_id": v_old_id,
            "v_new_id": v_new_id,
            "diff_text": "".join(diff),
            "lines_changed": len([l for l in diff if l.startswith("+") or l.startswith("-")]),
        }

    def rollback_to_version(self, version_id: int, changed_by: str = "user") -> Dict[str, Any]:
        """Restore configuration to a previous version and write to config file."""
        target_v = self.get_version(version_id)
        if not target_v:
            raise ValueError(f"Version #{version_id} not found.")

        self.config_file_path.write_text(target_v["yaml_snapshot"], encoding="utf-8")
        new_v_id = self.record_snapshot(
            target_v["yaml_snapshot"],
            changed_by=changed_by,
            reason=f"Rollback to version #{version_id}",
        )
        logger.info("Rolled back config to version #%d (new version #%d created)", version_id, new_v_id)
        return {
            "success": True,
            "restored_version_id": version_id,
            "new_version_id": new_v_id,
            "timestamp": target_v["timestamp"],
        }
