"""Timeline Stream Service (Phase 6.5H Pillar 8)

Serves high-performance, grouped chronological streams (Google Photos style):
- Year -> Month -> Day sections with sticky date markers
- Optimized pagination for infinite scroll
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from src.config import load_config

logger = logging.getLogger(__name__)


def _get_db_conn() -> sqlite3.Connection:
    config = load_config()
    db_path = Path(config.app.database_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def get_timeline_stream(page: int = 1, page_size: int = 50) -> Dict[str, Any]:
    """Retrieve chronological media stream formatted into year/month/day sections."""
    conn = _get_db_conn()
    offset = max(0, (page - 1) * page_size)

    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as total FROM media WHERE state = 'BACKED_UP'")
        total_count = cur.fetchone()["total"]

        cur.execute(
            """
            SELECT id, sha256, original_filename, media_type, size_bytes, date_taken, location_label, labels_json, people_json
            FROM media
            WHERE state = 'BACKED_UP'
            ORDER BY COALESCE(date_taken, discovered_at) DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (page_size, offset)
        )
        rows = cur.fetchall()

        sections: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            dt = r["date_taken"] or "Undated"
            year = dt[:4] if len(dt) >= 4 and dt[:4].isdigit() else "Undated"
            month = dt[:7] if len(dt) >= 7 else year

            sec_key = f"{year}-{month}"
            if sec_key not in sections:
                sections[sec_key] = {
                    "year": year,
                    "month": month,
                    "items_count": 0,
                    "items": []
                }

            sections[sec_key]["items_count"] += 1
            sections[sec_key]["items"].append({
                "id": r["id"],
                "filename": r["original_filename"],
                "media_type": r["media_type"],
                "size_bytes": r["size_bytes"],
                "date_taken": r["date_taken"],
                "location": r["location_label"],
                "labels": json.loads(r["labels_json"] or "[]"),
                "people": json.loads(r["people_json"] or "[]")
            })

        return {
            "page": page,
            "page_size": page_size,
            "total_items": total_count,
            "has_more": (offset + len(rows)) < total_count,
            "sections": list(sections.values())
        }
    finally:
        conn.close()
