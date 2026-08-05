import pytest
import sqlite3
from unittest.mock import MagicMock, patch
from pathlib import Path
import numpy as np

from src.face_analysis import FaceAnalysisWorker
from src.database import ArchiveDatabase

@pytest.fixture
def memory_db(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    db = ArchiveDatabase(db_path)
    db.apply_migrations(Path("sql"))
    return db

@pytest.fixture
def mock_engine_config():
    config = MagicMock()
    config.app.dry_run = False
    config.faces.enabled = True
    config.faces.analyze_videos = False
    config.faces.aggregate_method = "top_k_mean"
    config.faces.aggregate_top_k = 1
    config.faces.minimum_strong_support = 1
    config.faces.policy_identity = "mock_policy"
    config.faces.minimum_face_size_px = 20
    config.faces.calibration_required = False
    config.faces.minimum_supporting_references = 1
    return config

def test_canonical_hash_resolves_existing_calibration(memory_db, mock_engine_config, tmp_path):
    logger = MagicMock()
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    emb = np.ones(32, dtype=np.float32).tobytes()
    with memory_db.connect() as conn:
        conn.execute("INSERT INTO people (person_id, person_slug, display_name, created_at, updated_at) VALUES (1, 'person-a', 'Person A', 'now', 'now')")
        conn.execute(
            "INSERT INTO face_references (person_id, source_sha256, source_path, enrolled_at, active, embedding_blob, embedding_dimension, model_identity) VALUES (1, ?, 'path', 'now', 1, ?, 32, 'modelA')",
            ("a" * 64, emb)
        )
        conn.execute(
            "INSERT INTO face_references (person_id, source_sha256, source_path, enrolled_at, active, embedding_blob, embedding_dimension, model_identity) VALUES (1, ?, 'path', 'now', 1, ?, 32, 'modelA')",
            ("b" * 64, emb)
        )

    worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)

    from src.hashing import get_reference_set_hash, get_calibration_scope_hash
    base_hash = get_reference_set_hash(["b"*64, "a"*64])
    policy_id = mock_engine_config.faces.policy_identity
    scope_hash = get_calibration_scope_hash("modelA", base_hash, policy_id)

    with memory_db.connect() as conn:
        conn.execute(
            "INSERT INTO face_calibrations (model_identity, reference_set_hash, accept_threshold, review_threshold, minimum_margin, positive_pair_count, negative_pair_count, active, generated_at) VALUES (?, ?, ?, ?, ?, 0, 0, 1, ?)",
            ("modelA", scope_hash, 0.8, 0.6, 0.1, "now")
        )

    worker.load_snapshots()
    assert worker.calibration_snapshot is not None
    assert worker.calibration_snapshot != "INVALID"
    assert worker.calibration_snapshot["reference_set_hash"] == scope_hash


def test_analyze_pending_hashes_string_reference_values(memory_db, mock_engine_config, tmp_path):
    logger = MagicMock()
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    with memory_db.connect() as conn:
        conn.execute("INSERT INTO people (person_id, person_slug, display_name, created_at, updated_at) VALUES (1, 'person-a', 'Person A', 'now', 'now')")
        conn.execute(
            "INSERT INTO face_references (person_id, source_sha256, source_path, enrolled_at, active) VALUES (1, ?, 'path', 'now', 1)",
            ("hash1",)
        )
        
        conn.execute(
            "INSERT INTO media (id, original_path, original_filename, size_bytes, sha256, short_hash, media_type, state, modified_ns, discovered_at, updated_at) VALUES (26, 'path', 'file', 100, 'hash', 'hash', 'image', 'READY_TO_UPLOAD', 0, 'now', 'now')"
        )

        conn.execute(
            "INSERT INTO face_analysis_attempts (media_id, analysis_key, analysis_version, model_identity, reference_set_hash, started_at, outcome) VALUES (26, 'key', 1, 'modelA', 'refhash', 'now', 'PENDING')"
        )

    worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
    worker.analyze_pending()



def test_face_analysis_recovery_flow(memory_db, mock_engine_config, tmp_path):
    logger = MagicMock()
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"
    
    # We will simulate analyze_image results to be correct
    # media 26 -> 0 faces (NO_FACE)
    # media 27 -> 1 known match
    # media 28 -> 1 unknown match (low score)

    with memory_db.connect() as conn:
        conn.execute("INSERT INTO people (person_id, person_slug, display_name, created_at, updated_at) VALUES (1, 'person-a', 'Person A', 'now', 'now')")
        for i, h in zip([26, 27, 28], ['6f74ec95', 'fe07c900', 'bc0b4882']):
            conn.execute(
                f"INSERT INTO media (id, original_path, original_filename, size_bytes, sha256, short_hash, media_type, state, face_state, cleanup_state, modified_ns, discovered_at, updated_at) VALUES ({i}, 'path{i}', 'file{i}', 100, '{h}', '{h}', 'image', 'BACKED_UP', 'FAILED', 'PENDING', 0, 'now', 'now')"
            )

    from src.hashing import get_calibration_scope_hash
    ref_set_hash = get_calibration_scope_hash("modelA", "empty", mock_engine_config.faces.policy_identity)

    # Insert old version 2 failures
    with memory_db.connect() as conn:
        for i in [26, 27, 28]:
            conn.execute(
                f"INSERT INTO face_analysis_attempts (media_id, analysis_key, analysis_version, model_identity, reference_set_hash, started_at, outcome) VALUES ({i}, 'key', 2, 'modelA', ?, 'now', 'FAILURE')",
                (ref_set_hash,)
            )

    from src.models import ImageFaceAnalysisResult
    import json

    def fake_analyze_image(image, short_hash="unknown"):
        res = ImageFaceAnalysisResult()
        res.stage = "SUCCESS"
        if short_hash == "6f74ec95":
            res.raw_detections = 0
        elif short_hash == "fe07c900":
            res.raw_detections = 1
            res.accepted_size = 1
            res.accepted_faces = 1
            res.face_results.append({
                "face_index": 0,
                "bounding_box_json": json.dumps({"x": 0, "y": 0, "w": 50, "h": 50}),
                "detector_confidence": 0.99,
                "embedding_blob": b'123',
                "embedding_dimension": 32,
                "model_identity": "modelA",
                "best_person_id": 1,
                "best_score": 0.9,
                "second_best_person_id": None,
                "second_best_score": None,
                "score_margin": 0.9,
                "supporting_reference_count": 5,
                "decision": "KNOWN_MATCH"
            })
        elif short_hash == "bc0b4882":
            res.raw_detections = 1
            res.accepted_size = 1
            res.unknown_faces = 1
            res.face_results.append({
                "face_index": 0,
                "bounding_box_json": json.dumps({"x": 0, "y": 0, "w": 50, "h": 50}),
                "detector_confidence": 0.99,
                "embedding_blob": b'123',
                "embedding_dimension": 32,
                "model_identity": "modelA",
                "best_person_id": None,
                "best_score": None,
                "second_best_person_id": None,
                "second_best_score": None,
                "score_margin": 0.0,
                "supporting_reference_count": 0,
                "decision": "UNKNOWN_LOW_SCORE"
            })
        return res

    with patch("src.face_analysis.FaceAnalysisWorker._generate_analysis_key", return_value=("key", 3)):
        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.analyze_image = fake_analyze_image

        with patch("src.face_analysis.Path.exists", return_value=True), patch("src.face_analysis.decode_image_with_exif", return_value={"image": "img"}):
            worker.analyze_pending()

        with memory_db.connect() as conn:
            media_rows = conn.execute("SELECT id, face_state FROM media").fetchall()
            assert len(media_rows) == 3
            states = {row[0]: row[1] for row in media_rows}
            assert states[26] == 'NO_FACE'
            assert states[27] == 'ANALYZED'
            assert states[28] == 'ANALYZED'
            
            old_attempts = conn.execute("SELECT outcome FROM face_analysis_attempts WHERE analysis_version = 2").fetchall()
            assert len(old_attempts) == 3
            assert all(a[0] == 'FAILURE' for a in old_attempts)
            
            new_attempts = conn.execute("SELECT attempt_id, outcome, media_id FROM face_analysis_attempts WHERE analysis_version = 3").fetchall()
            assert len(new_attempts) == 3
            assert all(a[1] == 'SUCCESS' for a in new_attempts)
            new_attempt_ids = {a[2]: a[0] for a in new_attempts}
            
            results_26 = conn.execute("SELECT * FROM media_faces WHERE media_id = 26").fetchall()
            assert len(results_26) == 0
            
            results_27 = conn.execute("SELECT decision FROM media_faces WHERE media_id = 27").fetchall()
            assert len(results_27) == 1
            assert results_27[0][0] == 'KNOWN_MATCH'
            
            results_28 = conn.execute("SELECT decision FROM media_faces WHERE media_id = 28").fetchall()
            assert len(results_28) == 1
            assert results_28[0][0] == 'UNKNOWN_LOW_SCORE'

        # Run again to prove idempotency
        with patch("src.face_analysis.Path.exists", return_value=True), patch("src.face_analysis.decode_image_with_exif", return_value={"image": "img"}):
            worker.analyze_pending()
            
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_analysis_attempts").fetchone()[0] == 6
            assert conn.execute("SELECT COUNT(*) FROM media_faces").fetchone()[0] == 2

def test_exception_stage_tracking(memory_db, mock_engine_config, tmp_path):
    logger = MagicMock()
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"
    
    with memory_db.connect() as conn:
        conn.execute(
            f"INSERT INTO media (id, original_path, original_filename, size_bytes, sha256, short_hash, media_type, state, face_state, cleanup_state, modified_ns, discovered_at, updated_at) VALUES (100, 'path100', 'file100', 100, 'abcdefgh', 'abcdefgh', 'image', 'READY_TO_UPLOAD', 'PENDING', 'PENDING', 0, 'now', 'now')"
        )
        
    worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
    from src.models import ImageFaceAnalysisResult
    import json
    
    def fake_analyze_image(image, short_hash="unknown"):
        res = ImageFaceAnalysisResult()
        res.stage = "SUCCESS"
        res.raw_detections = 1
        res.accepted_size = 1
        res.accepted_faces = 1
        res.face_results.append({
            "face_index": 0,
            "bounding_box_json": json.dumps({"x": 0, "y": 0, "w": 50, "h": 50}),
            "detector_confidence": 0.99,
            "embedding_blob": b'123',
            "embedding_dimension": 32,
            "model_identity": "modelA",
            "best_person_id": 1,
            "best_score": 0.9,
            "second_best_person_id": None,
            "second_best_score": None,
            "score_margin": 0.9,
            "supporting_reference_count": 5,
            "decision": "KNOWN_MATCH"
        })
        return res
        
    worker.analyze_image = fake_analyze_image
    
    with patch("src.face_analysis.Path.exists", return_value=True), patch("src.face_analysis.decode_image_with_exif", return_value={"image": "img"}):
        with patch.object(memory_db, "record_face_analysis_success", side_effect=NameError("foo")):
            worker.analyze_pending()
            
    logger.error.assert_called_with("Candidate [%s] failed: stage=%s error=%s", "abcdefgh", "PERSIST_RESULTS", "NameError")
