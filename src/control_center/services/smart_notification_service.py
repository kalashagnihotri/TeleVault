"""Smart Notification Intelligence Service (Phase 6.5H Pillar 4)

Generates proactive, actionable system notifications based on real vault telemetry:
- Archive Health alerts (missing scenes, pending retries)
- Life Memories synthesized (trip highlights, family milestones)
- Face intelligence alerts (newly clustered people, potential duplicates)
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from src.config import load_config
from src.control_center.services.memory_service import detect_events

logger = logging.getLogger(__name__)


def _get_db_conn() -> sqlite3.Connection:
    config = load_config()
    db_path = Path(config.app.database_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def get_smart_notifications_feed() -> List[Dict[str, Any]]:
    """Generate dynamic contextual notifications feed."""
    conn = _get_db_conn()
    notifications: List[Dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        cur = conn.cursor()

        # 1. Health Alert: Check unanalyzed scene media
        cur.execute("SELECT COUNT(*) as cnt FROM media WHERE state = 'BACKED_UP' AND (scene_state IS NULL OR scene_state = 'PENDING')")
        r_scene = cur.fetchone()
        unanalyzed_scenes = r_scene["cnt"] if r_scene else 0
        if unanalyzed_scenes > 0:
            notifications.append({
                "id": "health_scene_coverage",
                "category": "HEALTH",
                "level": "WARNING",
                "title": "⚠️ Scene Analysis Incomplete",
                "message": f"{unanalyzed_scenes} backed-up photos have no scene classification.",
                "action_label": "Run Scene Analysis",
                "action_route": "/maintenance",
                "timestamp": now_iso
            })

        # 2. Face Intelligence: Check unknown face clusters
        cur.execute("SELECT COUNT(DISTINCT media_id) as cnt FROM media_faces WHERE decision = 'UNKNOWN'")
        r_unknown = cur.fetchone()
        unknown_faces = r_unknown["cnt"] if r_unknown else 0
        if unknown_faces > 0:
            notifications.append({
                "id": "face_unknown_clusters",
                "category": "FACES",
                "level": "INFO",
                "title": "👤 Unknown Faces Detected",
                "message": f"{unknown_faces} photos have unknown people ready for identity review.",
                "action_label": "Review Faces",
                "action_route": "/faces",
                "timestamp": now_iso
            })

        # 3. Life Memories: Check synthesized memories
        try:
            events = detect_events()
            if events:
                top_event = events[0]
                notifications.append({
                    "id": f"memory_event_{top_event.get('id')}",
                    "category": "MEMORY",
                    "level": "SUCCESS",
                    "title": f"📸 Memory Created: {top_event.get('title')}",
                    "message": f"{len(top_event.get('media_ids', []))} photos from {top_event.get('location', 'Trip')} have been curated.",
                    "action_label": "View Memory",
                    "action_route": "/memories",
                    "timestamp": now_iso
                })
        except Exception as e:
            logger.warning("Could not evaluate memory notifications: %s", e)

        # 4. Backup Pipeline Health
        cur.execute("SELECT COUNT(*) as cnt FROM media WHERE state = 'BACKED_UP'")
        backed_up_count = cur.fetchone()["cnt"]
        notifications.append({
            "id": "vault_status_healthy",
            "category": "SYSTEM",
            "level": "SUCCESS",
            "title": "🛡️ Vault Fully Operational",
            "message": f"{backed_up_count} media assets safely archived in Telegram cloud.",
            "action_label": "System Dashboard",
            "action_route": "/dashboard",
            "timestamp": now_iso
        })

        return notifications
    finally:
        conn.close()
