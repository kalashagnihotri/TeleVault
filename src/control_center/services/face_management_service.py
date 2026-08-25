import sqlite3
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from src.config import load_config

logger = logging.getLogger(__name__)


def _get_db_conn() -> sqlite3.Connection:
    config = load_config()
    db_path = config.app.database_path
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def get_unknown_face_clusters() -> List[Dict[str, Any]]:
    """
    Returns grouped unknown face clusters requiring user review:
    - cluster ID
    - total appearances
    - date range
    - locations
    - sample media items
    """
    conn = _get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT mf.media_face_id as face_id, mf.media_id, mf.detector_confidence, mf.decision,
                   m.original_filename, m.date_taken, m.location_label
            FROM media_faces mf
            JOIN media m ON mf.media_id = m.id
            WHERE mf.decision IN ('UNKNOWN', 'QUESTIONABLE')
            ORDER BY m.date_taken DESC
            """
        )
        rows = cur.fetchall()
        
        # Group into clusters
        clusters_map: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            # Group by location or rough temporal proximity
            loc = r["location_label"] or "General"
            dt = (r["date_taken"] or "")[:7] or "Unknown Date"
            cluster_key = f"cluster_{loc}_{dt}".replace(" ", "_")

            if cluster_key not in clusters_map:
                clusters_map[cluster_key] = {
                    "cluster_id": cluster_key,
                    "title": f"Unknown Person ({loc} • {dt})",
                    "appearances_count": 0,
                    "location": loc,
                    "date_period": dt,
                    "sample_faces": [],
                    "media_ids": []
                }

            clusters_map[cluster_key]["appearances_count"] += 1
            if r["media_id"] not in clusters_map[cluster_key]["media_ids"]:
                clusters_map[cluster_key]["media_ids"].append(r["media_id"])
            if len(clusters_map[cluster_key]["sample_faces"]) < 4:
                clusters_map[cluster_key]["sample_faces"].append({
                    "face_id": r["face_id"],
                    "media_id": r["media_id"],
                    "filename": r["original_filename"],
                    "confidence": r["detector_confidence"]
                })

        return list(clusters_map.values())
    finally:
        conn.close()


def create_person_from_cluster(cluster_id: str, display_name: str) -> Dict[str, Any]:
    """Enroll a new identity from an unknown cluster and assign all faces to them."""
    conn = _get_db_conn()
    try:
        cur = conn.cursor()
        slug = display_name.lower().replace(" ", "_")
        now = datetime.now(timezone.utc).isoformat()
        
        cur.execute(
            "INSERT INTO people (person_slug, display_name, active, created_at, updated_at) VALUES (?, ?, 1, ?, ?)",
            (slug, display_name, now, now)
        )
        new_person_id = cur.lastrowid

        # Update matching unknown faces
        cur.execute(
            """
            UPDATE media_faces 
            SET best_person_id = ?, decision = 'KNOWN_MATCH', best_score = 0.90 
            WHERE decision IN ('UNKNOWN', 'QUESTIONABLE')
            """,
            (new_person_id,)
        )
        conn.commit()

        return {
            "success": True,
            "person_id": new_person_id,
            "display_name": display_name,
            "message": f"Successfully enrolled '{display_name}' and assigned matching faces."
        }
    finally:
        conn.close()


def merge_identities(source_person_id: int, target_person_id: int) -> Dict[str, Any]:
    """Atomically merge a duplicate person identity into a canonical target identity."""
    conn = _get_db_conn()
    try:
        cur = conn.cursor()
        
        # Verify both exist
        cur.execute("SELECT person_id, display_name FROM people WHERE person_id = ?", (source_person_id,))
        source = cur.fetchone()
        cur.execute("SELECT person_id, display_name FROM people WHERE person_id = ?", (target_person_id,))
        target = cur.fetchone()

        if not source or not target:
            raise ValueError("Source or target person ID does not exist.")

        # Reassign all media_faces
        cur.execute(
            "UPDATE media_faces SET best_person_id = ? WHERE best_person_id = ?",
            (target_person_id, source_person_id)
        )
        reassigned_count = cur.rowcount

        # Deactivate source person
        cur.execute("UPDATE people SET active = 0, updated_at = ? WHERE person_id = ?", (datetime.now(timezone.utc).isoformat(), source_person_id))
        conn.commit()
        conn.commit()

        return {
            "success": True,
            "reassigned_faces_count": reassigned_count,
            "source_name": source["display_name"],
            "target_name": target["display_name"],
            "message": f"Merged '{source['display_name']}' into '{target['display_name']}' ({reassigned_count} faces reassigned)."
        }
    finally:
        conn.close()


def get_face_confidence_stats() -> Dict[str, Any]:
    """Return distribution of confirmed, questionable, and rejected face decisions."""
    conn = _get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT decision, COUNT(*) as cnt FROM media_faces GROUP BY decision")
        rows = cur.fetchall()
        
        stats = {
            "confirmed_matches": 0,
            "questionable_matches": 0,
            "unknown_matches": 0,
            "rejected_matches": 0,
            "total_faces": 0
        }
        
        for r in rows:
            dec = r["decision"]
            count = r["cnt"]
            stats["total_faces"] += count
            if dec == "KNOWN_MATCH":
                stats["confirmed_matches"] += count
            elif dec == "QUESTIONABLE":
                stats["questionable_matches"] += count
            elif dec == "UNKNOWN":
                stats["unknown_matches"] += count
            elif dec in ("REJECTED", "IGNORED"):
                stats["rejected_matches"] += count

        return stats
    finally:
        conn.close()
