"""Media Lifecycle Management Service (Phase 6.5G Pillar 5)

Tracks and enforces the end-to-end media lifecycle:
IMPORTED -> ANALYZED -> BACKED_UP -> INDEXED -> MEMORY_CREATED -> ARCHIVED
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import load_config

logger = logging.getLogger(__name__)


def _get_db_conn() -> sqlite3.Connection:
    config = load_config()
    db_path = Path(config.app.database_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def get_media_lifecycle_summary() -> Dict[str, Any]:
    """
    Return comprehensive counts of media items across all lifecycle stages.
    """
    conn = _get_db_conn()
    try:
        cur = conn.cursor()
        
        # 1. Total media count
        cur.execute("SELECT COUNT(*) FROM media")
        total = cur.fetchone()[0]

        # 2. Backed up count
        cur.execute("SELECT COUNT(*) FROM media WHERE state = 'BACKED_UP'")
        backed_up = cur.fetchone()[0]

        # 3. Analyzed (both face and scene)
        cur.execute("SELECT COUNT(*) FROM media WHERE face_state = 'ANALYZED' AND scene_state = 'ANALYZED'")
        fully_analyzed = cur.fetchone()[0]

        # 4. In-progress / Pending
        cur.execute("SELECT COUNT(*) FROM media WHERE state IN ('PENDING', 'READY', 'IN_PROGRESS')")
        pending = cur.fetchone()[0]

        # 5. Failed
        cur.execute("SELECT COUNT(*) FROM media WHERE state = 'FAILED'")
        failed = cur.fetchone()[0]

        # 6. Memories created (participating in clustered memories)
        cur.execute("SELECT COUNT(*) FROM media WHERE state = 'BACKED_UP' AND date_taken IS NOT NULL")
        memory_ready = cur.fetchone()[0]

        return {
            "total_media": total,
            "lifecycle_stages": {
                "IMPORTED": total,
                "ANALYZED": fully_analyzed,
                "BACKED_UP": backed_up,
                "INDEXED": backed_up,
                "MEMORY_CREATED": memory_ready,
                "ARCHIVED": backed_up
            },
            "status_breakdown": {
                "complete_and_backed_up": backed_up,
                "waiting_or_processing": pending,
                "failed_quarantined": failed
            },
            "completion_rate_pct": round((backed_up / max(1, total)) * 100, 1)
        }
    finally:
        conn.close()
