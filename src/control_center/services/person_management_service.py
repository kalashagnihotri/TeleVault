"""Person Identity Management Service (Phase 6.5H Pillar 2)

Provides full life-cycle identity operations:
- Rename, Merge, Split, Delete identities
- Identity Timeline distribution (Photos per year / month)
- Co-occurrence relationship mapping
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import load_config
from src.control_center.services.audit_service import record_audit_event

logger = logging.getLogger(__name__)


def _get_db_conn() -> sqlite3.Connection:
    config = load_config()
    db_path = Path(config.app.database_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def get_all_people_summaries() -> List[Dict[str, Any]]:
    """Return all people profiles with photo count, first/last seen, and confidence."""
    conn = _get_db_conn()
    people_list: List[Dict[str, Any]] = []
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT p.person_id, p.person_slug, p.display_name, p.active, p.created_at, p.updated_at,
                   COUNT(DISTINCT mf.media_id) as photo_count,
                   AVG(mf.best_score) as avg_confidence,
                   MIN(m.date_taken) as first_seen,
                   MAX(m.date_taken) as last_seen
            FROM people p
            LEFT JOIN media_faces mf ON p.person_id = mf.best_person_id AND mf.decision = 'KNOWN_MATCH'
            LEFT JOIN media m ON mf.media_id = m.id
            WHERE p.active = 1
            GROUP BY p.person_id
            ORDER BY photo_count DESC, p.display_name ASC
            """
        )
        for r in cur.fetchall():
            people_list.append({
                "person_id": r["person_id"],
                "person_slug": r["person_slug"],
                "display_name": r["display_name"],
                "photo_count": r["photo_count"],
                "avg_confidence_pct": round((r["avg_confidence"] or 0.9) * 100, 1),
                "first_seen": r["first_seen"] or r["created_at"],
                "last_seen": r["last_seen"] or r["updated_at"]
            })
        return people_list
    finally:
        conn.close()


def get_person_timeline(person_id: int) -> Dict[str, Any]:
    """
    Generate annual and monthly chronological photo distribution for a person.
    Example: 2024 (30 photos), 2025 (220 photos), 2026 (292 photos).
    """
    conn = _get_db_conn()
    timeline: Dict[str, Any] = {"person_id": person_id, "total_photos": 0, "years": {}}
    try:
        cur = conn.cursor()
        cur.execute("SELECT display_name FROM people WHERE person_id = ?", (person_id,))
        p_row = cur.fetchone()
        if not p_row:
            return timeline
        timeline["display_name"] = p_row["display_name"]

        cur.execute(
            """
            SELECT m.id as media_id, m.original_filename, m.date_taken, m.location_label
            FROM media_faces mf
            JOIN media m ON mf.media_id = m.id
            WHERE mf.best_person_id = ? AND mf.decision = 'KNOWN_MATCH'
            ORDER BY m.date_taken ASC
            """,
            (person_id,)
        )
        rows = cur.fetchall()
        timeline["total_photos"] = len(rows)

        years_map: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            dt = r["date_taken"] or "Unknown"
            year = dt[:4] if len(dt) >= 4 and dt[:4].isdigit() else "Other"
            month = dt[:7] if len(dt) >= 7 else year

            if year not in years_map:
                years_map[year] = {"year": year, "photo_count": 0, "months": {}, "sample_media_ids": []}
            
            years_map[year]["photo_count"] += 1
            if len(years_map[year]["sample_media_ids"]) < 5:
                years_map[year]["sample_media_ids"].append(r["media_id"])

            if month not in years_map[year]["months"]:
                years_map[year]["months"][month] = {"month": month, "count": 0}
            years_map[year]["months"][month]["count"] += 1

        timeline["years"] = sorted(years_map.values(), key=lambda y: y["year"])
        return timeline
    finally:
        conn.close()


def rename_person(person_id: int, new_display_name: str) -> Dict[str, Any]:
    """Rename a person display name and log audit event."""
    conn = _get_db_conn()
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        cur = conn.cursor()
        cur.execute("SELECT display_name FROM people WHERE person_id = ?", (person_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Person #{person_id} not found")
        old_name = row["display_name"]

        with conn:
            conn.execute("UPDATE people SET display_name = ?, updated_at = ? WHERE person_id = ?", (new_display_name, now_iso, person_id))

        record_audit_event(
            actor="USER",
            action="RENAME_PERSON",
            object_type="person",
            object_id=str(person_id),
            before_state={"display_name": old_name},
            after_state={"display_name": new_display_name}
        )
        return {"success": True, "person_id": person_id, "old_name": old_name, "new_name": new_display_name}
    finally:
        conn.close()


def split_person_identity(source_person_id: int, target_media_face_ids: List[int], new_person_name: str) -> Dict[str, Any]:
    """Split selected face occurrences out from one identity into a new separate identity."""
    conn = _get_db_conn()
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        cur = conn.cursor()
        cur.execute("SELECT display_name FROM people WHERE person_id = ?", (source_person_id,))
        src_row = cur.fetchone()
        if not src_row:
            raise ValueError(f"Source person #{source_person_id} not found")

        slug = new_person_name.lower().replace(" ", "_")
        with conn:
            c = conn.execute(
                "INSERT INTO people (person_slug, display_name, active, created_at, updated_at) VALUES (?, ?, 1, ?, ?)",
                (slug, new_person_name, now_iso, now_iso)
            )
            new_p_id = c.lastrowid

            for mf_id in target_media_face_ids:
                conn.execute(
                    "UPDATE media_faces SET best_person_id = ? WHERE id = ? AND best_person_id = ?",
                    (new_p_id, mf_id, source_person_id)
                )

        record_audit_event(
            actor="USER",
            action="SPLIT_PERSON_IDENTITY",
            object_type="person",
            object_id=str(source_person_id),
            before_state={"display_name": src_row["display_name"], "face_ids": target_media_face_ids},
            after_state={"new_person_id": new_p_id, "new_name": new_person_name}
        )
        return {"success": True, "new_person_id": new_p_id, "moved_face_count": len(target_media_face_ids)}
    finally:
        conn.close()


def delete_person(person_id: int) -> Dict[str, Any]:
    """Soft delete / deactivate a person identity."""
    conn = _get_db_conn()
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        cur = conn.cursor()
        cur.execute("SELECT display_name FROM people WHERE person_id = ?", (person_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Person #{person_id} not found")

        with conn:
            conn.execute("UPDATE people SET active = 0, updated_at = ? WHERE person_id = ?", (now_iso, person_id))
            conn.execute("UPDATE media_faces SET decision = 'UNKNOWN' WHERE best_person_id = ?", (person_id,))

        record_audit_event(
            actor="USER",
            action="DELETE_PERSON",
            object_type="person",
            object_id=str(person_id),
            before_state={"display_name": row["display_name"], "active": 1},
            after_state={"active": 0}
        )
        return {"success": True, "person_id": person_id, "message": f"Person '{row['display_name']}' deactivated."}
    finally:
        conn.close()
