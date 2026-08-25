"""Place & Reverse Geocoding Engine for TeleVault.

Resolves geographic coordinates (Latitude, Longitude) to human-readable locations:
1. Checks local custom overrides in `config/places.json` (Priority 1: "Home", "Office", "Cabin").
2. Queries Reverse Geocoding API (Priority 2):
   - OpenStreetMap / Nominatim (Free, no API key needed, global coverage)
   - Google Maps Geocoding API (Optional: if GOOGLE_MAPS_API_KEY is configured in .env)
3. Caches all results locally in `cache/places_cache.json` (rounded to 3 decimal places ~100m)
   to ensure zero duplicate API requests and lightning-fast offline operation.
4. Fail-safe: Never blocks or crashes if network is unavailable; falls back gracefully.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
import httpx

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
        enable_online_api: bool = True
    ) -> None:
        self.config_path = config_path
        self.cache_path = cache_path
        self.enable_online_api = enable_online_api
        self.places: List[PlaceConfig] = []
        self._cache: Dict[str, str] = {}

        # 1. Load custom local overrides (Home, Office, etc.)
        self._load_local_places()

        # 2. Load persistent disk cache
        self._load_cache()

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

    def _load_cache(self) -> None:
        if self.cache_path.is_file():
            try:
                with self.cache_path.open("r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            except Exception:
                self._cache = {}

    def _save_cache(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self.cache_path.open("w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            logger.warning("Could not save places cache: %s", e)

    def _get_cache_key(self, lat: float, lon: float) -> str:
        # Round to 3 decimal places (~110m precision) to maximize cache hits
        return f"{round(lat, 3)},{round(lon, 3)}"

    def resolve(self, lat: float | None, lon: float | None) -> str:
        """Resolve latitude and longitude to a human-friendly place name."""
        if lat is None or lon is None:
            return "Misc"

        # Step 1: Check user's custom places first (Highest Priority)
        for place in self.places:
            if place.contains(lat, lon):
                return place.label

        # Step 2: Check persistent local cache
        cache_key = self._get_cache_key(lat, lon)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Step 3: Query Online Reverse Geocoding API if enabled
        if self.enable_online_api:
            resolved_name = self._fetch_online_place_name(lat, lon)
            if resolved_name:
                self._cache[cache_key] = resolved_name
                self._save_cache()
                return resolved_name

        return "Unknown GPS Location"

    def _fetch_online_place_name(self, lat: float, lon: float) -> Optional[str]:
        """Fetch place name using Google Maps API (if key provided) or OpenStreetMap Nominatim."""
        google_api_key = os.getenv("GOOGLE_MAPS_API_KEY")

        # Option A: Google Maps Geocoding API (if user configured an API key)
        if google_api_key:
            try:
                url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lon}&key={google_api_key}"
                with httpx.Client(timeout=3.0) as client:
                    resp = client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        results = data.get("results", [])
                        if results:
                            # Extract formatted address or components
                            return results[0].get("formatted_address")
            except Exception as e:
                logger.warning("Google Maps Geocoding query failed: %s", e)

        # Option B: OpenStreetMap / Nominatim (Free, no API key required)
        try:
            url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&zoom=12"
            headers = {"User-Agent": "TeleVault/1.0 (media-archive-personal-ai)"}
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    addr = data.get("address", {})

                    # Construct clean hierarchy: City/Town/Village -> State -> Country
                    city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county") or addr.get("municipality") or addr.get("hamlet")
                    state = addr.get("state") or addr.get("state_district") or addr.get("region")
                    country = addr.get("country")

                    parts = [p for p in [city, state, country] if p]
                    if parts:
                        return ", ".join(parts)
                    elif "display_name" in data:
                        # Fallback to display name truncated to 3 parts
                        d_parts = [p.strip() for p in data["display_name"].split(",") if p.strip()]
                        return ", ".join(d_parts[:3])
        except Exception as e:
            logger.warning("OpenStreetMap reverse geocoding query failed: %s", e)

        return None
