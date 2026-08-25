"""Personal Preference & Behavioral Affinity Learning Service (Phase 6.5G Pillar 7)

Learns user habits, interaction frequencies, and favorite categories
(Trips, People, Documents, Videos) to provide tailored dashboard recommendations.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import load_config

logger = logging.getLogger(__name__)

DEFAULT_CATEGORIES = {
    "trips": "🏔 Trips & Travel",
    "people": "👥 Family & People",
    "documents": "📄 Documents & Receipts",
    "videos": "🎬 Video Vault",
    "nature": "🌿 Nature & Outdoors"
}


def _get_db_conn() -> sqlite3.Connection:
    config = load_config()
    db_path = Path(config.app.database_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def record_interaction(category: str, increment: float = 1.0) -> None:
    """Record a user interaction with a specific media category or story."""
    conn = _get_db_conn()
    now_iso = datetime.now(timezone.utc).isoformat()
    cat_key = category.lower().strip()
    try:
        cur = conn.cursor()
        cur.execute("SELECT affinity_score, interaction_count FROM user_preferences WHERE preference_key = ?", (cat_key,))
        row = cur.fetchone()
        if row:
            new_score = row["affinity_score"] + increment
            new_count = row["interaction_count"] + 1
            cur.execute(
                "UPDATE user_preferences SET affinity_score = ?, interaction_count = ?, last_interacted_at = ? WHERE preference_key = ?",
                (new_score, new_count, now_iso, cat_key)
            )
        else:
            cur.execute(
                "INSERT INTO user_preferences (preference_key, category, affinity_score, interaction_count, last_interacted_at) VALUES (?, ?, ?, 1, ?)",
                (cat_key, cat_key.capitalize(), increment, now_iso)
            )
        conn.commit()
    finally:
        conn.close()


def get_user_preferences_profile() -> Dict[str, Any]:
    """Retrieve affinity scores and top favorite category rankings."""
    conn = _get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT preference_key, category, affinity_score, interaction_count, last_interacted_at FROM user_preferences ORDER BY affinity_score DESC")
        rows = cur.fetchall()

        if not rows:
            # Seed default profile if empty
            favorites = [
                {"category": "Trips", "label": "🏔 Trips & Travel", "affinity_score": 10.0},
                {"category": "People", "label": "👥 Family & People", "affinity_score": 8.5},
                {"category": "Documents", "label": "📄 Documents & Receipts", "affinity_score": 6.0}
            ]
        else:
            favorites = []
            for r in rows:
                key = r["preference_key"]
                label = DEFAULT_CATEGORIES.get(key, r["category"])
                favorites.append({
                    "category": r["category"],
                    "label": label,
                    "affinity_score": r["affinity_score"],
                    "interaction_count": r["interaction_count"],
                    "last_interacted_at": r["last_interacted_at"]
                })

        return {
            "top_favorites": favorites[:3],
            "all_preferences": favorites
        }
    finally:
        conn.close()
