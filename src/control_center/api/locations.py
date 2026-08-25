"""Location Intelligence and MapLibre REST API Endpoints for Phase 6.5I."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.config import load_config
from src.control_center.services.location_service import LocationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["locations"])

def _get_location_service() -> LocationService:
    cfg = load_config()
    return LocationService(
        db_path=Path(cfg.app.database_path),
        nominatim_url=cfg.location.nominatim_url if hasattr(cfg, "location") else "https://nominatim.openstreetmap.org",
        cache_results=cfg.location.cache_results if hasattr(cfg, "location") else True,
        enabled=cfg.location.enabled if hasattr(cfg, "location") else True,
    )

class AliasRequest(BaseModel):
    latitude: float
    longitude: float
    custom_name: str
    radius: float = 0.05

class TestLookupRequest(BaseModel):
    latitude: float
    longitude: float

# 1. Location Statistics
@router.get("/api/archive/location_stats")
def get_location_statistics(service: LocationService = Depends(_get_location_service)) -> List[Dict[str, Any]]:
    """Return aggregated place counts across the archive."""
    return service.get_location_stats()

# 2. Map Data Points for MapLibre
@router.get("/api/archive/map_points")
def get_map_points(service: LocationService = Depends(_get_location_service)) -> List[Dict[str, Any]]:
    """Return all geocoded media points formatted for MapLibre GL."""
    return service.get_map_points()

# 3. User Location Correction / Alias Registration
@router.post("/api/location/alias")
def add_user_location_alias(req: AliasRequest, service: LocationService = Depends(_get_location_service)) -> Dict[str, Any]:
    """Learn and register a user-defined location alias (e.g. 'Disney World')."""
    return service.add_user_alias(
        latitude=req.latitude,
        longitude=req.longitude,
        custom_name=req.custom_name,
        radius=req.radius,
    )

# 4. Service Status & Health (Defined before dynamic /api/location/{media_id})
@router.get("/api/location/status")
def get_location_status(service: LocationService = Depends(_get_location_service)) -> Dict[str, Any]:
    """Get status of OSM provider, GeoNames gazetteer, and SQLite cache count."""
    return service.get_service_status()

# 5. Test GPS Lookup
@router.post("/api/location/test_lookup")
def test_gps_lookup(req: TestLookupRequest, service: LocationService = Depends(_get_location_service)) -> Dict[str, Any]:
    """Directly test location resolution for custom coordinates."""
    res = service.resolve_location(req.latitude, req.longitude)
    return res.to_dict()

# 6. Rebuild Location Cache
@router.post("/api/location/rebuild_cache")
def rebuild_location_cache(service: LocationService = Depends(_get_location_service)) -> Dict[str, Any]:
    """Scan and re-resolve all media GPS coordinates into the locations cache."""
    cfg = load_config()
    with sqlite3.connect(cfg.app.database_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, latitude, longitude FROM media WHERE latitude IS NOT NULL AND longitude IS NOT NULL").fetchall()

        updated_count = 0
        for r in rows:
            res = service.resolve_location(r["latitude"], r["longitude"])
            if res.place_name and res.place_name != "UNKNOWN_LOCATION":
                conn.execute("UPDATE media SET location_label = ? WHERE id = ?", (res.place_name, r["id"]))
                updated_count += 1

    return {
        "success": True,
        "scanned_count": len(rows),
        "updated_count": updated_count,
        "message": f"Successfully refreshed location cache for {updated_count} media assets.",
    }

# 7. Location Health Scan
@router.post("/api/location/health_scan")
def location_health_scan(service: LocationService = Depends(_get_location_service)) -> Dict[str, Any]:
    """Audit location resolution coverage and GPS integrity."""
    cfg = load_config()
    with sqlite3.connect(cfg.app.database_path) as conn:
        total_media = conn.execute("SELECT COUNT(*) FROM media").fetchone()[0]
        with_gps = conn.execute("SELECT COUNT(*) FROM media WHERE latitude IS NOT NULL AND longitude IS NOT NULL").fetchone()[0]
        resolved = conn.execute("SELECT COUNT(*) FROM media WHERE location_label IS NOT NULL AND location_label != '' AND location_label != 'Misc'").fetchone()[0]
        aliases = conn.execute("SELECT COUNT(*) FROM location_aliases").fetchone()[0]
        cached_locs = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]

    gps_coverage_pct = round((with_gps / max(1, total_media)) * 100, 1)
    resolution_rate_pct = round((resolved / max(1, with_gps)) * 100, 1) if with_gps > 0 else 100.0

    return {
        "total_media": total_media,
        "media_with_gps": with_gps,
        "media_resolved_locations": resolved,
        "gps_coverage_pct": gps_coverage_pct,
        "resolution_rate_pct": resolution_rate_pct,
        "user_aliases_learned": aliases,
        "cached_unique_locations": cached_locs,
        "status": "HEALTHY" if resolution_rate_pct >= 90.0 else "WARNING",
    }

# 8. Location Lookup by Media ID
@router.get("/api/location/{media_id}")
def get_media_location(media_id: int, service: LocationService = Depends(_get_location_service)) -> Dict[str, Any]:
    """Retrieve GPS coordinates and resolved location for a specific media asset."""
    cfg = load_config()
    with sqlite3.connect(cfg.app.database_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, latitude, longitude, location_label, original_filename FROM media WHERE id = ?",
            (media_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Media asset not found")

    lat = row["latitude"]
    lon = row["longitude"]

    if lat is None or lon is None:
        return {
            "media_id": media_id,
            "filename": row["original_filename"],
            "gps": None,
            "location": {
                "name": "UNKNOWN_LOCATION",
                "confidence": 0,
            },
        }

    res = service.resolve_location(lat, lon)
    return {
        "media_id": media_id,
        "filename": row["original_filename"],
        "gps": {
            "lat": lat,
            "lon": lon,
        },
        "location": {
            "name": res.place_name,
            "confidence": res.confidence,
            "source": res.source,
            "city": res.city,
            "state": res.state,
            "country": res.country,
        },
    }
