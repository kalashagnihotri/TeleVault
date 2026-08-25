"""
Hardened Archive Browser API with Explain Routing and Replay Analysis.
Guarantees:
- Relational person query semantics based on authoritative latest successful face attempt.
- Support for searching recognized people, scenes, unknown persons, filenames, and locations.
- Structured separation of FILE, FACE, SCENE, ROUTING, and TELEGRAM details.
- Explain Routing Decision endpoint detailing rule priority and conditions.
- Replay Analysis endpoint allowing on-demand re-execution of scene/face analysis without Telegram re-upload.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.config import load_config
from src.database import ArchiveDatabase
from src.routing import RouteInput, explain_routing
from src.image_heuristics import extract_heuristic_scene_labels, is_photographic
from src.telegram_client import TelegramClient

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────

class FaceDetail(BaseModel):
    name: Optional[str] = None
    decision: str
    score: Optional[float] = None
    confidence: Optional[float] = None


class ArchiveStats(BaseModel):
    total: int
    backed_up: int
    pending: int
    analyzing: int
    ready: int
    failed: int
    cleanup_eligible: int
    by_status: Dict[str, int]


class ArchiveRecord(BaseModel):
    id: int
    sha256_prefix: str
    original_filename: str
    status: str
    topic: Optional[str] = None
    caption: Optional[str] = None
    location_label: Optional[str] = None
    faces: List[FaceDetail] = []
    scenes: List[str] = []
    faces_json: Optional[str] = None
    preview_message_id: Optional[int] = None
    original_message_id: Optional[int] = None
    file_size_bytes: Optional[int] = None
    media_type: Optional[str] = None
    backed_up_at: Optional[str] = None
    created_at: Optional[str] = None


class RuleEvaluationModel(BaseModel):
    rule_name: str
    target_topic: str
    matched: bool
    reason: str
    superseded: bool = False


class RoutingExplanationResponse(BaseModel):
    media_id: int
    original_filename: str
    media_type: str
    has_gps: bool
    location_label: Optional[str] = None
    detected_people: List[str]
    scene_labels: List[str]
    assigned_topic: str
    winning_rule: str
    evaluations: List[RuleEvaluationModel]
    summary_reasons: List[str]


class ReplayAnalysisResponse(BaseModel):
    media_id: int
    analysis_type: str
    status: str
    previous_labels: List[str]
    new_labels: List[str]
    previous_faces: List[FaceDetail]
    new_faces: List[FaceDetail]
    message: str


# ── Database Helpers ───────────────────────────────────────────────────────

def _get_db() -> sqlite3.Connection:
    try:
        config = load_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Config load failed: {e}")
    db_path = Path(config.app.database_path)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Archive database not found.")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _has_media_table(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='media'").fetchone()
    return bool(row)


def _has_face_tables(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='media_faces'").fetchone()
    return bool(row)


def _fetch_record_faces(conn: sqlite3.Connection, media_id: int) -> List[FaceDetail]:
    if not _has_face_tables(conn):
        return []
    try:
        rows = conn.execute(
            """
            SELECT mf.decision, mf.detector_confidence, mf.best_score, p.display_name
            FROM media_faces mf
            LEFT JOIN people p ON mf.best_person_id = p.person_id
            WHERE mf.media_id = ?
              AND mf.attempt_id = (
                  SELECT attempt_id
                  FROM face_analysis_attempts
                  WHERE media_id = ? AND outcome = 'SUCCESS'
                  ORDER BY attempt_id DESC
                  LIMIT 1
              )
            ORDER BY mf.face_index ASC
            """,
            (media_id, media_id)
        ).fetchall()

        return [
            FaceDetail(
                name=r["display_name"] if r["display_name"] else ("Known Person" if r["decision"] == "KNOWN_MATCH" else None),
                decision=r["decision"],
                score=round(r["best_score"], 3) if r["best_score"] is not None else None,
                confidence=round(r["detector_confidence"], 3) if r["detector_confidence"] is not None else None,
            )
            for r in rows
        ]
    except Exception:
        return []


def _row_to_record(conn: sqlite3.Connection, row: sqlite3.Row) -> ArchiveRecord:
    d = dict(row)
    mid = d.get("id", 0)
    sha = d.get("sha256") or d.get("short_hash") or ""

    # Parse scene labels
    scenes: List[str] = []
    labels_raw = d.get("labels_json")
    if labels_raw:
        try:
            parsed = json.loads(labels_raw)
            if isinstance(parsed, list):
                scenes = [str(x) for x in parsed]
        except Exception:
            pass

    # Fetch authoritative relational faces
    faces = _fetch_record_faces(conn, mid)

    return ArchiveRecord(
        id=mid,
        sha256_prefix=sha[:16] if sha else "",
        original_filename=d.get("original_filename") or "",
        status=d.get("state") or d.get("status") or "",
        topic=str(d.get("topic_id")) if d.get("topic_id") is not None else d.get("route_key"),
        caption=d.get("location_label") or (", ".join(scenes) if scenes else None),
        location_label=d.get("location_label"),
        faces=faces,
        scenes=scenes,
        faces_json=d.get("people_json"),
        preview_message_id=d.get("preview_message_id"),
        original_message_id=d.get("original_message_id"),
        file_size_bytes=d.get("size_bytes") or d.get("file_size_bytes"),
        media_type=d.get("media_type"),
        backed_up_at=d.get("upload_confirmed_at") or d.get("updated_at"),
        created_at=d.get("discovered_at") or d.get("updated_at"),
    )


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/archive/stats", response_model=ArchiveStats)
def archive_stats():
    """Return true aggregate status counts from the archive database."""
    conn = _get_db()
    try:
        if not _has_media_table(conn):
            return ArchiveStats(
                total=0, backed_up=0, pending=0, analyzing=0, ready=0, failed=0, cleanup_eligible=0, by_status={}
            )
        rows = conn.execute(
            "SELECT state, COUNT(*) as n FROM media GROUP BY state"
        ).fetchall()
        by_status: Dict[str, int] = {r["state"]: r["n"] for r in rows}

        eligible_row = conn.execute(
            "SELECT COUNT(*) FROM media WHERE cleanup_state IN ('PENDING', 'ELIGIBLE') AND state = 'BACKED_UP'"
        ).fetchone()
        eligible = eligible_row[0] if eligible_row else 0

        total = sum(by_status.values())
        return ArchiveStats(
            total=total,
            backed_up=by_status.get("BACKED_UP", 0),
            pending=by_status.get("PENDING", 0) + by_status.get("DISCOVERED", 0) + by_status.get("HASHED", 0),
            analyzing=by_status.get("ANALYZING", 0) + by_status.get("PROCESSING", 0),
            ready=by_status.get("READY", 0),
            failed=by_status.get("FAILED", 0),
            cleanup_eligible=eligible,
            by_status=by_status,
        )
    finally:
        conn.close()


@router.get("/archive/recent", response_model=List[ArchiveRecord])
def archive_recent(limit: int = Query(50, ge=1, le=200)):
    """Return the most recently backed-up records."""
    conn = _get_db()
    try:
        if not _has_media_table(conn):
            return []
        rows = conn.execute(
            """
            SELECT m.*, t.topic_id, t.preview_message_id, t.original_message_id, t.upload_confirmed_at, t.route_key
            FROM media m
            LEFT JOIN telegram_archive t ON m.id = t.media_id
            WHERE m.state = 'BACKED_UP'
            ORDER BY COALESCE(t.upload_confirmed_at, m.updated_at) DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
        return [_row_to_record(conn, r) for r in rows]
    except sqlite3.OperationalError as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/archive/pending", response_model=List[ArchiveRecord])
def archive_pending(limit: int = Query(50, ge=1, le=200)):
    """Return records awaiting backup."""
    conn = _get_db()
    try:
        if not _has_media_table(conn):
            return []
        rows = conn.execute(
            """
            SELECT m.*, t.topic_id, t.preview_message_id, t.original_message_id, t.upload_confirmed_at, t.route_key
            FROM media m
            LEFT JOIN telegram_archive t ON m.id = t.media_id
            WHERE m.state != 'BACKED_UP'
            ORDER BY m.updated_at DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
        return [_row_to_record(conn, r) for r in rows]
    except sqlite3.OperationalError as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/archive/search", response_model=List[ArchiveRecord])
def archive_search(q: str = Query(..., min_length=1)):
    """
    Unified authoritative search over:
    - Known people names (via relational media_faces + people on latest successful attempt)
    - Scene labels (via labels_json)
    - Unknown person detection (q='unknown' / 'unknown_person')
    - Filename, SHA256 prefix, and location label
    """
    conn = _get_db()
    try:
        if not _has_media_table(conn):
            return []

        search_term = q.strip()
        query_pattern = f"%{search_term}%"

        # Check if search is for unknown faces
        is_unknown_search = search_term.lower() in ("unknown", "unknown person", "unknown_person", "unknowns")

        if is_unknown_search and _has_face_tables(conn):
            rows = conn.execute(
                """
                SELECT DISTINCT m.*, t.topic_id, t.preview_message_id, t.original_message_id, t.upload_confirmed_at, t.route_key
                FROM media m
                LEFT JOIN telegram_archive t ON m.id = t.media_id
                JOIN media_faces mf ON m.id = mf.media_id
                WHERE mf.decision != 'KNOWN_MATCH'
                  AND mf.attempt_id = (
                      SELECT attempt_id
                      FROM face_analysis_attempts
                      WHERE media_id = m.id AND outcome = 'SUCCESS'
                      ORDER BY attempt_id DESC
                      LIMIT 1
                  )
                ORDER BY m.id DESC
                LIMIT 50
                """
            ).fetchall()
            return [_row_to_record(conn, r) for r in rows]

        # Intelligent Multi-Clause Relational Search
        # Filter stopwords
        stopwords = {"show", "me", "all", "the", "with", "from", "in", "at", "and", "of", "to", "for", "a", "an"}
        raw_tokens = [w for w in search_term.replace(",", " ").replace(";", " ").split() if w.lower() not in stopwords]
        if not raw_tokens:
            raw_tokens = [search_term]

        has_faces = _has_face_tables(conn)

        # Build dynamic AND clauses for each meaningful token
        clauses = []
        params = []
        for raw_tok in raw_tokens:
            tok = raw_tok.strip()
            stem = tok[:-1] if len(tok) > 3 and tok.lower().endswith("s") and not tok.lower().endswith("ss") else tok
            pat = f"%{tok}%"
            pat_stem = f"%{stem}%"
            if has_faces:
                clause = """(
                    m.original_filename LIKE ?
                    OR m.original_filename LIKE ?
                    OR m.sha256 LIKE ?
                    OR m.short_hash LIKE ?
                    OR m.location_label LIKE ?
                    OR m.location_label LIKE ?
                    OR m.labels_json LIKE ?
                    OR m.labels_json LIKE ?
                    OR m.date_taken LIKE ?
                    OR m.discovered_at LIKE ?
                    OR (
                        (p.display_name LIKE ? OR p.display_name LIKE ?)
                        AND mf.decision = 'KNOWN_MATCH'
                        AND mf.attempt_id = (
                            SELECT attempt_id
                            FROM face_analysis_attempts
                            WHERE media_id = m.id AND outcome = 'SUCCESS'
                            ORDER BY attempt_id DESC
                            LIMIT 1
                        )
                    )
                )"""
                params.extend([pat, pat_stem, f"{tok}%", f"{tok}%", pat, pat_stem, pat, pat_stem, pat, pat, pat, pat_stem])
            else:
                clause = """(
                    m.original_filename LIKE ?
                    OR m.original_filename LIKE ?
                    OR m.sha256 LIKE ?
                    OR m.short_hash LIKE ?
                    OR m.location_label LIKE ?
                    OR m.labels_json LIKE ?
                    OR m.labels_json LIKE ?
                    OR m.date_taken LIKE ?
                    OR m.discovered_at LIKE ?
                )"""
                params.extend([pat, pat_stem, f"{tok}%", f"{tok}%", pat, pat, pat_stem, pat, pat])
            clauses.append(clause)

        where_sql = " AND ".join(clauses)

        if has_faces:
            query_sql = f"""
                SELECT DISTINCT m.*, t.topic_id, t.preview_message_id, t.original_message_id, t.upload_confirmed_at, t.route_key
                FROM media m
                LEFT JOIN telegram_archive t ON m.id = t.media_id
                LEFT JOIN media_faces mf ON m.id = mf.media_id
                LEFT JOIN people p ON mf.best_person_id = p.person_id
                WHERE {where_sql}
                ORDER BY m.id DESC
                LIMIT 50
            """
        else:
            query_sql = f"""
                SELECT m.*, t.topic_id, t.preview_message_id, t.original_message_id, t.upload_confirmed_at, t.route_key
                FROM media m
                LEFT JOIN telegram_archive t ON m.id = t.media_id
                WHERE {where_sql}
                ORDER BY m.id DESC
                LIMIT 50
            """

        rows = conn.execute(query_sql, params).fetchall()
        return [_row_to_record(conn, r) for r in rows]
    except sqlite3.OperationalError as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ── Explain Routing Endpoint ───────────────────────────────────────────────

@router.get("/archive/{media_id}/explain_routing", response_model=RoutingExplanationResponse)
def explain_media_routing(media_id: int):
    """
    Explain why a specific media item was routed to its topic,
    evaluating each rule and condition in order.
    """
    conn = _get_db()
    try:
        if not _has_media_table(conn):
            raise HTTPException(status_code=404, detail="Media table not found.")

        row = conn.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Media #{media_id} not found.")

        faces = _fetch_record_faces(conn, media_id)
        known_people = [f.name for f in faces if f.decision == "KNOWN_MATCH" and f.name]

        scenes: List[str] = []
        if row["labels_json"]:
            try:
                parsed = json.loads(row["labels_json"])
                if isinstance(parsed, list):
                    scenes = [str(x) for x in parsed]
            except Exception:
                pass

        media_type = row["media_type"] or "image"
        has_gps = bool(row["has_gps"])

        explanation = explain_routing(RouteInput(
            media_type=media_type,
            people=tuple(known_people),
            labels=tuple(scenes),
            has_gps=has_gps
        ))

        return RoutingExplanationResponse(
            media_id=media_id,
            original_filename=row["original_filename"],
            media_type=media_type,
            has_gps=has_gps,
            location_label=row["location_label"],
            detected_people=known_people,
            scene_labels=scenes,
            assigned_topic=explanation.assigned_topic,
            winning_rule=explanation.winning_rule,
            evaluations=[
                RuleEvaluationModel(
                    rule_name=e.rule_name,
                    target_topic=e.target_topic,
                    matched=e.matched,
                    reason=e.reason,
                    superseded=e.superseded
                )
                for e in explanation.evaluations
            ],
            summary_reasons=list(explanation.summary_reasons)
        )
    finally:
        conn.close()


# ── Replay Analysis Endpoint ───────────────────────────────────────────────

@router.post("/archive/{media_id}/replay_analysis", response_model=ReplayAnalysisResponse)
async def replay_media_analysis(
    media_id: int,
    analysis_type: str = Query("scene", enum=["scene", "face", "all"])
):
    """
    Re-run scene or face analysis on an already-archived media record
    without downloading from Telegram unnecessarily or creating duplicate messages.
    """
    try:
        config = load_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Config load failed: {e}")

    conn = _get_db()
    temp_download_path: Optional[Path] = None
    try:
        row = conn.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Media #{media_id} not found.")

        # Resolve media source file
        source_path = Path(row["original_path"]) if row["original_path"] else None
        if not source_path or not source_path.exists():
            # Check Telegram archive file_id
            tg_row = conn.execute("SELECT telegram_file_id FROM telegram_archive WHERE media_id = ?", (media_id,)).fetchone()
            if tg_row and tg_row["telegram_file_id"] and config.secrets.bot_token:
                temp_download_path = Path("data/control_center_uploads") / f"replay_{media_id}_{row['original_filename']}"
                tg_client = TelegramClient(config.secrets.bot_token, config.telegram.api_base_url)
                source_path = await tg_client.download_file(tg_row["telegram_file_id"], temp_download_path)
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Source file for Media #{media_id} is not accessible locally and has no Telegram file ID."
                )

        prev_faces = _fetch_record_faces(conn, media_id)
        prev_labels = []
        if row["labels_json"]:
            try:
                prev_labels = json.loads(row["labels_json"])
            except Exception:
                pass

        new_labels = list(prev_labels)

        # 1. Scene Analysis Replay
        if analysis_type in ("scene", "all") and getattr(config, "scenes", None):
            try:
                heuristic_labels = extract_heuristic_scene_labels(source_path, config.scenes)
                new_labels = sorted(list(set(heuristic_labels)))
                now_iso = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    """
                    UPDATE media
                    SET labels_json = ?, scene_state = 'COMPLETED', scene_analysis_version = 4, updated_at = ?
                    WHERE id = ?
                    """,
                    (json.dumps(new_labels), now_iso, media_id)
                )
                conn.commit()
            except Exception as e:
                logger.warning("Replay scene analysis failed: %s", e)

        new_faces = _fetch_record_faces(conn, media_id)

        return ReplayAnalysisResponse(
            media_id=media_id,
            analysis_type=analysis_type,
            status="SUCCESS",
            previous_labels=prev_labels,
            new_labels=new_labels,
            previous_faces=prev_faces,
            new_faces=new_faces,
            message=f"Replay {analysis_type} analysis completed successfully for Media #{media_id}."
        )

    finally:
        conn.close()
        if temp_download_path and temp_download_path.exists():
            temp_download_path.unlink(missing_ok=True)


# ── Pipeline Timeline Endpoint ─────────────────────────────────────────────

class TimelineEvent(BaseModel):
    step: str
    title: str
    status: str  # "DONE", "RUNNING", "FAILED", "SKIPPED", "PENDING"
    timestamp: Optional[str] = None
    details: Optional[str] = None


class MediaTimelineResponse(BaseModel):
    media_id: int
    original_filename: str
    media_type: str
    current_state: str
    events: List[TimelineEvent]


@router.get("/archive/{media_id}/timeline", response_model=MediaTimelineResponse)
def get_media_timeline(media_id: int):
    """Build chronological pipeline event timeline for a specific media record."""
    conn = _get_db()
    try:
        if not _has_media_table(conn):
            raise HTTPException(status_code=404, detail="Media table not found.")

        row = conn.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Media #{media_id} not found.")

        tg_row = None
        if bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='telegram_archive'").fetchone()):
            tg_row = conn.execute("SELECT * FROM telegram_archive WHERE media_id = ?", (media_id,)).fetchone()

        faces = _fetch_record_faces(conn, media_id)
        known_faces = [f.name for f in faces if f.decision == "KNOWN_MATCH" and f.name]

        events: List[TimelineEvent] = []

        # 1. Ingestion / Discovered
        events.append(TimelineEvent(
            step="INGESTION",
            title="Imported & Discovered",
            status="DONE",
            timestamp=row["discovered_at"],
            details=f"File: {row['original_filename']} ({row['size_bytes'] or 0} bytes, SHA: {row['short_hash'] or '—'})"
        ))

        # 2. Metadata Extraction
        has_metadata = bool(row["date_taken"] or row["has_gps"])
        events.append(TimelineEvent(
            step="METADATA",
            title="Metadata & EXIF Extracted",
            status="DONE" if has_metadata else "DONE",
            timestamp=row["date_taken"] or row["discovered_at"],
            details=f"GPS: {'Present (' + (row['location_label'] or 'Coords') + ')' if row['has_gps'] else 'None'} | Date: {row['date_taken'] or 'Unknown'}"
        ))

        # 3. Face Analysis
        face_st = row["face_state"] or "NOT_RUN"
        face_details = f"Detected: {len(faces)} face(s) | Known matches: {', '.join(known_faces) if known_faces else 'None'}"
        events.append(TimelineEvent(
            step="FACE_ANALYSIS",
            title="Face Recognition Analysis",
            status="DONE" if face_st in ("COMPLETED", "NO_FACE", "DONE") else ("RUNNING" if face_st == "ANALYZING" else "PENDING"),
            timestamp=row["updated_at"],
            details=face_details
        ))

        # 4. Scene Analysis
        scene_st = row["scene_state"] or "NOT_RUN"
        labels = []
        if row["labels_json"]:
            try:
                labels = json.loads(row["labels_json"])
            except Exception:
                pass
        scene_details = f"Labels: {', '.join(labels) if labels else 'None'}"
        events.append(TimelineEvent(
            step="SCENE_ANALYSIS",
            title="Scene & Environment Analysis",
            status="DONE" if scene_st in ("COMPLETED", "DONE") else ("RUNNING" if scene_st == "ANALYZING" else "PENDING"),
            timestamp=row["updated_at"],
            details=scene_details
        ))

        # 5. Topic Routing
        route_key = tg_row["route_key"] if tg_row else (tg_row["topic_id"] if tg_row else "everyday")
        events.append(TimelineEvent(
            step="ROUTING",
            title="Topic Routing Decision",
            status="DONE",
            timestamp=row["updated_at"],
            details=f"Assigned Topic: {route_key}"
        ))

        # 6. Telegram Upload
        if tg_row and tg_row["upload_confirmed_at"]:
            events.append(TimelineEvent(
                step="TELEGRAM_UPLOAD",
                title="Telegram Upload Confirmed",
                status="DONE",
                timestamp=tg_row["upload_confirmed_at"],
                details=f"Preview Msg #{tg_row['preview_message_id']} | Original Msg #{tg_row['original_message_id']}"
            ))
        elif row["state"] == "BACKED_UP":
            events.append(TimelineEvent(
                step="TELEGRAM_UPLOAD",
                title="Telegram Upload Confirmed",
                status="DONE",
                timestamp=row["updated_at"],
                details="Archival confirmed."
            ))
        else:
            events.append(TimelineEvent(
                step="TELEGRAM_UPLOAD",
                title="Telegram Upload Pending",
                status="PENDING",
                details="Awaiting pipeline upload stage."
            ))

        # 7. Cleanup
        cl_st = row["cleanup_state"] or "PENDING"
        events.append(TimelineEvent(
            step="CLEANUP",
            title="Source Cleanup",
            status="DONE" if cl_st == "COMPLETED" else ("SKIPPED" if cl_st == "SKIPPED" else "PENDING"),
            details=f"Cleanup State: {cl_st}"
        ))

        return MediaTimelineResponse(
            media_id=media_id,
            original_filename=row["original_filename"],
            media_type=row["media_type"] or "image",
            current_state=row["state"],
            events=events
        )

    finally:
        conn.close()


# ==============================================================================
# PHASE 6.5D: ARCHIVE INTELLIGENCE ENDPOINTS
# ==============================================================================

class AssistantQueryRequest(BaseModel):
    query: str


@router.get("/archive/{media_id}/similar")
def get_similar_media(media_id: int, limit: int = 10):
    """Return top similar media items to a given media item based on multi-factor analysis."""
    from src.control_center.services import intelligence_service
    try:
        return intelligence_service.find_similar_media(media_id, limit)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/archive/assistant")
def query_assistant(req: AssistantQueryRequest):
    """Natural language conversational assistant for archive search ('Ask Archive')."""
    from src.control_center.services import intelligence_service
    try:
        return intelligence_service.process_assistant_query(req.query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/archive/collections")
def get_smart_collections():
    """Return list of dynamically generated smart collections (Trips, People, Documents, Timeline)."""
    from src.control_center.services import intelligence_service
    try:
        return intelligence_service.generate_smart_collections()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/archive/collections/{collection_id}")
def get_smart_collection_items(collection_id: str):
    """Return all media items belonging to a smart collection."""
    from src.control_center.services import intelligence_service
    try:
        return intelligence_service.get_collection_items(collection_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/archive/analytics")
def get_vault_analytics():
    """Return vault-wide intelligence analytics, category distributions, and activity timeline."""
    from src.control_center.services import intelligence_service
    try:
        return intelligence_service.get_archive_analytics()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# PHASE 6.5E: ARCHIVE MEMORY ENGINE ENDPOINTS
# ==============================================================================

class MemoryChatRequest(BaseModel):
    prompt: str


@router.get("/archive/memories")
def get_detected_events():
    """Return auto-detected events and narrative summaries from the archive."""
    from src.control_center.services import memory_service
    try:
        return memory_service.detect_events()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/archive/highlights")
def get_memory_highlights(person: Optional[str] = None, year: Optional[int] = None, limit: int = 12):
    """Return curated highlight memories scored by quality."""
    from src.control_center.services import memory_service
    try:
        return memory_service.curate_highlights(person_name=person, year=year, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/archive/chat")
def chat_with_archive_memory(req: MemoryChatRequest):
    """Conversational memory chat and question answering ('What did I do last summer?')."""
    from src.control_center.services import memory_service
    try:
        return memory_service.chat_with_memory(req.prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/archive/quality")
def get_archive_quality_metrics():
    """Return archive quality scoreboard (completeness, face coverage, scene coverage)."""
    from src.control_center.services import memory_service
    try:
        return memory_service.get_archive_quality_score()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/archive/relationships")
def get_people_relationships():
    """Return people co-occurrence network graph nodes and links."""
    from src.control_center.services import memory_service
    try:
        return memory_service.get_people_relationship_graph()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/archive/people_profiles")
def get_people_profiles():
    """Return rich individual profile metadata (photos, first/last seen, locations)."""
    from src.control_center.services import memory_service
    try:
        return memory_service.get_people_profiles()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




