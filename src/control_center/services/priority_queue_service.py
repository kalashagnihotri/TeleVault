"""Priority Worker Queue System for Phase 6.5I.

Provides persistent 3-tier SQLite job queuing (Priority 1: Failed retries, Priority 2: New uploads, Priority 3: Reprocessing).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class PriorityQueueService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def enqueue_job(
        self,
        media_id: int,
        task_type: str,
        priority: int = 2,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Enqueue a new job with priority (1=Highest/Retry, 2=Normal/Upload, 3=Background/Reprocess)."""
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        payload_str = json.dumps(payload or {}, ensure_ascii=False)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO job_priority_queue 
                (job_id, media_id, task_type, priority, payload_json, status, attempts, created_at)
                VALUES (?, ?, ?, ?, ?, 'QUEUED', 0, ?)
                """,
                (job_id, media_id, task_type.upper(), priority, payload_str, now_iso),
            )
        logger.info("Enqueued priority job %s (type=%s, prio=%d, media=%d)", job_id, task_type, priority, media_id)
        return job_id

    def fetch_next_job(self) -> Optional[Dict[str, Any]]:
        """Fetch highest priority queued job atomically (order by priority ASC, created_at ASC)."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT job_id, media_id, task_type, priority, payload_json, attempts, created_at
                FROM job_priority_queue
                WHERE status = 'QUEUED'
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
                """
            ).fetchone()

            if not row:
                return None

            conn.execute(
                """
                UPDATE job_priority_queue 
                SET status = 'RUNNING', started_at = ?, attempts = attempts + 1 
                WHERE job_id = ?
                """,
                (now_iso, row["job_id"]),
            )

        payload_dict = {}
        try:
            payload_dict = json.loads(row["payload_json"])
        except Exception:
            pass

        return {
            "job_id": row["job_id"],
            "media_id": row["media_id"],
            "task_type": row["task_type"],
            "priority": row["priority"],
            "payload": payload_dict,
            "attempts": row["attempts"] + 1,
            "created_at": row["created_at"],
        }

    def complete_job(self, job_id: str, success: bool = True, error_msg: Optional[str] = None) -> None:
        """Mark job finished as COMPLETED or FAILED."""
        now_iso = datetime.now(timezone.utc).isoformat()
        status = "COMPLETED" if success else "FAILED"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE job_priority_queue 
                SET status = ?, finished_at = ?, error_message = ? 
                WHERE job_id = ?
                """,
                (status, now_iso, error_msg, job_id),
            )
        logger.info("Job %s finished with status %s", job_id, status)

    def get_queue_stats(self) -> Dict[str, Any]:
        """Return queue backlog summary by priority and status."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT status, priority, COUNT(*) as count 
                FROM job_priority_queue 
                GROUP BY status, priority
                """
            ).fetchall()

            recent = conn.execute(
                """
                SELECT job_id, media_id, task_type, priority, status, attempts, created_at, started_at, finished_at, error_message
                FROM job_priority_queue
                ORDER BY created_at DESC
                LIMIT 20
                """
            ).fetchall()

        summary = {"queued": 0, "running": 0, "completed": 0, "failed": 0, "priority_1": 0, "priority_2": 0, "priority_3": 0}
        for r in rows:
            st = r["status"].lower()
            if st in summary:
                summary[st] += r["count"]
            pr = f"priority_{r['priority']}"
            if pr in summary:
                summary[pr] += r["count"]

        return {
            "summary": summary,
            "recent_jobs": [dict(r) for r in recent],
        }
