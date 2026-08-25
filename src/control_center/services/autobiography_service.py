"""Memory Autobiography Generator Service for Phase 6.5J.

Synthesizes annual structured life stories ("My 2026", "My 2025") organizing photos and memories
into chronological narrative chapters with titles, key milestones, and monthly highlights.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

class AutobiographyService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def generate_annual_autobiography(self, year: str = "2026") -> Dict[str, Any]:
        """Synthesize a complete chronological yearly autobiography story."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, original_filename, date_taken, location_label, labels_json, people_json
                FROM media
                WHERE date_taken LIKE ?
                ORDER BY date_taken ASC
                """,
                (f"{year}%",),
            ).fetchall()

        monthly_buckets: Dict[int, List[Dict[str, Any]]] = {i: [] for i in range(1, 13)}
        locations_set = set()
        people_set = set()

        for r in rows:
            dt = r["date_taken"] or ""
            try:
                m_int = int(dt.split("-")[1])
                monthly_buckets[m_int].append(dict(r))
            except Exception:
                monthly_buckets[8].append(dict(r))

            if r["location_label"]:
                locations_set.add(r["location_label"])
            if r["people_json"]:
                for p in r["people_json"].replace("[", "").replace("]", "").replace('"', '').split(","):
                    if p.strip():
                        people_set.add(p.strip())

        chapters = []
        for m_idx in range(1, 13):
            items = monthly_buckets[m_idx]
            m_name = MONTH_NAMES[m_idx - 1]
            if items:
                loc_list = list({it["location_label"] for it in items if it.get("location_label")})
                loc_str = f" in {', '.join(loc_list[:2])}" if loc_list else ""
                
                if m_idx in [6, 7, 8]:
                    theme = "Summer Travels & Family Gatherings"
                elif m_idx in [1, 2]:
                    theme = "New Beginnings & Winter Focus"
                elif m_idx in [3, 4, 5]:
                    theme = "Spring Explorations & Outdoor Activities"
                else:
                    theme = "Autumn Projects & Celebrations"

                chapters.append({
                    "month_number": m_idx,
                    "month_name": m_name,
                    "chapter_title": f"{m_name}: {theme}",
                    "narrative": f"During {m_name} {year}, you captured {len(items)} memorable moments{loc_str}. Notable highlights include engaging outdoor trips, quality family milestones, and personal projects.",
                    "photo_count": len(items),
                    "sample_photos": [it["original_filename"] for it in items[:4]],
                })

        summary_narrative = (
            f"The year {year} was filled with vibrant experiences across {len(locations_set)} locations "
            f"and memorable gatherings with {len(people_set)} people. Across {len(rows)} preserved photos and videos, "
            f"it represents a major chapter of discovery, travel, and personal growth."
        )

        logger.info("Generated autobiography for year %s (%d chapters, %d photos)", year, len(chapters), len(rows))

        return {
            "year": year,
            "book_title": f"My {year}: A Year in Moments",
            "executive_summary": summary_narrative,
            "total_photos_in_year": len(rows),
            "total_locations_visited": len(locations_set),
            "key_people": list(people_set),
            "chapters": chapters,
        }
