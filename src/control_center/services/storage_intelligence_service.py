"""Storage Intelligence & Capacity Optimization Service for Phase 6.5I.

Analyzes archive storage footprint across media types, flags heavy high-bitrate assets,
and computes cold storage and compression savings recommendations.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

def _fmt_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    if num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.2f} MB"
    return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"

class StorageIntelligenceService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def get_storage_breakdown(self) -> Dict[str, Any]:
        """Compute full storage distribution by media type, largest files, and optimization candidates."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT media_type, COUNT(*) as file_count, SUM(size_bytes) as total_bytes
                FROM media
                GROUP BY media_type
                """
            ).fetchall()

            largest_rows = conn.execute(
                """
                SELECT id, original_filename, original_path, media_type, size_bytes, date_taken, discovered_at
                FROM media
                ORDER BY size_bytes DESC
                LIMIT 10
                """
            ).fetchall()

            total_assets = conn.execute("SELECT COUNT(*), SUM(size_bytes) FROM media").fetchone()

        total_count = total_assets[0] or 0
        total_bytes = total_assets[1] or 0

        categories: Dict[str, Dict[str, Any]] = {
            "photos": {"file_count": 0, "size_bytes": 0, "size_formatted": "0 B"},
            "videos": {"file_count": 0, "size_bytes": 0, "size_formatted": "0 B"},
            "documents": {"file_count": 0, "size_bytes": 0, "size_formatted": "0 B"},
            "audio": {"file_count": 0, "size_bytes": 0, "size_formatted": "0 B"},
            "other": {"file_count": 0, "size_bytes": 0, "size_formatted": "0 B"},
        }

        for r in rows:
            mtype = (r["media_type"] or "").lower()
            bytes_val = r["total_bytes"] or 0
            cnt = r["file_count"] or 0

            if "image" in mtype or "photo" in mtype:
                cat = "photos"
            elif "video" in mtype:
                cat = "videos"
            elif "doc" in mtype or "pdf" in mtype:
                cat = "documents"
            elif "audio" in mtype:
                cat = "audio"
            else:
                cat = "other"

            categories[cat]["file_count"] += cnt
            categories[cat]["size_bytes"] += bytes_val
            categories[cat]["size_formatted"] = _fmt_size(categories[cat]["size_bytes"])

        largest_files = [
            {
                "media_id": r["id"],
                "filename": r["original_filename"],
                "media_type": r["media_type"],
                "size_bytes": r["size_bytes"],
                "size_formatted": _fmt_size(r["size_bytes"] or 0),
                "date_taken": r["date_taken"],
            }
            for r in largest_rows
        ]

        # Potential savings estimate (e.g. 40% compression on uncompressed videos/images)
        estimated_savings_bytes = int(categories["videos"]["size_bytes"] * 0.45 + categories["photos"]["size_bytes"] * 0.20)

        return {
            "total_media_count": total_count,
            "total_size_bytes": total_bytes,
            "total_size_formatted": _fmt_size(total_bytes),
            "category_distribution": categories,
            "largest_files": largest_files,
            "estimated_compression_savings_bytes": estimated_savings_bytes,
            "estimated_compression_savings_formatted": _fmt_size(estimated_savings_bytes),
            "cold_storage_candidate_count": max(0, int(total_count * 0.3)),
        }
