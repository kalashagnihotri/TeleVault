"""Place & Reverse Geocoding Engine for TeleVault.

Resolves geographic coordinates (Latitude, Longitude) to human-readable locations:
1. Checks local custom overrides in `config/places.json` (Priority 1: "Home", "Office", "Cabin").
2. Queries LocationService (Priority 2: Aliases -> SQLite Cache -> Nominatim -> GeoNames).
3. Fail-safe: Never blocks or crashes if network is unavailable; falls back gracefully.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

@dataclass
class PlaceConfig:
    label: str
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    def contains(self, lat: float, lon: float) -> bool:
        return (self.min_lat <= lat <= self.max_lat) and (self.min_lon <= lon <= self.max_lon)

class PlaceResolver:
    def __init__(
        self, 
        config_path: Path = Path("config/places.json"),
        cache_path: Path = Path("cache/places_cache.json"),
        enable_online_api: bool = True,
        db_path: Path = Path("data/archive.sqlite3"),
    ) -> None:
        self.config_path = config_path
        self.cache_path = cache_path
        self.enable_online_api = enable_online_api
        self.db_path = db_path
        self.places: List[PlaceConfig] = []

        # Load custom local overrides
        self._load_local_places()

        # Instantiate unified LocationService
        try:
            from src.control_center.services.location_service import LocationService
            self.location_service = LocationService(
                db_path=self.db_path,
                cache_results=True,
                enabled=self.enable_online_api,
            )
        except Exception as e:
            logger.warning("Could not initialize LocationService in PlaceResolver: %s", e)
            self.location_service = None

    def _load_local_places(self) -> None:
        if self.config_path.is_file():
            try:
                with self.config_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        self.places.append(
                            PlaceConfig(
                                label=item["label"],
                                min_lat=float(item["min_lat"]),
                                max_lat=float(item["max_lat"]),
                                min_lon=float(item["min_lon"]),
                                max_lon=float(item["max_lon"]),
                            )
                        )
                logger.info("Loaded %d custom offline places from %s", len(self.places), self.config_path)
            except Exception as e:
                logger.error("Failed to load places config from %r: %s", str(self.config_path), e)

    def resolve(self, lat: float | None, lon: float | None) -> str:
        """Resolve latitude and longitude to a human-friendly place name."""
        if lat is None or lon is None:
            return "Misc"

        # Step 1: Check user's custom places first (Highest Priority)
        for place in self.places:
            if place.contains(lat, lon):
                return place.label

        # Step 2: Use unified LocationService
        if self.location_service is not None:
            res = self.location_service.resolve_location(lat, lon)
            if res.place_name and res.place_name != "UNKNOWN_LOCATION":
                return res.place_name

        return "Unknown GPS Location"
