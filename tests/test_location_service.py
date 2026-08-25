"""Tests for Location Intelligence Service (Phase 6.5I).

Verifies:
- Test 1: Known coordinates resolution (Yosemite)
- Test 2: Cache hit optimization (No repeated network calls)
- Test 3: User location alias learning (Lake Buena Vista -> Disney World)
- Test 4: Missing GPS safety handling (UNKNOWN_LOCATION)
- Test 5: Offline mode resilience (GeoNames fallback)
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.control_center.services.location_service import LocationService, LocationResult

@pytest.fixture
def test_location_env():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        tmp_p = Path(tmp_dir)
        db_p = tmp_p / "test_locations.sqlite3"

        # Initialize schema from migrations
        conn = sqlite3.connect(db_p)
        for sql_file in sorted(Path("sql").glob("*.sql")):
            conn.executescript(sql_file.read_text(encoding="utf-8"))
        conn.close()

        service = LocationService(
            db_path=db_p,
            geonames_dir=tmp_p / "geonames",
            nominatim_url="https://nominatim.openstreetmap.org",
            cache_results=True,
            enabled=True,
        )

        yield {
            "dir": tmp_p,
            "db_path": db_p,
            "service": service,
        }

def test_1_known_coordinates_yosemite(test_location_env):
    """Test 1: Known coordinates for Yosemite resolve to Yosemite National Park or California."""
    service = test_location_env["service"]
    
    # Yosemite National Park coordinates
    lat = 37.8651
    lon = -119.5383

    res = service.resolve_location(lat, lon)
    assert res is not None
    assert "Yosemite" in res.place_name or "California" in res.place_name
    assert res.confidence >= 50
    assert res.source in ("openstreetmap", "geonames", "cache")

def test_2_cache_hit_optimization(test_location_env):
    """Test 2: Second lookup hits SQLite locations cache without re-querying provider."""
    service = test_location_env["service"]
    db_p = test_location_env["db_path"]

    lat = 37.7749
    lon = -122.4194

    # First lookup (caches in SQLite)
    res1 = service.resolve_location(lat, lon)
    assert res1.place_name != "UNKNOWN_LOCATION"

    # Verify written to locations table
    with sqlite3.connect(db_p) as conn:
        count = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
        assert count >= 1

    # Second lookup with network mocked to fail
    with patch("httpx.Client.get", side_effect=Exception("Network Offline")):
        res2 = service.resolve_location(lat, lon)
        assert res2.source == "cache"
        assert res2.place_name == res1.place_name

def test_3_user_location_alias_learning(test_location_env):
    """Test 3: User location alias correction (Lake Buena Vista -> Disney World)."""
    service = test_location_env["service"]
    db_p = test_location_env["db_path"]

    # Coordinates near Disney World / Lake Buena Vista, FL
    lat = 28.3772
    lon = -81.5707

    # Seed media record
    with sqlite3.connect(db_p) as conn:
        conn.execute(
            """
            INSERT INTO media (id, sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, face_state, scene_state, latitude, longitude, location_label, discovered_at, updated_at)
            VALUES (1, 'sha_disney', 'sh_d', '/disney.jpg', 'disney.jpg', 'image', 1000, 0, 'BACKED_UP', 'ANALYZED', 'ANALYZED', ?, ?, 'Lake Buena Vista', '2026-08-25', '2026-08-25')
            """,
            (lat, lon),
        )

    # Initial resolve before alias
    res_before = service.resolve_location(lat, lon)

    # Register user correction alias
    alias_res = service.add_user_alias(latitude=lat, longitude=lon, custom_name="Disney World", radius=0.05)
    assert alias_res["custom_name"] == "Disney World"

    # Resolve after alias
    res_after = service.resolve_location(lat, lon)
    assert res_after.source == "user_alias"
    assert res_after.place_name == "Disney World"
    assert res_after.confidence == 100

    # Verify media record was updated
    with sqlite3.connect(db_p) as conn:
        updated_label = conn.execute("SELECT location_label FROM media WHERE id = 1").fetchone()[0]
        assert updated_label == "Disney World"

def test_4_no_gps_safety_handling(test_location_env):
    """Test 4: Missing or None GPS coordinates safely returns UNKNOWN_LOCATION."""
    service = test_location_env["service"]

    res = service.resolve_location(None, None)
    assert res.place_name == "UNKNOWN_LOCATION"
    assert res.confidence == 0
    assert res.source == "raw_gps"

def test_5_offline_mode_geonames_fallback(test_location_env):
    """Test 5: When online provider is offline, falls back to GeoNames city gazetteer."""
    service = test_location_env["service"]
    
    # Austin, Texas coordinates
    lat = 30.2672
    lon = -97.7431

    # Force network failure to test offline GeoNames fallback
    with patch("httpx.Client.get", side_effect=Exception("Connection Refused")):
        res = service.resolve_location(lat, lon)
        assert res.source == "geonames"
        assert "Austin" in res.city or "Texas" in res.state
        assert res.confidence >= 50
