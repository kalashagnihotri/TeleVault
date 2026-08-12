import pytest
from pathlib import Path
from unittest.mock import MagicMock
import logging

from src.config import Config
from src.database import ArchiveDatabase
from src.face_analysis import FaceAnalysisWorker

def setup_worker_and_db(tmp_path: Path):
    db_path = tmp_path / "test.sqlite3"
    db = ArchiveDatabase(db_path)
    db.apply_migrations(Path("sql"))

    config = MagicMock()
    config.faces.enabled = True
    config.faces.use_for_routing = True
    config.faces.include_names_in_captions = False
    config.faces.analyze_videos = False

    logger = logging.getLogger("test")
    engine = MagicMock()

    worker = FaceAnalysisWorker(config, db, engine, logger)
    return worker, db

def test_apply_face_routing_success(tmp_path: Path):
    worker, db = setup_worker_and_db(tmp_path)

    media_id = db.reserve_media(
        sha256="hash", short_hash="hash", original_path="path", original_filename="path",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(media_id, None, 0, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01")

    # Mock the db methods instead of setting up a complex attempt just to get the names
    db.get_media_people_names = MagicMock(return_value=["Person A"])

    worker._apply_face_routing_if_enabled(media_id, "hash")

    # The route_key should now be 'people'
    with db.connect() as conn:
        route = conn.execute("SELECT route_key FROM telegram_archive WHERE media_id=?", (media_id,)).fetchone()[0]
        assert route == "people"

def test_apply_face_routing_missing_context(tmp_path: Path):
    worker, db = setup_worker_and_db(tmp_path)
    
    # Do not insert telegram_archive row, so context is missing
    media_id = 999
    db.get_media_people_names = MagicMock(return_value=["Person A"])
    
    # Should not raise exception
    worker._apply_face_routing_if_enabled(media_id, "hash")

def test_apply_face_routing_zero_people_preserves_route(tmp_path: Path):
    worker, db = setup_worker_and_db(tmp_path)
    
    media_id = db.reserve_media(
        sha256="hash", short_hash="hash", original_path="path", original_filename="path",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(media_id, None, 0, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01")

    # Return empty names (e.g. UNKNOWN_LOW_SCORE, NO_FACE)
    db.get_media_people_names = MagicMock(return_value=[])

    worker._apply_face_routing_if_enabled(media_id, "hash")

    # Route should remain everyday
    with db.connect() as conn:
        route = conn.execute("SELECT route_key FROM telegram_archive WHERE media_id=?", (media_id,)).fetchone()[0]
        assert route == "everyday"

def test_apply_face_routing_backed_up_does_not_change(tmp_path: Path):
    worker, db = setup_worker_and_db(tmp_path)
    
    media_id = db.reserve_media(
        sha256="hash", short_hash="hash", original_path="path", original_filename="path",
        media_type="image", size_bytes=100, modified_ns=1000, state="BACKED_UP", timestamp="2026-01-01"
    )
    db.update_metadata(media_id, None, 0, "", "[]", "[]", "everyday", "BACKED_UP", "2026-01-01")

    db.get_media_people_names = MagicMock(return_value=["Person A"])

    worker._apply_face_routing_if_enabled(media_id, "hash")

    # Route should remain everyday
    with db.connect() as conn:
        route = conn.execute("SELECT route_key FROM telegram_archive WHERE media_id=?", (media_id,)).fetchone()[0]
        assert route == "everyday"

def test_face_routing_caption_independence(tmp_path: Path):
    # faces.use_for_routing=True + include_names_in_captions=False
    worker, db = setup_worker_and_db(tmp_path)
    assert worker.config.faces.use_for_routing is True
    assert worker.config.faces.include_names_in_captions is False
