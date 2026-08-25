"""Portable Archive Export Service (Phase 6.5G Pillar 10)

Generates a completely portable, application-independent archive folder structure:
MyArchive/
  ├── photos/
  ├── videos/
  ├── metadata.json
  ├── people.json
  ├── memories.json
  └── timeline.json

Packages into a standardized .zip bundle guaranteeing lifetime memory preservation.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import load_config
from src.control_center.services.memory_service import detect_events as cluster_memories

logger = logging.getLogger(__name__)

EXPORTS_DIR = Path("data/exports")


def _get_db_conn() -> sqlite3.Connection:
    config = load_config()
    db_path = Path(config.app.database_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def export_portable_archive_bundle() -> Dict[str, Any]:
    """
    Generate and zip a fully portable standalone archive directory.
    """
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    bundle_name = f"MyArchive_{timestamp_str}"
    bundle_dir = EXPORTS_DIR / bundle_name
    
    photos_dir = bundle_dir / "photos"
    videos_dir = bundle_dir / "videos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    videos_dir.mkdir(parents=True, exist_ok=True)

    conn = _get_db_conn()
    try:
        cur = conn.cursor()
        
        # 1. Fetch Media Metadata
        cur.execute("SELECT id, sha256, original_filename, original_path, media_type, size_bytes, date_taken, location_label, labels_json, people_json FROM media WHERE state = 'BACKED_UP'")
        media_rows = [dict(r) for r in cur.fetchall()]

        # Copy physical media assets if present locally
        copied_photos = 0
        copied_videos = 0
        clean_metadata = []

        for m in media_rows:
            src_path = Path(m["original_path"])
            clean_entry = {
                "id": m["id"],
                "sha256": m["sha256"],
                "filename": m["original_filename"],
                "media_type": m["media_type"],
                "size_bytes": m["size_bytes"],
                "date_taken": m["date_taken"],
                "location": m["location_label"],
                "labels": json.loads(m["labels_json"] or "[]"),
                "people": json.loads(m["people_json"] or "[]")
            }
            clean_metadata.append(clean_entry)

            if src_path.exists():
                try:
                    if m["media_type"] == "image":
                        dest = photos_dir / m["original_filename"]
                        if not dest.exists():
                            shutil.copy2(src_path, dest)
                            copied_photos += 1
                    elif m["media_type"] == "video":
                        dest = videos_dir / m["original_filename"]
                        if not dest.exists():
                            shutil.copy2(src_path, dest)
                            copied_videos += 1
                except Exception as e:
                    logger.warning("Failed to copy %s to portable export: %s", src_path, e)

        # 2. Fetch People
        cur.execute("SELECT person_id as id, person_slug, display_name, active, created_at FROM people")
        people_rows = [dict(r) for r in cur.fetchall()]

        # 3. Fetch Memories
        try:
            memories_list = cluster_memories()
        except Exception:
            memories_list = []

        # 4. Generate Timeline
        timeline_events = []
        for m in clean_metadata:
            if m.get("date_taken"):
                timeline_events.append({
                    "date": m["date_taken"],
                    "filename": m["filename"],
                    "location": m["location"],
                    "people": m["people"],
                    "labels": m["labels"]
                })
        timeline_events.sort(key=lambda x: x["date"])

        # Write manifest JSON files
        (bundle_dir / "metadata.json").write_text(json.dumps(clean_metadata, indent=2), encoding="utf-8")
        (bundle_dir / "people.json").write_text(json.dumps(people_rows, indent=2), encoding="utf-8")
        (bundle_dir / "memories.json").write_text(json.dumps(memories_list, indent=2), encoding="utf-8")
        (bundle_dir / "timeline.json").write_text(json.dumps(timeline_events, indent=2), encoding="utf-8")

        # 5. Compress into .zip
        zip_path = EXPORTS_DIR / f"{bundle_name}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(bundle_dir):
                for file in files:
                    file_p = Path(root) / file
                    rel_p = file_p.relative_to(bundle_dir)
                    zipf.write(file_p, arcname=str(Path(bundle_name) / rel_p))

        # Cleanup unzipped folder
        shutil.rmtree(bundle_dir, ignore_errors=True)

        logger.info("Successfully generated portable archive: %s", zip_path.name)
        return {
            "success": True,
            "bundle_filename": zip_path.name,
            "bundle_path": str(zip_path),
            "media_count": len(clean_metadata),
            "people_count": len(people_rows),
            "memories_count": len(memories_list),
            "photos_copied": copied_photos,
            "videos_copied": copied_videos,
            "file_size_bytes": zip_path.stat().st_size
        }
    finally:
        conn.close()
