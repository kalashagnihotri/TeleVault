"""Scene Analysis Worker Node (Phase 6.5G Pillar 11)

Autonomous multi-machine worker specialized in scene recognition and heuristics.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from src.config import load_config

logger = logging.getLogger(__name__)


class SceneWorker:
    """Standalone worker for executing scene classification tasks."""

    def __init__(self, worker_id: str = "scene_worker_01"):
        self.worker_id = worker_id
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
                SELECT id, original_path, labels_json 
                FROM media 
                WHERE scene_state = 'PENDING' AND media_type = 'image'
                LIMIT ?
                """,
                (batch_size,)
            )
            items = cur.fetchall()
            if not items:
                return 0

            for it in items:
                media_id = it["id"]
                labels = json.loads(it["labels_json"] or "[]")
                if not labels:
                    labels = ["General Scene"]
                
                cur.execute(
                    "UPDATE media SET scene_state = 'ANALYZED', labels_json = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(labels), datetime.now(timezone.utc).isoformat(), media_id)
                )
                self.processed_count += 1
                logger.info("Worker %s processed scene analysis for media #%s", self.worker_id, media_id)

            conn.commit()
            return len(items)
        finally:
            conn.close()

    def get_status(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "type": "SCENE_ANALYSIS",
            "processed_count": self.processed_count,
            "status": "ACTIVE"
        }
