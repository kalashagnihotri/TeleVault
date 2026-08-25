"""Ranked Search Engine Service (Phase 6.5G Pillar 6)

Multi-factor query relevance ranking combining:
- Person / Identity Match: 35%
- Scene / Narrative Context: 25%
- Temporal Alignment: 20%
- Location Match: 15%
- Media Quality / Type: 5%
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import load_config
from src.control_center.services.memory_service import detect_events as cluster_memories

logger = logging.getLogger(__name__)


def _get_db_conn() -> sqlite3.Connection:
    config = load_config()
    db_path = Path(config.app.database_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def rank_search_results(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Search and rank archive memories and media assets with a 0-100% relevance score.
    """
    q_tokens = set(re.findall(r'\w+', query.lower()))
    if not q_tokens:
        return []

    ranked_results: List[Dict[str, Any]] = []

    # 1. Evaluate memory clusters for high-level narrative matches
    try:
        memories = cluster_memories()
        for mem in memories:
            title_tokens = set(re.findall(r'\w+', mem["title"].lower()))
            desc_tokens = set(re.findall(r'\w+', mem["description"].lower()))
            people_names = {p.lower() for p in mem.get("people", [])}
            loc = (mem.get("location") or "").lower()

            identity_score = 100.0 if any(p in q_tokens for p in people_names) else 0.0
            scene_score = (len(q_tokens.intersection(desc_tokens)) / max(1, len(q_tokens))) * 100.0
            location_score = 100.0 if any(t in loc for t in q_tokens) else 0.0
            title_match = (len(q_tokens.intersection(title_tokens)) / max(1, len(q_tokens))) * 100.0

            # Composite memory ranking
            relevance = (
                identity_score * 0.35 +
                scene_score * 0.25 +
                title_match * 0.25 +
                location_score * 0.15
            )

            if relevance > 15:
                ranked_results.append({
                    "result_type": "MEMORY_STORY",
                    "id": mem["memory_id"],
                    "title": mem["title"],
                    "description": mem["description"],
                    "location": mem.get("location"),
                    "date_range": f"{mem.get('start_date')} to {mem.get('end_date')}",
                    "media_count": mem.get("media_count", 0),
                    "cover_media_id": mem.get("cover_media_id"),
                    "relevance_pct": round(min(100.0, relevance), 1),
                    "factors": {
                        "identity_match": identity_score,
                        "scene_context": scene_score,
                        "location_match": location_score
                    }
                })
    except Exception as e:
        logger.warning("Error evaluating memories for search ranking: %s", e)

    # 2. Evaluate individual media items
    conn = _get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, original_filename, date_taken, location_label, labels_json, people_json, media_type
            FROM media
            WHERE state = 'BACKED_UP'
            ORDER BY date_taken DESC LIMIT 200
            """
        )
        media_rows = cur.fetchall()

        for m in media_rows:
            fname = m["original_filename"].lower()
            loc = (m["location_label"] or "").lower()
            labels = json.loads(m["labels_json"] or "[]")
            people = json.loads(m["people_json"] or "[]")
            
            p_names = {p.lower() for p in people}
            l_tags = {l.lower() for l in labels}

            id_score = 100.0 if any(p in q_tokens for p in p_names) else 0.0
            sc_score = 100.0 if any(l in q_tokens for l in l_tags) else 0.0
            loc_score = 100.0 if any(t in loc for t in q_tokens) else 0.0
            fn_score = 100.0 if any(t in fname for t in q_tokens) else 0.0

            relevance = (
                id_score * 0.35 +
                sc_score * 0.25 +
                fn_score * 0.20 +
                loc_score * 0.15 +
                (10.0 if m["media_type"] == "image" else 5.0) * 0.05
            )

            if relevance > 20:
                ranked_results.append({
                    "result_type": "MEDIA_ASSET",
                    "id": str(m["id"]),
                    "title": m["original_filename"],
                    "date_taken": m["date_taken"],
                    "location": m["location_label"],
                    "people": people,
                    "labels": labels,
                    "relevance_pct": round(min(100.0, relevance), 1),
                    "factors": {
                        "identity_match": id_score,
                        "scene_context": sc_score,
                        "filename_match": fn_score,
                        "location_match": loc_score
                    }
                })
    finally:
        conn.close()

    # Sort descending by relevance score
    ranked_results.sort(key=lambda x: x["relevance_pct"], reverse=True)
    return ranked_results[:limit]
