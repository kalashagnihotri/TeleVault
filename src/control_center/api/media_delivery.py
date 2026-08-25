from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from src.control_center.services import thumbnail_service

router = APIRouter()


@router.get("/media/{media_id}/thumbnail")
def get_media_thumbnail(media_id: int):
    """Serve 120px cached thumbnail."""
    path = thumbnail_service.generate_thumbnail(media_id, mode="thumbnail")
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(path, media_type="image/webp")


@router.get("/media/{media_id}/preview")
def get_media_preview(media_id: int):
    """Serve 600px cached preview."""
    path = thumbnail_service.generate_thumbnail(media_id, mode="preview")
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Preview not found")
    return FileResponse(path, media_type="image/webp")


@router.get("/media/{media_id}/raw")
def get_media_raw(media_id: int):
    """Serve original media file if present on disk."""
    path = thumbnail_service.get_media_path(media_id)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Original media not locally present on disk.")
    return FileResponse(path)
