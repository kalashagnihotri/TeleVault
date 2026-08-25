"""
Hardened Queue Ingestion API with Import History and Pipeline Status.
Guarantees:
- Persistent import history in control_center.sqlite3.
- Staging in data/control_center_uploads/ (never writes directly into Incoming).
- Chunked streaming for large files without reading entire payload into RAM.
- Real content validation (Pillow image verification + container signature checks).
- Exact SHA-256 duplicate detection against archive DB and current Incoming queue.
- Temporary destination naming (.<uuid>.controlcenter-part).
- Destination copy byte count + SHA-256 verification before atomic os.replace.
- Non-destructive filename collision handling for distinct hashes.
- Clean failure isolation and artifact removal.
- Pipeline status enrichment in GET /api/queue/status.
- Paginated import history endpoint: GET /api/queue/imports.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from PIL import Image
from pydantic import BaseModel

from src.config import load_config
from src.control_center.services import db_service
from src.hashing import sha256_file

logger = logging.getLogger(__name__)
router = APIRouter()

STAGING_DIR = Path("data/control_center_uploads")
STAGING_DIR.mkdir(parents=True, exist_ok=True)
CHUNK_SIZE = 1024 * 1024  # 1 MiB chunks

ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}


# ── Schemas ────────────────────────────────────────────────────────────────

class IngestResult(BaseModel):
    filename: str
    original_filename: str
    status: str  # "IMPORT_COMPLETE", "ARCHIVE_DUPLICATE", "QUEUE_DUPLICATE", "INVALID_MEDIA", "IMPORT_FAILED"
    size_bytes: Optional[int] = None
    sha256_prefix: Optional[str] = None
    destination: Optional[str] = None
    error: Optional[str] = None
    existing_media_id: Optional[int] = None
    existing_state: Optional[str] = None
    existing_route: Optional[str] = None
    existing_preview_id: Optional[int] = None
    existing_original_id: Optional[int] = None


class ImportRecord(BaseModel):
    id: str
    filename: str
    original_filename: str
    sha256: Optional[str] = None
    size_bytes: Optional[int] = None
    media_type: Optional[str] = None
    status: str
    created_at: str
    completed_at: Optional[str] = None
    destination: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class QueueFileInfo(BaseModel):
    filename: str
    media_type: str
    size_bytes: int
    modified_at: str
    pipeline_status: str = "WAITING"  # WAITING, DISCOVERED, ANALYZING, READY, UPLOADING, BACKED_UP


class QueueStatusResult(BaseModel):
    images: int
    videos: int
    image_files: List[QueueFileInfo]
    video_files: List[QueueFileInfo]


# ── Validation Helpers ─────────────────────────────────────────────────────

def _sanitize_filename(name: str) -> str:
    cleaned = Path(name).name
    cleaned = re.sub(r'[^\w\.\-\_]', '_', cleaned)
    return cleaned or "unnamed_media"


def _classify_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in ALLOWED_IMAGE_EXTS:
        return "image"
    if ext in ALLOWED_VIDEO_EXTS:
        return "video"
    return "unknown"


def _validate_image_content(file_path: Path) -> tuple[bool, str]:
    try:
        with Image.open(file_path) as img:
            img.verify()
            fmt = (img.format or "").upper()
            if fmt not in ("JPEG", "PNG", "WEBP", "MPO", "HEIF", "HEIC", "BMP", "GIF"):
                return False, f"Unsupported image container format: {fmt}"
            w, h = img.size
            if w <= 0 or h <= 0:
                return False, f"Invalid image dimensions: {w}x{h}"
        return True, ""
    except Exception as e:
        return False, f"Corrupt or spoofed image: {e}"


def _validate_video_content(file_path: Path) -> tuple[bool, str]:
    try:
        size = file_path.stat().st_size
        if size < 16:
            return False, "Video file too small to contain a valid container header"

        with open(file_path, "rb") as vf:
            header = vf.read(64)

        if len(header) >= 8 and (
            header[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip")
            or header[0:4] in (b"moov", b"mdat")
        ):
            return True, ""

        if header.startswith(b"\x1a\x45\xdf\xa3"):
            return True, ""

        if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"AVI ":
            return True, ""

        return False, "Unrecognized video container signature"
    except Exception as e:
        return False, f"Error validating video header: {e}"


def _validate_media(file_path: Path, media_type: str) -> tuple[bool, str]:
    if media_type == "image":
        return _validate_image_content(file_path)
    elif media_type == "video":
        return _validate_video_content(file_path)
    return False, f"Unsupported media type: {media_type}"


# ── Ingestion Endpoints ────────────────────────────────────────────────────

@router.post("/queue/ingest", response_model=List[IngestResult])
async def ingest_files(files: List[UploadFile] = File(...)):
    """
    Safely ingest uploaded media into the incoming queue using staging,
    chunked streaming, real content validation, exact SHA-256 duplicate checking,
    destination verification, and atomic rename.
    Records operational lifecycle in control_center.sqlite3 imports table.
    """
    try:
        config = load_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Configuration load failed: {e}")

    img_dir = Path(config.queue.incoming_images)
    vid_dir = Path(config.queue.incoming_videos)
    img_dir.mkdir(parents=True, exist_ok=True)
    vid_dir.mkdir(parents=True, exist_ok=True)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    db_path = Path(config.app.database_path)
    results: List[IngestResult] = []

    for upload in files:
        raw_name = upload.filename or "unnamed_media"
        safe_name = _sanitize_filename(raw_name)
        media_type = _classify_extension(safe_name)
        import_id = f"imp-{uuid4().hex[:8]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        # Record initial import staging record
        db_service.save_import({
            "id": import_id,
            "filename": safe_name,
            "original_filename": raw_name,
            "media_type": media_type,
            "status": "STAGED",
            "created_at": now_iso
        })

        if media_type == "unknown":
            err_msg = f"Unsupported file extension: {Path(safe_name).suffix}. Allowed images: {sorted(ALLOWED_IMAGE_EXTS)}, videos: {sorted(ALLOWED_VIDEO_EXTS)}"
            db_service.save_import({
                "id": import_id,
                "filename": safe_name,
                "original_filename": raw_name,
                "media_type": "unknown",
                "status": "INVALID_MEDIA",
                "created_at": now_iso,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error_code": "UNSUPPORTED_EXTENSION",
                "error_message": err_msg
            })
            results.append(IngestResult(
                filename=safe_name,
                original_filename=raw_name,
                status="INVALID_MEDIA",
                error=err_msg
            ))
            continue

        staging_path = STAGING_DIR / f"{uuid4().hex}_{safe_name}.staging"
        hasher = hashlib.sha256()
        total_bytes = 0

        # Step 1: Chunked streaming upload to staging file
        try:
            with open(staging_path, "wb") as sf:
                while True:
                    chunk = await upload.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    sf.write(chunk)
                    hasher.update(chunk)
                    total_bytes += len(chunk)
        except Exception as e:
            staging_path.unlink(missing_ok=True)
            logger.warning("Upload staging failed for %s: %s", raw_name, e)
            db_service.save_import({
                "id": import_id,
                "filename": safe_name,
                "original_filename": raw_name,
                "media_type": media_type,
                "status": "FAILED",
                "created_at": now_iso,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error_code": "UPLOAD_INTERRUPTED",
                "error_message": str(e)
            })
            results.append(IngestResult(
                filename=safe_name,
                original_filename=raw_name,
                status="IMPORT_FAILED",
                error=f"Upload stream interrupted: {e}"
            ))
            continue

        full_sha256 = hasher.hexdigest()
        sha_prefix = full_sha256[:16]

        # Step 2: Media content validation
        valid, val_err = _validate_media(staging_path, media_type)
        if not valid:
            staging_path.unlink(missing_ok=True)
            logger.warning("Media validation rejected %s: %s", raw_name, val_err)
            db_service.save_import({
                "id": import_id,
                "filename": safe_name,
                "original_filename": raw_name,
                "sha256": full_sha256,
                "size_bytes": total_bytes,
                "media_type": media_type,
                "status": "INVALID_MEDIA",
                "created_at": now_iso,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error_code": "VALIDATION_FAILED",
                "error_message": val_err
            })
            results.append(IngestResult(
                filename=safe_name,
                original_filename=raw_name,
                status="INVALID_MEDIA",
                size_bytes=total_bytes,
                sha256_prefix=sha_prefix,
                error=val_err
            ))
            continue

        # Step 3: Exact duplicate check against archive DB
        is_archive_dup = False
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                has_media = bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='media'").fetchone())
                if has_media:
                    row = conn.execute(
                        """
                        SELECT m.id, m.state, m.original_filename, t.topic_id, t.preview_message_id, t.original_message_id, t.route_key
                        FROM media m
                        LEFT JOIN telegram_archive t ON m.id = t.media_id
                        WHERE m.sha256 = ?
                        LIMIT 1
                        """,
                        (full_sha256,)
                    ).fetchone()
                    if row:
                        is_archive_dup = True
                        staging_path.unlink(missing_ok=True)
                        logger.info("Exact archive duplicate detected for %s: Media ID=%s, SHA=%s", raw_name, row["id"], sha_prefix)
                        db_service.save_import({
                            "id": import_id,
                            "filename": safe_name,
                            "original_filename": raw_name,
                            "sha256": full_sha256,
                            "size_bytes": total_bytes,
                            "media_type": media_type,
                            "status": "DUPLICATE",
                            "created_at": now_iso,
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                            "error_code": "ARCHIVE_DUPLICATE",
                            "error_message": f"Exact duplicate of archived Media #{row['id']}"
                        })
                        results.append(IngestResult(
                            filename=safe_name,
                            original_filename=raw_name,
                            status="ARCHIVE_DUPLICATE",
                            size_bytes=total_bytes,
                            sha256_prefix=sha_prefix,
                            existing_media_id=row["id"],
                            existing_state=row["state"],
                            existing_route=str(row["topic_id"]) if row["topic_id"] is not None else row["route_key"],
                            existing_preview_id=row["preview_message_id"],
                            existing_original_id=row["original_message_id"],
                        ))
                conn.close()
            except Exception as e:
                logger.warning("DB duplicate check encountered error: %s", e)

        if is_archive_dup:
            continue

        # Step 4: Exact duplicate check against current Incoming queue
        dest_dir = img_dir if media_type == "image" else vid_dir
        is_queue_dup = False
        try:
            for qf in dest_dir.iterdir():
                if qf.is_file() and not qf.name.startswith("."):
                    if qf.stat().st_size == total_bytes:
                        if sha256_file(qf) == full_sha256:
                            is_queue_dup = True
                            staging_path.unlink(missing_ok=True)
                            logger.info("Exact queue duplicate detected for %s in %s", raw_name, qf.name)
                            db_service.save_import({
                                "id": import_id,
                                "filename": qf.name,
                                "original_filename": raw_name,
                                "sha256": full_sha256,
                                "size_bytes": total_bytes,
                                "media_type": media_type,
                                "status": "DUPLICATE",
                                "created_at": now_iso,
                                "completed_at": datetime.now(timezone.utc).isoformat(),
                                "destination": str(qf),
                                "error_code": "QUEUE_DUPLICATE",
                                "error_message": f"Exact duplicate already waiting in queue as {qf.name}"
                            })
                            results.append(IngestResult(
                                filename=qf.name,
                                original_filename=raw_name,
                                status="QUEUE_DUPLICATE",
                                size_bytes=total_bytes,
                                sha256_prefix=sha_prefix,
                                destination=str(qf),
                            ))
                            break
        except Exception as e:
            logger.warning("Queue duplicate scan encountered error: %s", e)

        if is_queue_dup:
            continue

        # Step 5: Filename collision resolution for distinct content
        target_name = safe_name
        stem = Path(safe_name).stem
        suffix = Path(safe_name).suffix
        counter = 1
        while (dest_dir / target_name).exists():
            target_name = f"{stem}_{counter}{suffix}"
            counter += 1

        # Step 6: Copy to destination temporary file and verify
        temp_dest = dest_dir / f".{uuid4().hex}.controlcenter-part"
        try:
            dest_hasher = hashlib.sha256()
            dest_bytes = 0
            with open(staging_path, "rb") as sf, open(temp_dest, "wb") as df:
                while True:
                    c = sf.read(CHUNK_SIZE)
                    if not c:
                        break
                    df.write(c)
                    dest_hasher.update(c)
                    dest_bytes += len(c)

            # Step 7: Destination verification
            if dest_bytes != total_bytes or dest_hasher.hexdigest() != full_sha256:
                temp_dest.unlink(missing_ok=True)
                staging_path.unlink(missing_ok=True)
                logger.error("Destination verification failed for %s: byte/hash mismatch", raw_name)
                db_service.save_import({
                    "id": import_id,
                    "filename": safe_name,
                    "original_filename": raw_name,
                    "sha256": full_sha256,
                    "size_bytes": total_bytes,
                    "media_type": media_type,
                    "status": "FAILED",
                    "created_at": now_iso,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "error_code": "VERIFICATION_FAILED",
                    "error_message": "Destination copy failed SHA-256 verification"
                })
                results.append(IngestResult(
                    filename=safe_name,
                    original_filename=raw_name,
                    status="IMPORT_FAILED",
                    error="Destination copy SHA-256 verification failed"
                ))
                continue

            # Step 8: Atomic rename into final Incoming location
            final_dest = dest_dir / target_name
            os.replace(temp_dest, final_dest)
            staging_path.unlink(missing_ok=True)

            logger.info("Successfully ingested %s -> %s (SHA: %s...)", raw_name, final_dest, sha_prefix)
            db_service.save_import({
                "id": import_id,
                "filename": target_name,
                "original_filename": raw_name,
                "sha256": full_sha256,
                "size_bytes": total_bytes,
                "media_type": media_type,
                "status": "COMPLETE",
                "created_at": now_iso,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "destination": str(final_dest)
            })
            results.append(IngestResult(
                filename=target_name,
                original_filename=raw_name,
                status="IMPORT_COMPLETE",
                size_bytes=total_bytes,
                sha256_prefix=sha_prefix,
                destination=str(final_dest)
            ))

        except Exception as e:
            temp_dest.unlink(missing_ok=True)
            staging_path.unlink(missing_ok=True)
            logger.error("Destination copy failed for %s: %s", raw_name, e)
            db_service.save_import({
                "id": import_id,
                "filename": safe_name,
                "original_filename": raw_name,
                "sha256": full_sha256,
                "size_bytes": total_bytes,
                "media_type": media_type,
                "status": "FAILED",
                "created_at": now_iso,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error_code": "COPY_FAILED",
                "error_message": str(e)
            })
            results.append(IngestResult(
                filename=safe_name,
                original_filename=raw_name,
                status="IMPORT_FAILED",
                error=f"Destination copy failed: {e}"
            ))

    return results


# ── Import History Endpoint ────────────────────────────────────────────────

@router.get("/queue/imports", response_model=List[ImportRecord])
def get_import_history(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    """Return historical imports performed through Control Center."""
    rows = db_service.get_all_imports(limit=limit, offset=offset)
    return [
        ImportRecord(
            id=r["id"],
            filename=r["filename"],
            original_filename=r["original_filename"],
            sha256=r.get("sha256"),
            size_bytes=r.get("size_bytes"),
            media_type=r.get("media_type"),
            status=r["status"],
            created_at=r["created_at"],
            completed_at=r.get("completed_at"),
            destination=r.get("destination"),
            error_code=r.get("error_code"),
            error_message=r.get("error_message")
        )
        for r in rows
    ]


# ── Queue Status Endpoint ──────────────────────────────────────────────────

@router.get("/queue/status", response_model=QueueStatusResult)
def queue_status():
    """Return enriched stat-based metadata and pipeline status for files currently in Incoming paths."""
    try:
        config = load_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Configuration load failed: {e}")

    img_dir = Path(config.queue.incoming_images)
    vid_dir = Path(config.queue.incoming_videos)
    db_path = Path(config.app.database_path)

    # Pre-fetch known media states indexed by filename for fast matching
    media_state_by_name = {}
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            if bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='media'").fetchone()):
                rows = conn.execute("SELECT original_filename, state, face_state, scene_state FROM media").fetchall()
                for r in rows:
                    st = r["state"]
                    # If state is RESERVED or READY, check fine-grained stage
                    if st in ("RESERVED", "READY_TO_UPLOAD", "READY"):
                        if r["face_state"] == "ANALYZING" or r["scene_state"] == "ANALYZING":
                            st = "ANALYZING"
                        else:
                            st = "READY"
                    media_state_by_name[r["original_filename"]] = st
            conn.close()
        except Exception:
            pass

    def _get_file_info_list(d: Path, media_type: str) -> List[QueueFileInfo]:
        if not d.exists():
            return []
        items: List[QueueFileInfo] = []
        for f in sorted(d.iterdir()):
            if f.is_file() and not f.name.startswith("."):
                try:
                    st = f.stat()
                    mod_iso = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
                    pipe_status = media_state_by_name.get(f.name, "WAITING")
                    items.append(QueueFileInfo(
                        filename=f.name,
                        media_type=media_type,
                        size_bytes=st.st_size,
                        modified_at=mod_iso,
                        pipeline_status=pipe_status
                    ))
                except Exception:
                    pass
        return items

    imgs = _get_file_info_list(img_dir, "image")
    vids = _get_file_info_list(vid_dir, "video")

    return QueueStatusResult(
        images=len(imgs),
        videos=len(vids),
        image_files=imgs[:100],
        video_files=vids[:100],
    )


class QueueActionRequest(BaseModel):
    action: str  # "retry", "delete", "move", "cancel"
    filename: str
    media_type: str = "image"
    target_folder: Optional[str] = None


@router.post("/queue/action")
def perform_queue_action(req: QueueActionRequest):
    """Perform manual queue control action: retry, delete, move, or cancel."""
    try:
        config = load_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Configuration load failed: {e}")

    img_dir = Path(config.queue.incoming_images)
    vid_dir = Path(config.queue.incoming_videos)
    failed_dir = Path(config.queue.failed)
    
    src_dir = img_dir if req.media_type == "image" else vid_dir
    file_path = src_dir / req.filename
    if not file_path.exists():
        # Check failed directory
        file_path = failed_dir / req.filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Queue file '{req.filename}' not found.")

    if req.action == "delete":
        file_path.unlink()
        return {"status": "success", "message": f"Deleted '{req.filename}' from queue."}
    elif req.action == "retry":
        target = img_dir / req.filename if req.media_type == "image" else vid_dir / req.filename
        if file_path != target:
            shutil.move(str(file_path), str(target))
        return {"status": "success", "message": f"Moved '{req.filename}' to incoming queue for retry."}
    elif req.action == "cancel" or req.action == "move":
        target_dir = failed_dir if req.action == "cancel" else Path(req.target_folder or str(failed_dir))
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(file_path), str(target_dir / req.filename))
        return {"status": "success", "message": f"Moved '{req.filename}' to {target_dir.name}."}
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action '{req.action}'.")

