import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import json
import logging
import hashlib
import numpy as np

from src.models import MediaCandidate
from src.face_analysis import FaceAnalysisWorker
from src.database import ArchiveDatabase
from src.face_engine import FaceEngineError

@pytest.fixture
def memory_db(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    db = ArchiveDatabase(db_path)
    # Run migrations
    db.apply_migrations(Path("sql"))
    return db

@pytest.fixture
def mock_engine_config():
    config = MagicMock()
    config.app.dry_run = True
    config.faces.enabled = True
    config.faces.analyze_videos = False
    config.faces.minimum_face_size_px = 96
    config.faces.low_resolution_min_face_size_px = 48
    config.faces.detector_confidence = 0.90
    config.faces.low_resolution_detector_confidence = 0.90
    config.faces.low_resolution_accept_threshold_boost = 0.04
    config.faces.low_resolution_margin_boost = 0.03
    config.faces.low_resolution_individual_support_boost = 0.04
    config.faces.low_resolution_minimum_strong_support = 3
    config.faces.save_debug_crops = False
    config.faces.aggregate_method = "top_k_mean"
    config.faces.aggregate_top_k = 1
    config.faces.minimum_strong_support = 1
    config.faces.policy_identity = "mock_policy"
    config.faces.calibration_required = False
    config.faces.minimum_supporting_references = 1
    return config

def test_dry_run_analysis_with_no_candidates(memory_db, mock_engine_config):
    logger = MagicMock()
    worker = FaceAnalysisWorker(mock_engine_config, memory_db, MagicMock(), logger)
    worker.analyze_candidates([])
    logger.info.assert_any_call("Finished face analysis.")

def test_dry_run_analysis_with_known_and_unknown(memory_db, mock_engine_config, tmp_path):
    # Setup test candidates
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="50481bd5xxxx")
    c2 = MediaCandidate(path=tmp_path / "img2.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="9e54078dxxxx")
    c3 = MediaCandidate(path=tmp_path / "img3.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="6a3f9e88xxxx")
    c4 = MediaCandidate(path=tmp_path / "img4.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="f8e5de28xxxx")
    candidates = [c1, c2, c3, c4]

    logger = logging.getLogger("test_dry_run")
    logger.setLevel(logging.INFO)
    class LogCaptureHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []
        def emit(self, record):
            self.records.append(record)
    handler = LogCaptureHandler()
    logger.addHandler(handler)
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"
    
    def mock_decode(p):
        dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
        return {"image": dummy_img}

    with patch("src.face_analysis.decode_image_with_exif", side_effect=mock_decode):
        mock_engine.detect_faces.side_effect = [
            [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]], # c1
            [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]], # c2
            [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99], [0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]], # c3
            [] # c4
        ]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.side_effect = [
            MagicMock(size=128, tobytes=lambda: b"emb1"), # c1
            MagicMock(size=128, tobytes=lambda: b"emb2"), # c2
            MagicMock(size=128, tobytes=lambda: b"emb3"), # c3 face 1
            MagicMock(size=128, tobytes=lambda: b"emb4"), # c3 face 2
        ]
        
        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        from tests.conftest import activate_scoped_test_calibration
        activate_scoped_test_calibration(memory_db, mock_engine_config, "modelA", ["refhash"])
            
        def compare_embeddings(emb1, emb2):
            if emb1.tobytes() == b"emb1":
                return 0.9 
            elif emb1.tobytes() == b"emb2":
                return 0.7 
            elif emb1.tobytes() == b"emb3":
                return 0.85 
            elif emb1.tobytes() == b"emb4":
                return 0.85 
            return 0.0
            
        mock_engine.compare_embeddings.side_effect = compare_embeddings

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.analyze_candidates(candidates)
        
        logs = [r.getMessage() for r in handler.records]
        assert any("Candidate 1 [50481bd5]: faces=1, decision=KNOWN_MATCH" in log for log in logs)
        assert any("Candidate 2 [9e54078d]: faces=1, decision=UNKNOWN_LOW_SCORE" in log for log in logs)
        assert any("Candidate 3 [6a3f9e88]: faces=2, accepted=2, unknown=0" in log for log in logs)
        assert any("Candidate 4 [f8e5de28]: faces=0, decision=NO_FACE" in log for log in logs)

def test_dry_run_analysis_exception_produces_analysis_error(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="29c39a62xxxx")
    
    logger = logging.getLogger("test_dry_run_err")
    logger.setLevel(logging.DEBUG)
    class LogCaptureHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []
        def emit(self, record):
            self.records.append(record)
    handler = LogCaptureHandler()
    logger.addHandler(handler)
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"
    
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", side_effect=lambda x: {"image": dummy_img}):
        mock_engine.detect_faces.side_effect = Exception("Crash")
        
        from src.logging_utils import RuntimeOptions
        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger, opts=RuntimeOptions(verbose_private=True))
        worker.analyze_candidates([c1])
        
        info_logs = [r.getMessage() for r in handler.records if r.levelno == logging.INFO]
        err_logs = [r.getMessage() for r in handler.records if r.levelno == logging.ERROR]
        debug_logs = [r.getMessage() for r in handler.records if r.levelno == logging.DEBUG]
        
        assert any("Candidate 1 [29c39a62]: decision=ANALYSIS_ERROR stage=DETECTION error=Exception" in log for log in info_logs)
        assert any("Candidate [29c39a62] failed: stage=DETECTION error=Exception" in log for log in err_logs)
        assert any(r.exc_info is not None and "Crash" in str(r.exc_info[1]) for r in handler.records if r.levelno == logging.DEBUG)

def test_stale_calibration_produces_unknown_uncalibrated(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")
    
    logger = MagicMock()
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"
    
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", side_effect=lambda x: {"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")
        
        with memory_db.connect() as conn:
            conn.execute(
                "INSERT INTO face_calibrations (model_identity, reference_set_hash, accept_threshold, review_threshold, minimum_margin, individual_strong_support_threshold, positive_pair_count, negative_pair_count, active, generated_at) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 1, ?)",
                ("modelA", "wrong_hash", 0.8, 0.6, 0.1, 0.75, "now")
            )
            
        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.analyze_candidates([c1])
        
        logger.info.assert_any_call("Candidate %s [%s]: faces=1, decision=%s", 1, "abcxxxx", "UNKNOWN_UNCALIBRATED")

def test_dry_run_ignores_duplicates_and_videos(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, is_duplicate=True)
    c2 = MediaCandidate(path=tmp_path / "vid1.mp4", media_type="video", size_bytes=100, modified_ns=0)
    
    logger = MagicMock()
    mock_engine = MagicMock()
    
    worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
    worker.analyze_candidates([c1, c2])
    
    logger.info.assert_any_call("Face-analysis candidates: %s.", 0)


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure


def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure
