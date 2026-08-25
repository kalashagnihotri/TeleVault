"""
Archive Intelligence Service (Phase 6.5D).
Provides:
- Multi-factor Similar Image Search (People, Scene, Temporal, GPS)
- Conversational Natural Language Assistant ("Ask Archive")
- Auto-generated Smart Collections (Trips, People, Documents, Highlights)
- Vault-wide Visual Analytics & Metadata Distribution
"""
from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.config import load_config

logger = logging.getLogger(__name__)


def _get_db_conn() -> sqlite3.Connection:
    config = load_config()
    db_path = Path(config.app.database_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on the Earth in km."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def _parse_labels(labels_raw: Any) -> List[str]:
    if not labels_raw:
        return []
    if isinstance(labels_raw, list):
        return [str(x).lower().strip() for x in labels_raw if str(x).strip()]
    if isinstance(labels_raw, str):
        try:
            parsed = json.loads(labels_raw)
            if isinstance(parsed, list):
                return [str(x).lower().strip() for x in parsed if str(x).strip()]
        except Exception:
            return [x.lower().strip() for x in labels_raw.split(",") if x.strip()]
    return []


# ==============================================================================
# 1. SIMILAR MEDIA SEARCH
# ==============================================================================

def find_similar_media(target_media_id: int, limit: int = 10) -> Dict[str, Any]:
    """
    Find top similar media items to a target item using multi-factor scoring:
    - People identity overlap (35%)
    - Scene labels Jaccard similarity (25%)
    - Temporal proximity (20%)
    - Geospatial GPS proximity (15%)
    - Media type match (5%)
    """
    conn = _get_db_conn()
    try:
        # 1. Fetch target media record
        target = conn.execute("SELECT * FROM media WHERE id = ?", (target_media_id,)).fetchone()
        if not target:
            raise ValueError(f"Media #{target_media_id} not found")

        # Fetch target people
        target_people = set()
        has_face_tables = bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='media_faces'").fetchone())
        if has_face_tables:
            p_rows = conn.execute(
                """
                SELECT DISTINCT p.person_id, p.display_name
                FROM media_faces mf
                JOIN people p ON mf.best_person_id = p.person_id
                WHERE mf.media_id = ? AND mf.decision = 'KNOWN_MATCH'
                """,
                (target_media_id,)
            ).fetchall()
            target_people = {r["person_id"]: r["display_name"] for r in p_rows}

        target_labels = set(_parse_labels(target["labels_json"]))
        target_date = None
        if target["date_taken"]:
            try:
                target_date = datetime.fromisoformat(target["date_taken"].replace("Z", "+00:00"))
            except Exception:
                pass

        target_lat = target["latitude"] if "latitude" in target.keys() else None
        target_lon = target["longitude"] if "longitude" in target.keys() else None
        target_type = target["media_type"]

        # 2. Fetch candidate media records
        candidates = conn.execute(
            """
            SELECT m.*, t.topic_id, t.preview_message_id, t.original_message_id, t.upload_confirmed_at, t.route_key
            FROM media m
            LEFT JOIN telegram_archive t ON m.id = t.media_id
            WHERE m.id != ?
            ORDER BY m.id DESC
            LIMIT 500
            """,
            (target_media_id,)
        ).fetchall()

        # Pre-fetch candidate people if faces enabled
        candidate_people_map: Dict[int, Dict[int, str]] = {}
        if has_face_tables and candidates:
            cand_ids = [c["id"] for c in candidates]
            placeholders = ",".join("?" for _ in cand_ids)
            cp_rows = conn.execute(
                f"""
                SELECT mf.media_id, p.person_id, p.display_name
                FROM media_faces mf
                JOIN people p ON mf.best_person_id = p.person_id
                WHERE mf.media_id IN ({placeholders}) AND mf.decision = 'KNOWN_MATCH'
                """,
                cand_ids
            ).fetchall()
            for r in cp_rows:
                candidate_people_map.setdefault(r["media_id"], {})[r["person_id"]] = r["display_name"]

        scored_items = []

        for cand in candidates:
            score = 0.0
            reasons = []

            # Factor A: People identity overlap (35%)
            cand_people = candidate_people_map.get(cand["id"], {})
            if target_people and cand_people:
                common_ids = set(target_people.keys()) & set(cand_people.keys())
                if common_ids:
                    ratio = len(common_ids) / max(len(target_people), len(cand_people))
                    score += ratio * 35.0
                    names = [target_people[pid] for pid in common_ids]
                    reasons.append(f"Shared people: {', '.join(names)}")
            elif not target_people and not cand_people:
                # Neutral baseline if neither has people
                score += 10.0

            # Factor B: Scene labels Jaccard similarity (25%)
            cand_labels = set(_parse_labels(cand["labels_json"]))
            if target_labels and cand_labels:
                intersection = target_labels & cand_labels
                union = target_labels | cand_labels
                if union:
                    jaccard = len(intersection) / len(union)
                    score += jaccard * 25.0
                    if intersection:
                        reasons.append(f"Matching tags: {', '.join(sorted(intersection)[:3])}")
            
            # Factor C: Temporal proximity (20%)
            if target_date and cand["date_taken"]:
                try:
                    c_date = datetime.fromisoformat(cand["date_taken"].replace("Z", "+00:00"))
                    delta = abs(target_date - c_date)
                    if delta <= timedelta(hours=1):
                        score += 20.0
                        reasons.append("Taken within 1 hour")
                    elif delta <= timedelta(hours=24):
                        score += 15.0
                        reasons.append("Taken on same day")
                    elif delta <= timedelta(days=7):
                        score += 10.0
                        reasons.append("Taken within same week")
                    elif delta <= timedelta(days=30):
                        score += 5.0
                except Exception:
                    pass

            # Factor D: Location / GPS proximity (15%)
            t_loc = target["location_label"] if "location_label" in target.keys() else None
            c_loc = cand["location_label"] if "location_label" in cand.keys() else None
            if t_loc and c_loc and t_loc.lower() not in ("misc", "", "none") and t_loc.lower() == c_loc.lower():
                score += 15.0
                reasons.append(f"Same location: {c_loc}")
            elif "has_gps" in target.keys() and "has_gps" in cand.keys() and target["has_gps"] and cand["has_gps"]:
                score += 5.0

            # Factor E: Media format match (5%)
            if cand["media_type"] == target_type:
                score += 5.0

            if score >= 15.0:
                similarity_pct = min(int(round(score)), 100)
                scored_items.append({
                    "media_id": cand["id"],
                    "similarity_score": similarity_pct,
                    "reasons": reasons if reasons else ["General visual & format similarity"],
                    "original_filename": cand["original_filename"],
                    "short_hash": cand["short_hash"],
                    "media_type": cand["media_type"],
                    "date_taken": cand["date_taken"],
                    "location_label": cand["location_label"] if "location_label" in cand.keys() else None,
                    "labels": list(cand_labels),
                    "people": list(cand_people.values()),
                    "topic_id": cand["topic_id"],
                    "preview_message_id": cand["preview_message_id"],
                    "original_message_id": cand["original_message_id"]
                })

        scored_items.sort(key=lambda x: x["similarity_score"], reverse=True)

        return {
            "target_media_id": target_media_id,
            "target_filename": target["original_filename"],
            "total_matches": len(scored_items),
            "similar_items": scored_items[:limit]
        }
    finally:
        conn.close()


# ==============================================================================
# 2. NATURAL LANGUAGE ASSISTANT ("ASK ARCHIVE")
# ==============================================================================

def process_assistant_query(query_text: str) -> Dict[str, Any]:
    """
    Translates natural language questions into structured SQL queries with clear explanations.
    Examples:
    - "Show my family trips in 2025" -> date_taken LIKE '%2025%' AND (route_key='travel_nature' OR location_label IS NOT NULL)
    - "Find receipts from 2026" -> labels_json LIKE '%receipt%' AND date_taken LIKE '%2026%'
    - "Photos of Alice" -> p.display_name LIKE '%Alice%'
    """
    clean_query = query_text.strip().lower()
    conn = _get_db_conn()
    try:
        where_clauses: List[str] = []
        params: List[Any] = []
        intent_explanations: List[str] = []
        applied_filters: Dict[str, Any] = {}

        # 1. Year Extraction (e.g. 2023, 2024, 2025, 2026)
        year_match = re.search(r'\b(201\d|202\d)\b', clean_query)
        if year_match:
            year = year_match.group(1)
            where_clauses.append("(m.date_taken LIKE ? OR m.discovered_at LIKE ?)")
            params.extend([f"{year}%", f"{year}%"])
            intent_explanations.append(f"Filtered to year {year}")
            applied_filters["year"] = int(year)

        # 2. Category / Topic Intents
        if any(w in clean_query for w in ("trip", "trips", "travel", "vacation", "nature", "outdoor", "mountains", "beach")):
            where_clauses.append("(m.labels_json LIKE '%nature%' OR m.labels_json LIKE '%mountain%' OR m.labels_json LIKE '%beach%' OR t.route_key = 'travel_nature' OR (m.location_label IS NOT NULL AND m.location_label != ''))")
            intent_explanations.append("Identified travel & outdoor nature context")
            applied_filters["category"] = "travel_nature"

        if any(w in clean_query for w in ("receipt", "receipts", "invoice", "invoices", "bill", "bills", "tax", "taxes", "document", "documents")):
            where_clauses.append("(m.labels_json LIKE '%receipt%' OR m.labels_json LIKE '%invoice%' OR m.labels_json LIKE '%document%' OR t.route_key = 'screenshots_documents')")
            intent_explanations.append("Identified financial & document context")
            applied_filters["category"] = "documents"

        if any(w in clean_query for w in ("screenshot", "screenshots", "screen", "error")):
            where_clauses.append("(m.labels_json LIKE '%screenshot%' OR m.labels_json LIKE '%error%')")
            intent_explanations.append("Identified screenshot context")
            applied_filters["category"] = "screenshots"

        if any(w in clean_query for w in ("video", "videos", "clip", "movie")):
            where_clauses.append("m.media_type = 'video'")
            intent_explanations.append("Filtered for video media only")
            applied_filters["media_type"] = "video"

        # 3. People Name Matching
        has_face_tables = bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='people'").fetchone())
        if has_face_tables:
            known_people = conn.execute("SELECT person_id, display_name FROM people WHERE active = 1").fetchall()
            matched_people = []
            for p in known_people:
                first_name = p["display_name"].split()[0].lower()
                full_name = p["display_name"].lower()
                if first_name in clean_query or full_name in clean_query:
                    matched_people.append(p)

            if matched_people:
                person_clauses = []
                for p in matched_people:
                    person_clauses.append("""
                        p.person_id = ? AND mf.decision = 'KNOWN_MATCH' AND mf.attempt_id = (
                            SELECT attempt_id FROM face_analysis_attempts
                            WHERE media_id = m.id AND outcome = 'SUCCESS'
                            ORDER BY attempt_id DESC LIMIT 1
                        )
                    """)
                    params.append(p["person_id"])
                where_clauses.append(f"({' OR '.join(person_clauses)})")
                p_names = [p["display_name"] for p in matched_people]
                intent_explanations.append(f"Targeted recognized people: {', '.join(p_names)}")
                applied_filters["people"] = p_names

        # 4. Unknown Person Query
        if "unknown" in clean_query:
            where_clauses.append("""
                mf.decision != 'KNOWN_MATCH' AND mf.attempt_id = (
                    SELECT attempt_id FROM face_analysis_attempts
                    WHERE media_id = m.id AND outcome = 'SUCCESS'
                    ORDER BY attempt_id DESC LIMIT 1
                )
            """)
            intent_explanations.append("Filtered for unknown/unmatched faces")
            applied_filters["unknown_faces"] = True

        # Fallback if no specific structured rules matched
        if not where_clauses:
            # General keyword search
            clean_terms = [t for t in clean_query.split() if t not in ("show", "me", "find", "all", "the", "with", "in", "from", "of")]
            term_clauses = []
            for t in clean_terms:
                term_clauses.append("(m.original_filename LIKE ? OR m.labels_json LIKE ? OR m.location_label LIKE ?)")
                params.extend([f"%{t}%", f"%{t}%", f"%{t}%"])
            if term_clauses:
                where_clauses.append(f"({' AND '.join(term_clauses)})")
                intent_explanations.append(f"Applied general keyword matching for: {', '.join(clean_terms)}")
            else:
                intent_explanations.append("Showing recent archive records")

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        if has_face_tables:
            query_sql = f"""
                SELECT DISTINCT m.*, t.topic_id, t.preview_message_id, t.original_message_id, t.upload_confirmed_at, t.route_key
                FROM media m
                LEFT JOIN telegram_archive t ON m.id = t.media_id
                LEFT JOIN media_faces mf ON m.id = mf.media_id
                LEFT JOIN people p ON mf.best_person_id = p.person_id
                {where_sql}
                ORDER BY m.id DESC
                LIMIT 50
            """
        else:
            query_sql = f"""
                SELECT m.*, t.topic_id, t.preview_message_id, t.original_message_id, t.upload_confirmed_at, t.route_key
                FROM media m
                LEFT JOIN telegram_archive t ON m.id = t.media_id
                {where_sql}
                ORDER BY m.id DESC
                LIMIT 50
            """

        rows = conn.execute(query_sql, params).fetchall()

        results = []
        for r in rows:
            labels = _parse_labels(r["labels_json"])
            results.append({
                "id": r["id"],
                "original_filename": r["original_filename"],
                "short_hash": r["short_hash"],
                "media_type": r["media_type"],
                "status": r["state"],
                "date_taken": r["date_taken"],
                "location_label": r["location_label"] if "location_label" in r.keys() else None,
                "labels": labels,
                "topic_id": r["topic_id"],
                "preview_message_id": r["preview_message_id"],
                "original_message_id": r["original_message_id"]
            })

        explanation = ". ".join(intent_explanations) if intent_explanations else "Executed standard archive query."

        return {
            "query": query_text,
            "explanation": explanation,
            "applied_filters": applied_filters,
            "total_results": len(results),
            "results": results
        }
    finally:
        conn.close()


# ==============================================================================
# 3. SMART COLLECTIONS & ALBUMS
# ==============================================================================

def generate_smart_collections() -> List[Dict[str, Any]]:
    """
    Aggregates archive media into intelligent virtual collections:
    1. Trips & Adventures (GPS & Travel groupings)
    2. People Portfolios (Each recognized person)
    3. Document Vault (Receipts, Invoices, Screenshots)
    4. Yearly Retrospectives (2026, 2025 Highlights)
    5. Video Memories (All videos)
    """
    conn = _get_db_conn()
    try:
        collections: List[Dict[str, Any]] = []

        # 1. People Portfolios
        has_people_table = bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='people'").fetchone())
        if has_people_table:
            people_rows = conn.execute(
                """
                SELECT p.person_id, p.display_name, COUNT(DISTINCT mf.media_id) as photo_count, MAX(m.id) as cover_media_id
                FROM people p
                JOIN media_faces mf ON p.person_id = mf.best_person_id
                JOIN media m ON mf.media_id = m.id
                WHERE p.active = 1 AND mf.decision = 'KNOWN_MATCH'
                GROUP BY p.person_id, p.display_name
                HAVING photo_count > 0
                ORDER BY photo_count DESC
                """
            ).fetchall()

            for pr in people_rows:
                collections.append({
                    "id": f"person_{pr['person_id']}",
                    "title": pr["display_name"],
                    "category": "people",
                    "badge": f"{pr['photo_count']} Photos",
                    "description": f"All photos featuring {pr['display_name']}",
                    "count": pr["photo_count"],
                    "cover_media_id": pr["cover_media_id"]
                })

        # 2. Trips & Expeditions (Grouped by location_label)
        loc_rows = conn.execute(
            """
            SELECT location_label, COUNT(*) as count, MAX(id) as cover_media_id
            FROM media
            WHERE location_label IS NOT NULL AND location_label != ''
            GROUP BY location_label
            HAVING count > 0
            ORDER BY count DESC
            LIMIT 10
            """
        ).fetchall()

        for lr in loc_rows:
            collections.append({
                "id": f"loc_{abs(hash(lr['location_label'])) % 100000}",
                "title": lr["location_label"],
                "category": "trips",
                "badge": f"{lr['count']} Items",
                "description": f"Media captured at {lr['location_label']}",
                "count": lr["count"],
                "cover_media_id": lr["cover_media_id"],
                "filter_param": lr["location_label"]
            })

        # 3. Document Vault
        doc_count = conn.execute(
            "SELECT COUNT(*), MAX(id) FROM media WHERE labels_json LIKE '%receipt%' OR labels_json LIKE '%invoice%' OR labels_json LIKE '%document%'"
        ).fetchone()
        if doc_count and doc_count[0] > 0:
            collections.append({
                "id": "docs_vault",
                "title": "Receipts & Documents",
                "category": "documents",
                "badge": f"{doc_count[0]} Docs",
                "description": "Scanned documents, receipts, invoices, and financial records",
                "count": doc_count[0],
                "cover_media_id": doc_count[1]
            })

        # 4. Screenshots Vault
        shot_count = conn.execute(
            "SELECT COUNT(*), MAX(id) FROM media WHERE labels_json LIKE '%screenshot%'"
        ).fetchone()
        if shot_count and shot_count[0] > 0:
            collections.append({
                "id": "screenshots_vault",
                "title": "Technical Screenshots",
                "category": "screenshots",
                "badge": f"{shot_count[0]} Shots",
                "description": "App captures, error dialogs, and web screenshots",
                "count": shot_count[0],
                "cover_media_id": shot_count[1]
            })

        # 5. Videos Vault
        vid_count = conn.execute("SELECT COUNT(*), MAX(id) FROM media WHERE media_type = 'video'").fetchone()
        if vid_count and vid_count[0] > 0:
            collections.append({
                "id": "videos_vault",
                "title": "Video Memories",
                "category": "videos",
                "badge": f"{vid_count[0]} Videos",
                "description": "All video clips and recordings in archive",
                "count": vid_count[0],
                "cover_media_id": vid_count[1]
            })

        # 6. Yearly Retrospectives
        years = conn.execute(
            """
            SELECT SUBSTR(date_taken, 1, 4) as year, COUNT(*) as count, MAX(id) as cover_media_id
            FROM media
            WHERE date_taken IS NOT NULL AND date_taken != '' AND LENGTH(date_taken) >= 4
            GROUP BY year
            ORDER BY year DESC
            """
        ).fetchall()

        for yr in years:
            if yr["year"] and yr["year"].isdigit() and int(yr["year"]) >= 2000:
                collections.append({
                    "id": f"year_{yr['year']}",
                    "title": f"Year in Review: {yr['year']}",
                    "category": "timeline",
                    "badge": f"{yr['count']} Memories",
                    "description": f"Highlights and photos taken in {yr['year']}",
                    "count": yr["count"],
                    "cover_media_id": yr["cover_media_id"],
                    "filter_param": yr["year"]
                })

        return collections
    finally:
        conn.close()


def get_collection_items(collection_id: str) -> List[Dict[str, Any]]:
    """Retrieve all media records belonging to a smart collection."""
    conn = _get_db_conn()
    try:
        where_clause = ""
        params = []

        if collection_id.startswith("person_"):
            pid = int(collection_id.replace("person_", ""))
            where_clause = """
                m.id IN (
                    SELECT mf.media_id FROM media_faces mf
                    WHERE mf.best_person_id = ? AND mf.decision = 'KNOWN_MATCH'
                )
            """
            params.append(pid)
        elif collection_id.startswith("year_"):
            yr = collection_id.replace("year_", "")
            where_clause = "m.date_taken LIKE ?"
            params.append(f"{yr}%")
        elif collection_id == "docs_vault":
            where_clause = "(m.labels_json LIKE '%receipt%' OR m.labels_json LIKE '%invoice%' OR m.labels_json LIKE '%document%')"
        elif collection_id == "screenshots_vault":
            where_clause = "m.labels_json LIKE '%screenshot%'"
        elif collection_id == "videos_vault":
            where_clause = "m.media_type = 'video'"
        else:
            # Fallback
            where_clause = "1=1"

        rows = conn.execute(
            f"""
            SELECT m.*, t.topic_id, t.preview_message_id, t.original_message_id, t.upload_confirmed_at, t.route_key
            FROM media m
            LEFT JOIN telegram_archive t ON m.id = t.media_id
            WHERE {where_clause}
            ORDER BY m.id DESC
            """,
            params
        ).fetchall()

        items = []
        for r in rows:
            items.append({
                "id": r["id"],
                "original_filename": r["original_filename"],
                "short_hash": r["short_hash"],
                "media_type": r["media_type"],
                "status": r["state"],
                "date_taken": r["date_taken"],
                "location_label": r["location_label"] if "location_label" in r.keys() else None,
                "labels": _parse_labels(r["labels_json"]),
                "topic_id": r["topic_id"],
                "preview_message_id": r["preview_message_id"],
                "original_message_id": r["original_message_id"]
            })
        return items
    finally:
        conn.close()


# ==============================================================================
# 4. ARCHIVE ANALYTICS & INSIGHTS
# ==============================================================================

def get_archive_analytics() -> Dict[str, Any]:
    """Compute archive-wide intelligence metrics, category distributions, and timelines."""
    conn = _get_db_conn()
    try:
        # Media count by type
        total_media = conn.execute("SELECT COUNT(*) FROM media").fetchone()[0]
        total_bytes = conn.execute("SELECT COALESCE(SUM(size_bytes), 0) FROM media").fetchone()[0]
        images_cnt = conn.execute("SELECT COUNT(*) FROM media WHERE media_type = 'image'").fetchone()[0]
        videos_cnt = conn.execute("SELECT COUNT(*) FROM media WHERE media_type = 'video'").fetchone()[0]

        # People breakdown
        people_stats = []
        has_people_table = bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='people'").fetchone())
        if has_people_table:
            p_rows = conn.execute(
                """
                SELECT p.display_name, COUNT(DISTINCT mf.media_id) as count
                FROM people p
                JOIN media_faces mf ON p.person_id = mf.best_person_id
                WHERE p.active = 1 AND mf.decision = 'KNOWN_MATCH'
                GROUP BY p.person_id, p.display_name
                ORDER BY count DESC
                LIMIT 5
                """
            ).fetchall()
            people_stats = [{"name": r["display_name"], "count": r["count"]} for r in p_rows]

        # Top Scene Categories
        all_labels_rows = conn.execute("SELECT labels_json FROM media WHERE labels_json IS NOT NULL").fetchall()
        category_counts: Dict[str, int] = {
            "Nature & Outdoors": 0,
            "People & Portraits": 0,
            "Documents & Receipts": 0,
            "Screenshots & Tech": 0,
            "Everyday & Misc": 0,
        }
        for row in all_labels_rows:
            labs = _parse_labels(row[0])
            for l in labs:
                if any(k in l for k in ("mountain", "nature", "sky", "tree", "forest", "beach", "ocean", "landscape", "outdoor")):
                    category_counts["Nature & Outdoors"] += 1
                elif any(k in l for k in ("person", "people", "portrait", "face", "smile")):
                    category_counts["People & Portraits"] += 1
                elif any(k in l for k in ("receipt", "invoice", "document", "text", "bill", "tax")):
                    category_counts["Documents & Receipts"] += 1
                elif any(k in l for k in ("screenshot", "ui", "app", "window", "code", "browser")):
                    category_counts["Screenshots & Tech"] += 1
                else:
                    category_counts["Everyday & Misc"] += 1

        total_cat_tags = sum(category_counts.values()) or 1
        category_percentages = [
            {"category": k, "count": v, "percentage": round((v / total_cat_tags) * 100, 1)}
            for k, v in category_counts.items()
        ]

        # Locations breakdown
        loc_rows = conn.execute(
            """
            SELECT location_label, COUNT(*) as count
            FROM media
            WHERE location_label IS NOT NULL AND location_label != ''
            GROUP BY location_label
            ORDER BY count DESC
            LIMIT 5
            """
        ).fetchall()
        top_locations = [{"location": r["location_label"], "count": r["count"]} for r in loc_rows]

        # Monthly Activity Timeline
        timeline_rows = conn.execute(
            """
            SELECT SUBSTR(date_taken, 1, 7) as month_year, COUNT(*) as count
            FROM media
            WHERE date_taken IS NOT NULL AND date_taken != '' AND LENGTH(date_taken) >= 7
            GROUP BY month_year
            ORDER BY month_year ASC
            LIMIT 12
            """
        ).fetchall()
        timeline_activity = [{"period": r["month_year"], "count": r["count"]} for r in timeline_rows if r["month_year"]]

        return {
            "summary": {
                "total_media": total_media,
                "total_size_mb": round(total_bytes / (1024 * 1024), 2),
                "images_count": images_cnt,
                "videos_count": videos_cnt,
                "unique_people_count": len(people_stats),
                "unique_locations_count": len(top_locations)
            },
            "top_people": people_stats,
            "scene_distribution": category_percentages,
            "top_locations": top_locations,
            "timeline_activity": timeline_activity
        }
    finally:
        conn.close()
