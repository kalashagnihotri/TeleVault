"""Synthetic Test Data Generator & Archive Simulator (Phase 6.5H Pillar 11)

Generates complete, rich, synthetic datasets (Photos, People, Locations, Documents, Videos)
to enable comprehensive pipeline stress testing and disaster simulations on demand.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List
from PIL import Image, ImageDraw

from src.config import load_config

logger = logging.getLogger(__name__)


def generate_synthetic_archive_dataset(
    photo_count: int = 50,
    people_count: int = 5,
    locations_count: int = 3,
    output_dir: str = "data/simulator_dataset"
) -> Dict[str, Any]:
    """Generate and ingest a synthetic multi-modal dataset."""
    config = load_config()
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(config.app.database_path)
    now = datetime.now(timezone.utc)

    people_names = ["Alice Wonder", "Bob Builder", "Charlie Chaplin", "Diana Prince", "Ethan Hunt"][:people_count]
    locations = ["Yosemite National Park", "Austin Texas", "Tokyo Japan", "Paris France", "Malibu Beach"][:locations_count]
    categories = ["Landscape", "Portrait", "Document", "Receipt", "Event"]

    created_people_ids = []
    created_media_ids = []

    try:
        with conn:
            # 1. Create People
            for p_name in people_names:
                slug = p_name.lower().replace(" ", "_")
                c = conn.execute(
                    "INSERT OR REPLACE INTO people (person_slug, display_name, active, created_at, updated_at) VALUES (?, ?, 1, ?, ?)",
                    (slug, p_name, now.isoformat(), now.isoformat())
                )
                created_people_ids.append(c.lastrowid)

            # 2. Create Media Photos & Documents
            for i in range(photo_count):
                fn = f"simulated_asset_{i+1:03d}.jpg"
                fp = out_path / fn
                
                cat = categories[i % len(categories)]
                loc = locations[i % len(locations)]
                assigned_person = [people_names[i % len(people_names)]] if cat == "Portrait" else []
                
                # Synthetic image with PIL
                img = Image.new("RGB", (200, 200), color=((i * 37) % 255, (i * 73) % 255, (i * 109) % 255))
                draw = ImageDraw.Draw(img)
                draw.text((20, 90), f"{cat} #{i+1}", fill=(255, 255, 255))
                img.save(fp, quality=80)

                date_val = (now - timedelta(days=i * 2)).strftime("%Y-%m-%d")
                sha = f"sim_sha_{i+1:04d}_{hash(fn) & 0xffff}"

                c = conn.execute(
                    """
                    INSERT OR REPLACE INTO media 
                    (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, face_state, scene_state, labels_json, people_json, date_taken, location_label, discovered_at, updated_at)
                    VALUES (?, ?, ?, ?, 'image', ?, 0, 'BACKED_UP', 'ANALYZED', 'ANALYZED', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sha, sha[:8], str(fp), fn, fp.stat().st_size,
                        json.dumps([cat, loc]), json.dumps(assigned_person),
                        date_val, loc, now.isoformat(), now.isoformat()
                    )
                )
                created_media_ids.append(c.lastrowid)

        return {
            "success": True,
            "photos_generated": photo_count,
            "people_generated": len(people_names),
            "locations_used": locations,
            "output_directory": str(out_path),
            "total_media_ingested": len(created_media_ids)
        }
    finally:
        conn.close()
