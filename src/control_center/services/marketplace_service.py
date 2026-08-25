"""Plugin Marketplace Service for Phase 7.

Maintains catalog of certified community and official extensions (OCR+, Weather+, Maps+, AudioTranscribe+)
with 1-click installation and validation.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

MARKETPLACE_CATALOG = [
    {
        "plugin_id": "ocr_plus",
        "title": "OCR+ Enterprise Document Scanner",
        "version": "2.1.0",
        "author": "TeleVault Core Team",
        "description": "Multi-lingual document text extraction with auto-currency and table parsing.",
        "icon": "FileText",
        "category": "DOCUMENT_AI",
        "installed": True,
    },
    {
        "plugin_id": "weather_plus",
        "title": "Weather+ Historical Context",
        "version": "1.2.0",
        "author": "Open-Meteo Integration",
        "description": "Enriches photo EXIF GPS with historical temperature, sky condition, and weather tags.",
        "icon": "CloudSun",
        "category": "ENRICHMENT",
        "installed": True,
    },
    {
        "plugin_id": "maps_plus",
        "title": "Maps+ High-Precision Reverse Geocoding",
        "version": "1.5.0",
        "author": "Nominatim OSM Engine",
        "description": "Offline street and point-of-interest reverse geocoding from latitude/longitude coordinates.",
        "icon": "MapPin",
        "category": "LOCATION",
        "installed": True,
    },
    {
        "plugin_id": "audio_transcribe",
        "title": "AudioTranscribe+ Whisper Speech Engine",
        "version": "1.0.0",
        "author": "Whisper.cpp Engine",
        "description": "Transcribes spoken audio tracks in videos directly into searchable transcripts.",
        "icon": "Mic",
        "category": "AUDIO_AI",
        "installed": False,
    },
]

class PluginMarketplaceService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def list_marketplace_plugins(self) -> List[Dict[str, Any]]:
        """Return full marketplace catalog with installation state."""
        with sqlite3.connect(self.db_path) as conn:
            installed = {r[0] for r in conn.execute("SELECT plugin_name FROM plugins_registry").fetchall()}

        plugins = []
        for p in MARKETPLACE_CATALOG:
            item = dict(p)
            item["installed"] = (p["plugin_id"] in installed or p.get("installed", False))
            plugins.append(item)
        return plugins

    def install_plugin(self, plugin_id: str) -> Dict[str, Any]:
        """Install a plugin from the marketplace into plugins_registry."""
        found = next((p for p in MARKETPLACE_CATALOG if p["plugin_id"] == plugin_id), None)
        if not found:
            raise ValueError(f"Plugin {plugin_id} not found in marketplace catalog.")

        now_iso = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO plugins_registry (plugin_name, version, description, enabled, installed_at)
                VALUES (?, ?, ?, 1, ?)
                """,
                (found["plugin_id"], found["version"], found["description"], now_iso),
            )

        logger.info("Successfully installed marketplace plugin %s v%s", found["plugin_id"], found["version"])
        return {
            "success": True,
            "plugin_id": found["plugin_id"],
            "version": found["version"],
            "message": f"Plugin '{found['title']}' installed and enabled successfully.",
        }
