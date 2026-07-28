import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import json
import logging
import hashlib
import numpy as np
import math

from src.models import MediaCandidate
from src.face_analysis import FaceAnalysisWorker, _to_float
from src.database import ArchiveDatabase
from src.face_engine import FaceEngineError

def test_to_float_helper():
    assert _to_float(0.99) == 0.99
    assert _to_float(np.float32(0.99)) == np.float32(0.99)
    assert _to_float(np.array([0.99])) == 0.99
    
    with pytest.raises(ValueError):
        _to_float(np.array([0.99, 0.98]))
        
    with pytest.raises(ValueError):
        _to_float(float('nan'))
        
    with pytest.raises(ValueError):
        _to_float(float('inf'))

@pytest.fixture
def memory_db(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    db = ArchiveDatabase(db_path)
    db.apply_migrations(Path("sql"))
    return db

@pytest.fixture
def mock_engine_config():
    config = MagicMock()
    config.faces.enabled = True
    config.faces.minimum_face_size_px = 50
    config.faces.minimum_supporting_references = 1
    return config

def test_distinct_person_second_best(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="hash1")
    logger = logging.getLogger("test")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"target")
        
        person1 = memory_db.get_or_create_person("person1", "Person 1")
        person2 = memory_db.get_or_create_person("person2", "Person 2")
        
        # Add two refs for person1 and one for person2
        memory_db.add_reference(person1, "r1", "r1.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        memory_db.add_reference(person1, "r2", "r2.jpg", 0.99, 100, 100, "{}", (np.ones(128, dtype=np.float32)*2).tobytes(), 128, "modelA")
        memory_db.add_reference(person2, "r3", "r3.jpg", 0.99, 100, 100, "{}", (np.ones(128, dtype=np.float32)*3).tobytes(), 128, "modelA")
        
        with memory_db.connect() as conn:
            ref_hashes = ["r1", "r2", "r3"]
            ref_set_hash = hashlib.sha256("".join(sorted(ref_hashes)).encode()).hexdigest()
            conn.execute(
                "INSERT INTO face_calibrations (model_identity, reference_set_hash, accept_threshold, review_threshold, minimum_margin, positive_pair_count, negative_pair_count, active, generated_at) VALUES (?, ?, ?, ?, ?, 0, 0, 1, ?)",
                ("modelA", ref_set_hash, 0.8, 0.6, 0.1, "now")
            )
            
        def compare_embeddings(emb1, emb2):
            if np.allclose(emb2, np.ones(128, dtype=np.float32)):
                return 0.95 # Person 1 best
            elif np.allclose(emb2, np.ones(128, dtype=np.float32)*2):
                return 0.90 # Person 1 second score
            elif np.allclose(emb2, np.ones(128, dtype=np.float32)*3):
                return 0.82 # Person 2 best
            return 0.0
            
        mock_engine.compare_embeddings.side_effect = compare_embeddings
        
        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.analyze_candidates([c1])
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)
        
        assert len(res.face_results) == 1
        face = res.face_results[0]
        assert face["best_person_id"] == person1
        assert face["best_score"] == 0.95
        assert face["second_best_person_id"] == person2
        assert face["second_best_score"] == 0.82
        assert face["score_margin"] == pytest.approx(0.95 - 0.82)
        assert face["decision"] == "KNOWN_MATCH"

def test_missing_second_best(memory_db, mock_engine_config, tmp_path):
    logger = logging.getLogger("test")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"
    
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"target")
        
        person1 = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person1, "r1", "r1.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        with memory_db.connect() as conn:
            ref_set_hash = hashlib.sha256(b"r1").hexdigest()
            conn.execute(
                "INSERT INTO face_calibrations (model_identity, reference_set_hash, accept_threshold, review_threshold, minimum_margin, positive_pair_count, negative_pair_count, active, generated_at) VALUES (?, ?, ?, ?, ?, 0, 0, 1, ?)",
                ("modelA", ref_set_hash, 0.8, 0.6, 0.1, "now")
            )
            
        mock_engine.compare_embeddings.return_value = 0.90
        
        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)
        
        face = res.face_results[0]
        assert face["best_person_id"] == person1
        assert face["second_best_person_id"] is None
        assert face["score_margin"] == pytest.approx(0.90)
        assert face["decision"] == "KNOWN_MATCH"

def test_group_photo_resilience(memory_db, mock_engine_config, tmp_path):
    logger = logging.getLogger("test")
    logger.addHandler(logging.NullHandler())
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"
    
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [
            [0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99],
            [150, 150, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]
        ]
        
        def align_face(image, face):
            if face[0] == 0:
                return "aligned1"
            else:
                return "aligned2"
        mock_engine.align_face.side_effect = align_face
        
        def create_embedding(aligned):
            if aligned == "aligned1":
                raise ValueError("Crash on first face")
            return MagicMock(size=128, tobytes=lambda: b"target2")
        mock_engine.create_embedding.side_effect = create_embedding
        
        person1 = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person1, "r1", "r1.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        with memory_db.connect() as conn:
            conn.execute(
                "INSERT INTO face_calibrations (model_identity, reference_set_hash, accept_threshold, review_threshold, minimum_margin, positive_pair_count, negative_pair_count, active, generated_at) VALUES (?, ?, ?, ?, ?, 0, 0, 1, ?)",
                ("modelA", hashlib.sha256(b"r1").hexdigest(), 0.8, 0.6, 0.1, "now")
            )
        mock_engine.compare_embeddings.return_value = 0.90
        
        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)
        
        # Both faces should be recorded now (one error, one match)
        assert len(res.face_results) == 2
        assert res.raw_detections == 2
        assert res.accepted_faces == 1
        assert res.processing_errors == 1
        
        # Check first face is error
        assert res.face_results[0]["decision"] == "ANALYSIS_ERROR"
        
        # Check second face is match
        assert res.face_results[1]["decision"] == "KNOWN_MATCH"
        assert res.face_results[1]["best_person_id"] == person1
        assert res.stage == "SUCCESS"
