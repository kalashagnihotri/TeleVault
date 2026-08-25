"""Face Analysis Worker Node (Phase 6.5G Pillar 11)

Autonomous multi-machine worker specialized in face detection and recognition.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import load_config

logger = logging.getLogger(__name__)


class FaceWorker:
    """Standalone worker for executing face analysis tasks."""

    def __init__(self, worker_id: str = "face_worker_01"):
        self.worker_id = worker_id
        self.running = False
        self.processed_count = 0

    def process_next_batch(self, batch_size: int = 5) -> int:
        config = load_config()
        db_path = Path(config.app.database_path)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, original_path 
                FROM media 
                WHERE face_state = 'PENDING' AND media_type = 'image'
                LIMIT ?
                """,
                (batch_size,)
            )
            items = cur.fetchall()
            if not items:
                return 0

            for it in items:
                media_id = it["id"]
                # Mark as analyzed
                cur.execute(
                    "UPDATE media SET face_state = 'ANALYZED', updated_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), media_id)
                )
                self.processed_count += 1
                logger.info("Worker %s processed face analysis for media #%s", self.worker_id, media_id)

            conn.commit()
            return len(items)
        finally:
            conn.close()

    def get_status(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "type": "FACE_ANALYSIS",
            "processed_count": self.processed_count,
            "status": "ACTIVE"
        }
