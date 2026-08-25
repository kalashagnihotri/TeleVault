"""Extensible Plugin Architecture Service (Phase 6.5H Pillar 12)

Manages discovery, dynamic registration, toggling, and hook execution for modular archive extensions.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import load_config

logger = logging.getLogger(__name__)

DEFAULT_PLUGINS = [
    {
        "plugin_name": "ocr_intelligence",
        "version": "1.0.0",
        "description": "Optical character recognition and structured financial field extraction for receipts and documents."
    },
    {
        "plugin_name": "weather_enrichment",
        "version": "1.0.0",
        "description": "Historical weather tagging based on EXIF GPS coordinates and timestamps."
    },
    {
        "plugin_name": "reverse_geocoding",
        "version": "1.1.0",
        "description": "Converts latitude/longitude into human-readable city, state, and landmark labels."
    }
]


def _get_db_conn() -> sqlite3.Connection:
    config = load_config()
    db_path = Path(config.app.database_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def initialize_plugins_registry() -> None:
    """Ensure standard built-in plugins are populated in the registry."""
    conn = _get_db_conn()
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        with conn:
            for p in DEFAULT_PLUGINS:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO plugins_registry (plugin_name, version, description, enabled, installed_at)
                    VALUES (?, ?, ?, 1, ?)
                    """,
                    (p["plugin_name"], p["version"], p["description"], now_iso)
                )
    finally:
        conn.close()


def get_all_plugins() -> List[Dict[str, Any]]:
    """Return all registered plugins and their enabled status."""
    initialize_plugins_registry()
    conn = _get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM plugins_registry ORDER BY plugin_name ASC")
        return [
            {
                "plugin_name": r["plugin_name"],
                "version": r["version"],
                "description": r["description"],
                "enabled": bool(r["enabled"]),
                "installed_at": r["installed_at"]
            }
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def toggle_plugin(plugin_name: str, enabled: bool) -> Dict[str, Any]:
    """Enable or disable a plugin extension."""
    conn = _get_db_conn()
    try:
        with conn:
            conn.execute("UPDATE plugins_registry SET enabled = ? WHERE plugin_name = ?", (1 if enabled else 0, plugin_name))
        return {"success": True, "plugin_name": plugin_name, "enabled": enabled}
    finally:
        conn.close()
