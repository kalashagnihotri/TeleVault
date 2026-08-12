import pytest
from pathlib import Path
from unittest.mock import MagicMock
import logging
import json

from src.config import Config
from src.database import ArchiveDatabase
from src.face_analysis import FaceAnalysisWorker
from src.models import ImageFaceAnalysisResult, MediaCandidate

def setup_worker(tmp_path: Path):
    db_path = tmp_path / "test.sqlite3"
    db = ArchiveDatabase(db_path)
    db.apply_migrations(Path("sql"))

    config = MagicMock()
    config.faces.enabled = True
    config.faces.use_for_routing = True
    config.faces.include_names_in_captions = False
    config.faces.analyze_videos = False
    config.faces.policy_identity = "policy_v2"

    logger = logging.getLogger("test")
    engine = MagicMock()
    engine.model_identity.return_value = "mock_model_identity"

    worker = FaceAnalysisWorker(config, db, engine, logger)
    # Mock decoding/analysis to return deterministic results
    worker.ref_snapshot = []
    worker.calibration_snapshot = None
    worker.snapshots_loaded = True
    
    return worker, db

def mock_analyze_image(worker, decision, result_faces):
    res = ImageFaceAnalysisResult()
    res.raw_detections = len(result_faces)
    res.accepted_size = len(result_faces)
    
    for f in result_faces:
        res.face_results.append({
            "face_index": 0,
            "decision": decision,
            "best_person_id": 1 if decision == "KNOWN_MATCH" else None
        })
        if decision == "KNOWN_MATCH":
            res.accepted_faces += 1
        elif "UNKNOWN" in decision:
            res.unknown_faces += 1
            
    worker.analyze_image = MagicMock(return_value=res)

def create_media(db, state="READY_TO_UPLOAD", face_state="PENDING", media_type="image", route_key="misc"):
    mid = db.reserve_media("hash", "hash", "path", "path", media_type, 100, 1000, state, "2026-01-01")
    db.update_metadata(mid, None, 0, "", "[]", "[]", route_key, state, "2026-01-01")
    with db.connect() as c:
        c.execute("UPDATE media SET face_state = ? WHERE id = ?", (face_state, mid))
    return mid

def mock_people(db):
    with db.connect() as c:
        c.execute("INSERT INTO people (person_id, display_name, person_slug, created_at, updated_at) VALUES (1, 'Person A', 'person-a', '2026-01-01', '2026-01-01')")

def test_analyze_candidates_known_match_persistence(tmp_path: Path):
    worker, db = setup_worker(tmp_path)
    worker.config.faces.use_for_routing = False
    mock_people(db)
    
    mid = create_media(db)
    
    # Needs a dummy file so original_path.exists() is true in general, but analyze_candidates doesn't check it directly
    Path("path").write_text("")
    
    mock_analyze_image(worker, "KNOWN_MATCH", [{}])
    
    candidate = MediaCandidate(Path("path"), "image", 100, 1000, "hash")
    candidate.media_id = mid
    
    # decode_image_with_exif gets called, mock it
    import src.face_analysis
    src.face_analysis.decode_image_with_exif = MagicMock(return_value={"image": b"img"})
    
    worker.analyze_candidates([candidate])
    
    with db.connect() as c:
        # attempt exists
        attempt = c.execute("SELECT outcome, analysis_version FROM face_analysis_attempts WHERE media_id = ?", (mid,)).fetchone()
        assert attempt["outcome"] == "SUCCESS"
        assert attempt["analysis_version"] == 5
        
        # media_faces contains known match
        face = c.execute("SELECT decision FROM media_faces WHERE media_id = ?", (mid,)).fetchone()
        assert face["decision"] == "KNOWN_MATCH"
        
        # media.face_state == ANALYZED
        m = c.execute("SELECT face_state FROM media WHERE id = ?", (mid,)).fetchone()
        assert m["face_state"] == "ANALYZED"
        
        # route remains unchanged
        r = c.execute("SELECT route_key FROM telegram_archive WHERE media_id = ?", (mid,)).fetchone()
        assert r["route_key"] == "misc"

def test_analyze_candidates_known_match_routing(tmp_path: Path):
    worker, db = setup_worker(tmp_path)
    worker.config.faces.use_for_routing = True
    mock_people(db)
    
    mid = create_media(db)
    Path("path").write_text("")
    mock_analyze_image(worker, "KNOWN_MATCH", [{}])
    
    candidate = MediaCandidate(Path("path"), "image", 100, 1000, "hash")
    candidate.media_id = mid
    
    import src.face_analysis
    src.face_analysis.decode_image_with_exif = MagicMock(return_value={"image": b"img"})
    
    worker.analyze_candidates([candidate])
    
    with db.connect() as c:
        attempt = c.execute("SELECT outcome FROM face_analysis_attempts WHERE media_id = ?", (mid,)).fetchone()
        assert attempt["outcome"] == "SUCCESS"
        
        r = c.execute("SELECT route_key FROM telegram_archive WHERE media_id = ?", (mid,)).fetchone()
        assert r["route_key"] == "people"
        
        m = c.execute("SELECT state FROM media WHERE id = ?", (mid,)).fetchone()
        assert m["state"] == "READY_TO_UPLOAD"

def test_analyze_pending_known_match_routing(tmp_path: Path):
    worker, db = setup_worker(tmp_path)
    worker.config.faces.use_for_routing = True
    mock_people(db)
    
    mid = create_media(db)
    Path("path").write_text("")
    mock_analyze_image(worker, "KNOWN_MATCH", [{}])
    
    import src.face_analysis
    src.face_analysis.decode_image_with_exif = MagicMock(return_value={"image": b"img"})
    
    worker.analyze_pending()
    
    with db.connect() as c:
        attempt = c.execute("SELECT outcome FROM face_analysis_attempts WHERE media_id = ?", (mid,)).fetchone()
        assert attempt["outcome"] == "SUCCESS"
        
        r = c.execute("SELECT route_key FROM telegram_archive WHERE media_id = ?", (mid,)).fetchone()
        assert r["route_key"] == "people"

def test_unknown_preservation(tmp_path: Path):
    worker, db = setup_worker(tmp_path)
    mid = create_media(db)
    Path("path").write_text("")
    
    mock_analyze_image(worker, "UNKNOWN_LOW_SCORE", [{}])
    
    import src.face_analysis
    src.face_analysis.decode_image_with_exif = MagicMock(return_value={"image": b"img"})
    
    worker.analyze_pending()
    
    with db.connect() as c:
        attempt = c.execute("SELECT outcome FROM face_analysis_attempts WHERE media_id = ?", (mid,)).fetchone()
        assert attempt["outcome"] == "SUCCESS"
        r = c.execute("SELECT route_key FROM telegram_archive WHERE media_id = ?", (mid,)).fetchone()
        assert r["route_key"] == "misc"

def test_no_face_preservation(tmp_path: Path):
    worker, db = setup_worker(tmp_path)
    mid = create_media(db)
    Path("path").write_text("")
    
    mock_analyze_image(worker, "NO_FACE", [])
    
    import src.face_analysis
    src.face_analysis.decode_image_with_exif = MagicMock(return_value={"image": b"img"})
    
    worker.analyze_pending()
    
    with db.connect() as c:
        attempt = c.execute("SELECT outcome FROM face_analysis_attempts WHERE media_id = ?", (mid,)).fetchone()
        assert attempt["outcome"] == "SUCCESS"
        
        m = c.execute("SELECT face_state FROM media WHERE id = ?", (mid,)).fetchone()
        assert m["face_state"] == "NO_FACE"
        
        r = c.execute("SELECT route_key FROM telegram_archive WHERE media_id = ?", (mid,)).fetchone()
        assert r["route_key"] == "misc"

def test_backed_up_reanalysis_safety(tmp_path: Path):
    worker, db = setup_worker(tmp_path)
    mock_people(db)
    mid = create_media(db, state="BACKED_UP", route_key="everyday")
    
    with db.connect() as c:
        c.execute("UPDATE telegram_archive SET original_message_id='msg', telegram_file_id='file', preview_message_id='prev', upload_confirmed_at='2026' WHERE media_id=?", (mid,))
        
    Path("path").write_text("")
    mock_analyze_image(worker, "KNOWN_MATCH", [{}])
    
    candidate = MediaCandidate(Path("path"), "image", 100, 1000, "hash")
    candidate.media_id = mid
    
    import src.face_analysis
    src.face_analysis.decode_image_with_exif = MagicMock(return_value={"image": b"img"})
    
    worker.analyze_candidates([candidate])
    
    with db.connect() as c:
        r = c.execute("SELECT route_key, original_message_id FROM telegram_archive WHERE media_id = ?", (mid,)).fetchone()
        assert r["route_key"] == "everyday"
        assert r["original_message_id"] == "msg"

def test_routing_exception_cannot_corrupt_success(tmp_path: Path):
    worker, db = setup_worker(tmp_path)
    mock_people(db)
    mid = create_media(db)
    Path("path").write_text("")
    mock_analyze_image(worker, "KNOWN_MATCH", [{}])
    
    # force exception in routing
    db.update_route_before_upload = MagicMock(side_effect=Exception("Database locked test"))
    
    import src.face_analysis
    src.face_analysis.decode_image_with_exif = MagicMock(return_value={"image": b"img"})
    
    worker.analyze_pending()
    
    with db.connect() as c:
        attempt = c.execute("SELECT outcome FROM face_analysis_attempts WHERE media_id = ?", (mid,)).fetchone()
        assert attempt["outcome"] == "SUCCESS"
        m = c.execute("SELECT face_state, state FROM media WHERE id = ?", (mid,)).fetchone()
        assert m["face_state"] == "ANALYZED"
        assert m["state"] == "READY_TO_UPLOAD"

