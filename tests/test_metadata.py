import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.metadata_image import extract_image_metadata
from src.metadata_video import extract_video_metadata
from src.places import PlaceResolver, PlaceConfig
from src.routing import choose_topic, RouteInput

class MockExif(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self["dummy"] = True  # Ensure it is truthy

    def get_ifd(self, tag):
        if tag == 34853:
            return {
                1: "N",  # GPSLatitudeRef
                2: (37, 30, 0), # 37.5
                3: "W",  # GPSLongitudeRef
                4: (121, 30, 0) # 121.5
            }
        return {}

def test_image_metadata_extraction(tmp_path: Path) -> None:
    # 1. Image without GPS
    no_gps = tmp_path / "no_gps.jpg"
    no_gps.write_bytes(b"dummy")
    
    with patch('src.metadata_image.Image.open') as mock_open:
        mock_img = MagicMock()
        mock_img.getexif.return_value = {}
        mock_open.return_value.__enter__.return_value = mock_img
        
        meta = extract_image_metadata(no_gps)
        assert not meta.has_gps
        assert meta.latitude is None
    
    # 2. Image with GPS
    with_gps = tmp_path / "with_gps.jpg"
    with_gps.write_bytes(b"dummy")
    
    with patch('src.metadata_image.Image.open') as mock_open:
        mock_img = MagicMock()
        mock_exif = MockExif()
        mock_img.getexif.return_value = mock_exif
        mock_open.return_value.__enter__.return_value = mock_img
        
        meta = extract_image_metadata(with_gps)
        assert meta.has_gps
        assert abs(meta.latitude - 37.5) < 0.001
        assert abs(meta.longitude - (-121.5)) < 0.001
    
    # 3. Corrupt image
    corrupt = tmp_path / "corrupt.jpg"
    corrupt.write_bytes(b"not an image file data at all")
    meta = extract_image_metadata(corrupt)
    assert not meta.has_gps

def test_video_metadata_deep_scan(tmp_path: Path) -> None:
    with_gps = tmp_path / "with_gps.mp4"
    with_gps.write_bytes(b"dummy")
    
    # Mock subprocess.run for ffprobe
    with patch('subprocess.run') as mock_run:
        mock_run.return_value.stdout = json.dumps({
            "format": {
                "tags": {
                    "creation_time": "2025-09-12T04:46:55.000000Z"
                }
            },
            "streams": [
                {
                    "tags": {
                        "location-eng": "+30.7033+076.2206/"
                    }
                }
            ]
        })
        mock_run.return_value.returncode = 0
        
        meta = extract_video_metadata(with_gps)
        assert meta.has_gps
        assert abs(meta.latitude - 30.7033) < 0.001
        assert abs(meta.longitude - 76.2206) < 0.001
        assert meta.date_taken == "2025-09-12T04:46:55+00:00"

def test_video_metadata_corrupt(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.mp4"
    corrupt.write_bytes(b"not a video file")
    meta = extract_video_metadata(corrupt)
    assert not meta.has_gps

def test_places_resolver(tmp_path: Path) -> None:
    config_file = tmp_path / "places.json"
    config_file.write_text('''
    [
      {
        "label": "Home",
        "min_lat": 37.0,
        "max_lat": 38.0,
        "min_lon": -122.0,
        "max_lon": -121.0
      }
    ]
    ''')
    # 1. Test offline mode
    offline_resolver = PlaceResolver(config_file, cache_path=tmp_path / "cache_off.json", enable_online_api=False)
    assert offline_resolver.resolve(37.5, -121.5) == "Home"
    assert offline_resolver.resolve(40.0, -121.5) == "Unknown GPS Location"
    assert offline_resolver.resolve(None, None) == "Misc"

    # 2. Test online API mode
    online_resolver = PlaceResolver(config_file, cache_path=tmp_path / "cache_on.json", enable_online_api=True)
    assert online_resolver.resolve(37.5, -121.5) == "Home"
    res_online = online_resolver.resolve(37.7749, -122.4194)
    assert "San Francisco" in res_online or "California" in res_online

def test_routing() -> None:
    # No GPS -> misc
    assert choose_topic(RouteInput("image", tuple(), tuple(), False)) == "misc"
    
    # Has GPS, no specific labels -> everyday
    assert choose_topic(RouteInput("image", tuple(), tuple(), True)) == "everyday"
    
    # Has GPS, video -> videos
    assert choose_topic(RouteInput("video", tuple(), tuple(), True)) == "videos"
    
    # Specific label
    assert choose_topic(RouteInput("image", tuple(), ("mountains",), True)) == "travel_nature"
