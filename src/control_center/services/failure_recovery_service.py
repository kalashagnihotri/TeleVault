"""Consolidated Failure Recovery Center Service for Phase 6.5I.

Classifies failure root causes across the archive and provides 1-click batch remediation actions.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class FailureRecoveryService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def get_failure_overview(self) -> Dict[str, Any]:
        """Aggregate all failed media and group by diagnosed root cause."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, original_filename, original_path, media_type, state, face_state, scene_state, error_message, updated_at
                FROM media
                WHERE state = 'FAILED' OR face_state = 'FAILED' OR scene_state = 'FAILED'
                ORDER BY updated_at DESC
                """
            ).fetchall()

        failed_items = []
        root_causes = {
            "CORRUPTED_FILE": 0,
            "TELEGRAM_TIMEOUT": 0,
            "MISSING_MODEL": 0,
            "UNKNOWN_ERROR": 0,
        }

        for r in rows:
            err = (r["error_message"] or "").lower()
            if "corrupt" in err or "unreadable" in err or "truncate" in err or "cannot identify" in err:
                cause = "CORRUPTED_FILE"
            elif "timeout" in err or "network" in err or "telegram" in err or "connect" in err:
                cause = "TELEGRAM_TIMEOUT"
            elif "model" in err or "weight" in err or "onnx" in err:
                cause = "MISSING_MODEL"
            else:
                cause = "UNKNOWN_ERROR"

            root_causes[cause] += 1
            failed_items.append({
                "media_id": r["id"],
                "filename": r["original_filename"],
                "path": r["original_path"],
                "media_type": r["media_type"],
                "state": r["state"],
                "error_message": r["error_message"] or "Processing failed without explicit stacktrace",
                "diagnosed_cause": cause,
                "failed_at": r["updated_at"],
            })

        return {
            "total_failed_items": len(failed_items),
            "root_cause_breakdown": root_causes,
            "items": failed_items,
        }

    def retry_all_failed(self) -> Dict[str, Any]:
        """Reset state for all failed items to READY for worker re-ingestion."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE media 
                SET state = 'READY', 
                    face_state = CASE WHEN face_state = 'FAILED' THEN 'PENDING' ELSE face_state END,
                    scene_state = CASE WHEN scene_state = 'FAILED' THEN 'PENDING' ELSE scene_state END,
                    error_message = NULL,
                    updated_at = ?
                WHERE state = 'FAILED' OR face_state = 'FAILED' OR scene_state = 'FAILED'
                """,
                (now_iso,),
            )
            affected = cur.rowcount

            # Also record in audit ledger
            cur.execute(
                """
                INSERT INTO audit_events (actor, action, object_type, object_id, before_state, after_state, timestamp)
                VALUES ('failure_recovery_service', 'BATCH_RETRY_FAILED', 'archive', 'all', 'FAILED', ?, ?)
                """,
                (f"READY (reset_count={affected})", now_iso),
            )

        logger.info("Reset %d failed media assets to READY for retry", affected)
        return {
            "success": True,
            "reset_count": affected,
            "message": f"Successfully scheduled {affected} failed media assets for retry.",
        }

    def ignore_failure(self, media_id: int, reason: str = "User dismissed") -> Dict[str, Any]:
        """Mark a failed media item as IGNORED."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE media 
                SET state = 'IGNORED', updated_at = ? 
                WHERE id = ?
                """,
                (now_iso, media_id),
            )
        logger.info("Ignored failure for media #%d (reason=%s)", media_id, reason)
        return {"success": True, "media_id": media_id, "state": "IGNORED"}
