"""Location Intelligence Service for Phase 6.5I.

Production-grade, local-first location service that reverse-geocodes EXIF GPS
coordinates to structured location records using:
1. User Location Aliases (Learning corrections)
2. Local SQLite Location Cache
3. Local/Remote OpenStreetMap Nominatim Provider
4. GeoNames Offline City Gazetteer Fallback
5. Raw GPS Fallback
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

from src.control_center.services.geonames_service import GeoNamesService, haversine_km

logger = logging.getLogger(__name__)

@dataclass
class LocationResult:
    country: str
    state: str
    city: str
    place_name: str
    source: str  # "user_alias", "cache", "openstreetmap", "geonames", "raw_gps"
    confidence: int  # 0 to 100
    latitude: float
    longitude: float
    osm_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class LocationService:
    def __init__(
        self,
        db_path: Path = Path("data/archive.sqlite3"),
        geonames_dir: Path = Path("data/geonames"),
        nominatim_url: str = "https://nominatim.openstreetmap.org",
        cache_results: bool = True,
        enabled: bool = True,
    ) -> None:
        self.db_path = db_path
        self.nominatim_url = nominatim_url.rstrip("/")
        self.cache_results = cache_results
        self.enabled = enabled
        self.geonames = GeoNamesService(geonames_dir=geonames_dir)

    def resolve_location(self, latitude: Optional[float], longitude: Optional[float]) -> LocationResult:
        """Resolve latitude and longitude to a rich LocationResult according to 5-tier priority."""
        if latitude is None or longitude is None:
            return LocationResult(
                country="",
                state="",
                city="",
                place_name="UNKNOWN_LOCATION",
                source="raw_gps",
                confidence=0,
                latitude=0.0,
                longitude=0.0,
            )

        now_iso = datetime.now(timezone.utc).isoformat()

        # Tier 1: User Location Aliases (Learning / Manual Correction)
        alias = self._check_user_alias(latitude, longitude)
        if alias:
            logger.info("Resolved (%.4f, %.4f) via user alias: '%s'", latitude, longitude, alias["custom_name"])
            return LocationResult(
                country="User Specified",
                state="",
                city=alias["custom_name"],
                place_name=alias["custom_name"],
                source="user_alias",
                confidence=100,
                latitude=latitude,
                longitude=longitude,
            )

        # Tier 2: Cached Location in SQLite
        cached = self._check_sqlite_cache(latitude, longitude)
        if cached:
            return LocationResult(
                country=cached["country"] or "",
                state=cached["state"] or "",
                city=cached["city"] or "",
                place_name=cached["place_name"] or "",
                source="cache",
                confidence=cached["confidence"] or 95,
                latitude=latitude,
                longitude=longitude,
                osm_id=cached.get("osm_id"),
            )

        # Tier 3: OpenStreetMap / Nominatim Reverse Lookup
        if self.enabled:
            osm_res = self._fetch_nominatim(latitude, longitude)
            if osm_res:
                if self.cache_results:
                    self._save_to_cache(latitude, longitude, osm_res)
                return osm_res

        # Tier 4: GeoNames Offline City Gazetteer Fallback
        geo_res = self.geonames.find_nearest_city(latitude, longitude)
        if geo_res:
            res = LocationResult(
                country=geo_res["country"],
                state=geo_res["state"],
                city=geo_res["city"],
                place_name=geo_res["place_name"],
                source="geonames",
                confidence=geo_res["confidence"],
                latitude=latitude,
                longitude=longitude,
            )
            if self.cache_results:
                self._save_to_cache(latitude, longitude, res)
            return res

        # Tier 5: Raw GPS coordinates fallback
        return LocationResult(
            country="",
            state="",
            city="",
            place_name=f"GPS ({latitude:.4f}, {longitude:.4f})",
            source="raw_gps",
            confidence=10,
            latitude=latitude,
            longitude=longitude,
        )

    def _check_user_alias(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Check if coordinates fall within the radius of any user-learned location alias."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT * FROM location_aliases").fetchall()
                for r in rows:
                    alias_lat = r["latitude"]
                    alias_lon = r["longitude"]
                    radius_km = float(r["radius"] or 0.05) * 111.0  # approximate deg to km if stored in deg
                    if haversine_km(lat, lon, alias_lat, alias_lon) <= max(radius_km, 2.0):
                        return dict(r)
        except Exception as e:
            logger.warning("Failed querying location_aliases: %s", e)
        return None

    def _check_sqlite_cache(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Check if nearby location already exists in SQLite locations cache (~100m window)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                # Box query for fast indexing
                margin = 0.0015  # ~150 meters
                row = conn.execute(
                    """
                    SELECT * FROM locations
                    WHERE latitude BETWEEN ? AND ?
                      AND longitude BETWEEN ? AND ?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (lat - margin, lat + margin, lon - margin, lon + margin),
                ).fetchone()
                if row:
                    return dict(row)
        except Exception as e:
            logger.warning("Failed querying locations cache: %s", e)
        return None

    def _save_to_cache(self, lat: float, lon: float, res: LocationResult) -> None:
        """Persist newly resolved location into SQLite locations table."""
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO locations 
                    (latitude, longitude, country, state, city, place_name, osm_id, source, confidence, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lat,
                        lon,
                        res.country,
                        res.state,
                        res.city,
                        res.place_name,
                        res.osm_id,
                        res.source,
                        res.confidence,
                        now_iso,
                    ),
                )
        except Exception as e:
            logger.warning("Failed writing to locations table: %s", e)

    def _fetch_nominatim(self, lat: float, lon: float) -> Optional[LocationResult]:
        """Query Nominatim endpoint with 3.0s timeout."""
        try:
            url = f"{self.nominatim_url}/reverse?lat={lat}&lon={lon}&format=json&zoom=14"
            headers = {"User-Agent": "TeleVault/1.0 (LocationIntelligence; OpenStreetMap)"}
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    addr = data.get("address", {})

                    country = addr.get("country", "")
                    state = addr.get("state") or addr.get("state_district") or addr.get("region", "")
                    city = (
                        addr.get("city")
                        or addr.get("town")
                        or addr.get("village")
                        or addr.get("county")
                        or addr.get("municipality")
                        or addr.get("hamlet", "")
                    )
                    
                    # Specific place name (e.g. National Park, Tourism, Landmark)
                    tourism = addr.get("tourism") or addr.get("leisure") or addr.get("natural") or addr.get("amenity")
                    if tourism and city:
                        place_name = f"{tourism}, {city}"
                    elif city and state:
                        place_name = f"{city}, {state}" if country in ("United States", "US") else f"{city}, {country}"
                    elif data.get("display_name"):
                        d_parts = [p.strip() for p in data["display_name"].split(",") if p.strip()]
                        place_name = ", ".join(d_parts[:2])
                    else:
                        place_name = city or state or country

                    osm_id = str(data.get("osm_id", ""))

                    return LocationResult(
                        country=country,
                        state=state,
                        city=city,
                        place_name=place_name,
                        source="openstreetmap",
                        confidence=98,
                        latitude=lat,
                        longitude=lon,
                        osm_id=osm_id,
                    )
        except Exception as e:
            logger.info("Nominatim lookup unavailable or timed out: %s", e)
        return None

    def add_user_alias(self, latitude: float, longitude: float, custom_name: str, radius: float = 0.05) -> Dict[str, Any]:
        """Learn and register a user location correction."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO location_aliases (latitude, longitude, radius, custom_name, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (latitude, longitude, radius, custom_name, now_iso),
            )
            alias_id = cur.lastrowid

            # Also update any media matching this alias
            margin = radius
            conn.execute(
                """
                UPDATE media
                SET location_label = ?
                WHERE latitude BETWEEN ? AND ?
                  AND longitude BETWEEN ? AND ?
                """,
                (custom_name, latitude - margin, latitude + margin, longitude - margin, longitude + margin),
            )

        logger.info("Registered user location alias #%d: '%s' around (%.4f, %.4f)", alias_id, custom_name, latitude, longitude)
        return {
            "id": alias_id,
            "latitude": latitude,
            "longitude": longitude,
            "custom_name": custom_name,
            "radius": radius,
            "created_at": now_iso,
        }

    def get_location_stats(self) -> List[Dict[str, Any]]:
        """Return aggregated place counts across the entire media archive."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT location_label, COUNT(*) as count
                FROM media
                WHERE location_label IS NOT NULL AND location_label != '' AND location_label != 'Misc'
                GROUP BY location_label
                ORDER BY count DESC
                """
            ).fetchall()

        return [{"name": r["location_label"], "count": r["count"]} for r in rows]

    def get_map_points(self) -> List[Dict[str, Any]]:
        """Return all geocoded media assets formatted for MapLibre point & cluster markers."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, latitude, longitude, location_label, original_filename, date_taken, media_type, people_json, labels_json
                FROM media
                WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                ORDER BY id DESC
                LIMIT 500
                """
            ).fetchall()

        points = []
        for r in rows:
            points.append({
                "id": r["id"],
                "lat": r["latitude"],
                "lon": r["longitude"],
                "title": r["location_label"] or r["original_filename"],
                "filename": r["original_filename"],
                "date_taken": r["date_taken"],
                "media_type": r["media_type"],
                "people": r["people_json"],
                "labels": r["labels_json"],
            })

        return points

    def get_service_status(self) -> Dict[str, Any]:
        """Return health status of OSM provider, GeoNames gazetteer, and SQLite cache count."""
        with sqlite3.connect(self.db_path) as conn:
            cache_count = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
            alias_count = conn.execute("SELECT COUNT(*) FROM location_aliases").fetchone()[0]

        # Check OSM connectivity
        osm_status = "CONNECTED"
        try:
            with httpx.Client(timeout=1.5) as client:
                res = client.get(f"{self.nominatim_url}/status.php")
                if res.status_code != 200 and res.status_code != 404:
                    osm_status = "ONLINE"
        except Exception:
            osm_status = "STANDBY"

        return {
            "openstreetmap": osm_status,
            "geonames": "READY" if self.geonames.cities else "UNAVAILABLE",
            "geonames_cities_loaded": len(self.geonames.cities),
            "cached_locations_count": cache_count,
            "user_aliases_count": alias_count,
            "provider_url": self.nominatim_url,
        }
