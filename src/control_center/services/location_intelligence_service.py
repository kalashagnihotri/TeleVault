"""Location Intelligence and Places Visited Hierarchy Service for Phase 6.5J.

Performs structured reverse geocoding (GPS -> City -> State -> Country) and aggregates
historical places visited frequency statistics across life memories.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

class LocationIntelligenceService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def get_places_visited_hierarchy(self) -> Dict[str, Any]:
        """Aggregate cities and countries visited with visit counts and photo volumes."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT location_label, COUNT(*) as photo_count, MIN(date_taken) as first_seen, MAX(date_taken) as last_seen
                FROM media
                WHERE location_label IS NOT NULL AND location_label != ''
                GROUP BY location_label
                ORDER BY photo_count DESC
                """
            ).fetchall()

        cities_ranking = []
        for r in rows:
            loc = r["location_label"]
            # Structure city / state / country
            parts = [p.strip() for p in loc.split(",") if p.strip()]
            city = parts[0] if parts else loc
            country = parts[-1] if len(parts) > 1 else "United States"

            cities_ranking.append({
                "raw_label": loc,
                "city": city,
                "country": country,
                "photo_count": r["photo_count"],
                "first_visit": r["first_seen"],
                "last_visit": r["last_seen"],
                "estimated_trips_count": max(1, r["photo_count"] // 5),
            })

        total_locations = len(cities_ranking)
        logger.info("Computed location intelligence hierarchy across %d unique places", total_locations)

        return {
            "total_places_visited": total_locations,
            "top_visited_cities": cities_ranking[:10],
            "all_destinations": cities_ranking,
        }
