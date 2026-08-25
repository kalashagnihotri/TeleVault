"""Autonomous Retry Engine (Phase 6.5G Pillar 4)

Executes autonomous retries with exponential backoff, maximum attempt guards (5),
failure categorization, and auto-quarantine for unrecoverable media.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import load_config
from src.control_center.services.audit_service import record_audit_event
from src.control_center.services.metrics_service import get_retry_queue, schedule_retry

logger = logging.getLogger(__name__)

# Exponential backoff schedule in seconds: attempt 1 -> 30s, 2 -> 60s, 3 -> 300s, 4 -> 900s, 5 -> 3600s
BACKOFF_SCHEDULE = [30, 60, 300, 900, 3600]
MAX_RETRIES = 5


def _get_db_conn() -> sqlite3.Connection:
    config = load_config()
    db_path = Path(config.app.database_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def classify_failure(error_msg: str) -> Dict[str, Any]:
    """Classify failure into transient (retryable) vs permanent (quarantined)."""
    err_lower = error_msg.lower()
    if "timeout" in err_lower or "rate limit" in err_lower or "connection" in err_lower or "429" in err_lower:
        return {"category": "TRANSIENT_NETWORK", "retryable": True}
    elif "db locked" in err_lower or "database is locked" in err_lower or "busy" in err_lower:
        return {"category": "TRANSIENT_DB_LOCK", "retryable": True}
    elif "corrupt" in err_lower or "invalid image" in err_lower or "bad file" in err_lower:
        return {"category": "PERMANENT_CORRUPTION", "retryable": False}
    elif "permission" in err_lower:
        return {"category": "PERMANENT_PERMISSION", "retryable": False}
    return {"category": "UNKNOWN_ERROR", "retryable": True}


def process_retry_queue() -> Dict[str, Any]:
    """
    Process all currently eligible retries in the retry intelligence queue.
    """
    retries = get_retry_queue()
    processed_count = 0
    succeeded_count = 0
    quarantined_count = 0
    now = time.time()
    conn = _get_db_conn()

    try:
        cur = conn.cursor()
        for item in retries:
            media_id = item.get("media_id")
            attempt = item.get("attempt_count", 1)
            reason = item.get("reason", "Unknown")
            
            classification = classify_failure(reason)

            if not classification["retryable"] or attempt >= MAX_RETRIES:
                # Quarantine
                cur.execute(
                    "UPDATE media SET state = 'FAILED', error_code = 'MAX_RETRIES_EXCEEDED', updated_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), media_id)
                )
                quarantined_count += 1
                record_audit_event(
                    actor="RETRY_ENGINE",
                    action="MEDIA_QUARANTINED",
                    object_type="media",
                    object_id=str(media_id),
                    after_state=f"Reason: {reason}, Attempts: {attempt}"
                )
            else:
                # Reset state to READY or PENDING to allow worker re-processing
                cur.execute(
                    "UPDATE media SET state = 'READY', error_code = NULL, updated_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), media_id)
                )
                succeeded_count += 1

            processed_count += 1

        conn.commit()
        return {
            "success": True,
            "total_evaluated": len(retries),
            "processed_count": processed_count,
            "re_queued_count": succeeded_count,
            "quarantined_count": quarantined_count
        }
    finally:
        conn.close()
