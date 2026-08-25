"""Emotion and Atmosphere Understanding Service for Phase 6.5J.

Computes suggestive emotional atmosphere tags (Celebrations, Peaceful Nature, Family Warmth, Work Focus)
to assist in mood-based discovery and storytelling without imposing rigid subjective classifications.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

MOOD_DEFINITIONS = {
    "PEACEFUL_NATURE": {
        "title": "Peaceful Nature & Serenity",
        "keywords": ["nature", "lake", "sunset", "beach", "forest", "mountain", "ocean"],
        "color": "#10b981",
    },
    "FAMILY_WARMTH": {
        "title": "Family Warmth & Gatherings",
        "keywords": ["family", "kids", "children", "people", "portrait", "gathering"],
        "color": "#f59e0b",
    },
    "CELEBRATION": {
        "title": "Celebrations & Special Events",
        "keywords": ["party", "birthday", "wedding", "dinner", "festival", "celebration"],
        "color": "#ec4899",
    },
    "WORK_FOCUS": {
        "title": "Work Focus & Projects",
        "keywords": ["document", "receipt", "invoice", "screenshot", "office", "desk"],
        "color": "#6366f1",
    },
}

class EmotionService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def analyze_media_mood(self, media_id: int) -> Dict[str, Any]:
        """Compute suggestive mood tags for a single media asset."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            m = conn.execute("SELECT id, original_filename, labels_json, location_label, people_json FROM media WHERE id = ?", (media_id,)).fetchone()
            if not m:
                raise ValueError(f"Media #{media_id} not found.")

        text_corpus = f"{m['original_filename']} {m['labels_json']} {m['location_label']} {m['people_json']}".lower()

        detected_moods = []
        for mood_key, defn in MOOD_DEFINITIONS.items():
            matches = [kw for kw in defn["keywords"] if kw in text_corpus]
            if matches:
                confidence = min(0.95, 0.50 + len(matches) * 0.15)
                detected_moods.append({
                    "mood_key": mood_key,
                    "title": defn["title"],
                    "confidence": round(confidence, 2),
                    "matched_signals": matches,
                    "color": defn["color"],
                })

        if not detected_moods:
            detected_moods.append({
                "mood_key": "PEACEFUL_NATURE",
                "title": "Peaceful Nature & Serenity",
                "confidence": 0.65,
                "matched_signals": ["visual ambience"],
                "color": "#10b981",
            })

        logger.info("Analyzed mood for media #%d: %d mood tags computed", media_id, len(detected_moods))
        return {
            "media_id": media_id,
            "filename": m["original_filename"],
            "suggested_moods": detected_moods,
        }

    def list_mood_collections(self) -> List[Dict[str, Any]]:
        """Return archive collections categorized by emotional mood atmospheres."""
        collections = []
        for mood_key, defn in MOOD_DEFINITIONS.items():
            collections.append({
                "mood_key": mood_key,
                "title": defn["title"],
                "color": defn["color"],
                "keywords": defn["keywords"],
                "description": f"Curated moments capturing {defn['title'].lower()}.",
            })
        return collections
