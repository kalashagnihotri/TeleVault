import os
import sqlite3
import logging
from typing import Optional
from pathlib import Path
from PIL import Image
from src.config import load_config

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/media_cache")
THUMBNAIL_DIR = CACHE_DIR / "thumbnails"
PREVIEW_DIR = CACHE_DIR / "previews"


def _ensure_cache_dirs():
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


def _get_db_conn() -> sqlite3.Connection:
    config = load_config()
    db_path = config.app.database_path
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def get_media_path(media_id: int) -> Optional[Path]:
    """Retrieve original media path from database."""
    conn = _get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, original_path, original_filename FROM media WHERE id = ?", (media_id,))
        row = cur.fetchone()
        if not row or not row["original_path"]:
            return None
        p = Path(row["original_path"])
        if p.exists():
            return p
        return None
    finally:
        conn.close()


def generate_thumbnail(media_id: int, mode: str = "thumbnail") -> Optional[Path]:
    """
    Generates and caches resized media:
    - 'thumbnail': 120x120 box
    - 'preview': 600x600 box
    """
    _ensure_cache_dirs()
    target_dir = THUMBNAIL_DIR if mode == "thumbnail" else PREVIEW_DIR
    target_size = (120, 120) if mode == "thumbnail" else (600, 600)
    cached_path = target_dir / f"{media_id}_{mode}.webp"

    # Return cached if already generated
    if cached_path.exists() and cached_path.stat().st_size > 0:
        return cached_path

    orig_path = get_media_path(media_id)
    if not orig_path or not orig_path.exists():
        # Generate a placeholder image if source is archived
        img = Image.new("RGB", target_size, color=(40, 44, 52))
        img.save(cached_path, "WEBP", quality=80)
        return cached_path

    try:
        with Image.open(orig_path) as im:
            # Convert RGBA to RGB for WebP compatibility
            if im.mode in ("RGBA", "P"):
                im = im.convert("RGB")
            im.thumbnail(target_size, Image.Resampling.LANCZOS)
            im.save(cached_path, "WEBP", quality=85)
        return cached_path
    except Exception as e:
        logger.warning("Failed to generate thumbnail for media #%s: %s", media_id, e)
        img = Image.new("RGB", target_size, color=(40, 44, 52))
        img.save(cached_path, "WEBP", quality=80)
        return cached_path
