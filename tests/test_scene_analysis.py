import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock
import logging

from src.config import Config
from src.database import ArchiveDatabase
from src.scene_analysis import SceneAnalysisWorker, CURRENT_SCENE_ANALYSIS_VERSION
from src.routing import choose_topic, RouteInput

def setup_worker_and_db(tmp_path: Path):
    db_path = tmp_path / "test.sqlite3"
    db = ArchiveDatabase(db_path)
    db.apply_migrations(Path("sql"))

    config = MagicMock()
    config.scenes = MagicMock()
    config.scenes.enabled = True
    config.scenes.model_path = ""
    config.scenes.minimum_confidence = 0.25
    config.scenes.max_labels = 3
    config.scenes.enable_screenshot_heuristics = False
    config.scenes.enable_document_heuristics = False
    config.app.dry_run = False

    logger = logging.getLogger("test")

    worker = SceneAnalysisWorker(config, db, logger)
    return worker, db

def test_scene_analysis_success_updates_state_and_routing(tmp_path: Path):
    worker, db = setup_worker_and_db(tmp_path)

    media_id = db.reserve_media(
        sha256="hash1", short_hash="hash1", original_path="test.jpg", original_filename="test.jpg",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    # Set scene_state to PENDING
    db.update_metadata(media_id, None, 1, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01", scene_state="PENDING")
    
    # Fake classifier output
    fake_clf = MagicMock()
    fake_clf.classify.return_value = [{"label": "mountain", "confidence": 0.9}]
    worker._fake_classifier = fake_clf
    
    worker.run_pending()
    
    with db.connect() as conn:
        row = conn.execute("SELECT scene_state, labels_json FROM media WHERE id=?", (media_id,)).fetchone()
        assert row["scene_state"] == "COMPLETED"
        assert "mountains" in json.loads(row["labels_json"])
        
        route = conn.execute("SELECT route_key FROM telegram_archive WHERE media_id=?", (media_id,)).fetchone()[0]
        assert route == "travel_nature"

def test_scene_analysis_failure_preserves_upload_state(tmp_path: Path):
    worker, db = setup_worker_and_db(tmp_path)

    media_id = db.reserve_media(
        sha256="hash2", short_hash="hash2", original_path="test2.jpg", original_filename="test2.jpg",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(media_id, None, 1, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01", scene_state="PENDING")
    
    fake_clf = MagicMock()
    fake_clf.classify.side_effect = Exception("Model crashed")
    worker._fake_classifier = fake_clf
    
    worker.run_pending()
    
    with db.connect() as conn:
        row = conn.execute("SELECT scene_state, state FROM media WHERE id=?", (media_id,)).fetchone()
        assert row["scene_state"] == "FAILED"
        assert row["state"] == "READY_TO_UPLOAD"
        row2 = conn.execute("SELECT scene_error_code FROM media WHERE id=?", (media_id,)).fetchone()
        assert row2["scene_error_code"] == "SCENE_INFERENCE_FAILED"

def test_scene_routing_does_not_override_face_routing(tmp_path: Path):
    worker, db = setup_worker_and_db(tmp_path)

    media_id = db.reserve_media(
        sha256="hash3", short_hash="hash3", original_path="test3.jpg", original_filename="test3.jpg",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(media_id, None, 1, "", "[]", "[]", "people", "READY_TO_UPLOAD", "2026-01-01", scene_state="PENDING")
    
    # Mock face routing overriding by simulating person exists
    db.get_media_people_names = MagicMock(return_value=["Person A"])
    
    fake_clf = MagicMock()
    fake_clf.classify.return_value = [{"label": "screenshot", "confidence": 0.9}]
    worker._fake_classifier = fake_clf
    
    worker.run_pending()
    
    with db.connect() as conn:
        route = conn.execute("SELECT route_key FROM telegram_archive WHERE media_id=?", (media_id,)).fetchone()[0]
        # Should stay people because of person presence
        assert route == "people"

def test_scene_does_not_update_route_after_upload_started(tmp_path: Path):
    worker, db = setup_worker_and_db(tmp_path)

    media_id = db.reserve_media(
        sha256="hash4", short_hash="hash4", original_path="test4.jpg", original_filename="test4.jpg",
        media_type="image", size_bytes=100, modified_ns=1000, state="PREVIEW_CONFIRMED", timestamp="2026-01-01"
    )
    db.update_metadata(media_id, None, 1, "", "[]", "[]", "everyday", "PREVIEW_CONFIRMED", "2026-01-01", scene_state="PENDING")
    
    # Update archive to have preview_message_id
    with db.connect() as conn:
        conn.execute("UPDATE telegram_archive SET preview_message_id = 123 WHERE media_id = ?", (media_id,))
        conn.commit()
    
    fake_clf = MagicMock()
    fake_clf.classify.return_value = [{"label": "mountains", "confidence": 0.9}]
    worker._fake_classifier = fake_clf
    
    worker.run_pending()
    
    with db.connect() as conn:
        route = conn.execute("SELECT route_key FROM telegram_archive WHERE media_id=?", (media_id,)).fetchone()[0]
        # The route update should be rejected because upload started
        assert route == "everyday"
        # The scene state should STILL be COMPLETED successfully
        scene_state = conn.execute("SELECT scene_state FROM media WHERE id=?", (media_id,)).fetchone()[0]
        assert scene_state == "COMPLETED"

def test_screenshot_heuristic_short_circuits_ml(tmp_path: Path):
    worker, db = setup_worker_and_db(tmp_path)
    
    media_id = db.reserve_media(
        sha256="hash5", short_hash="hash5", original_path="test5.png", original_filename="test5.png",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(media_id, None, 1, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01", scene_state="PENDING")
    
    worker.config.scenes.enable_screenshot_heuristics = True
    
    fake_clf = MagicMock()
    # If ML is called, it returns indoor
    fake_clf.classify.return_value = [{"label": "indoor", "confidence": 0.9}]
    worker._fake_classifier = fake_clf
    
    with patch('src.scene_analysis.extract_heuristic_scene_labels', return_value=["screenshot"]), \
         patch('src.scene_analysis.is_photographic', return_value=False):
        worker.run_pending()
        
    # Classifier should NOT be called
    fake_clf.classify.assert_not_called()
    
    with db.connect() as conn:
        row = conn.execute("SELECT scene_state, labels_json FROM media WHERE id=?", (media_id,)).fetchone()
        assert row["scene_state"] == "COMPLETED"
        labels = json.loads(row["labels_json"])
        assert "screenshot" in labels
        assert "indoor" not in labels # ML skipped
        
        route = conn.execute("SELECT route_key FROM telegram_archive WHERE media_id=?", (media_id,)).fetchone()[0]
        assert route == "screenshots_documents"

def test_scene_classifier_manifest_validation(tmp_path: Path):
    from src.scene_analysis import SceneClassifier
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    
    # Create fake model and categories
    model_file = model_dir / "test.onnx"
    model_file.write_bytes(b"fake model")
    
    cat_file = model_dir / "cats.txt"
    # Needs 365 categories
    cats = "\n".join([f"/a/a_{i} {i}" for i in range(365)])
    cat_file.write_bytes(cats.encode("utf-8"))
    
    manifest_file = model_dir / "manifest.json"
    
    # Fake hashes
    import hashlib
    h_onnx = hashlib.sha256(b"fake model").hexdigest()
    h_cats = hashlib.sha256(cats.encode("utf-8")).hexdigest()
    
    manifest_file.write_text(json.dumps({
        "onnx_sha256": h_onnx,
        "categories_sha256": h_cats
    }))
    
    import onnxruntime as ort
    original_session = ort.InferenceSession
    ort.InferenceSession = MagicMock()
    
    try:
        # Should succeed
        SceneClassifier(str(model_file), str(cat_file))
        
        # Now corrupt manifest
        manifest_file.write_text(json.dumps({
            "onnx_sha256": "badhash",
            "categories_sha256": h_cats
        }))
        
        with pytest.raises(ValueError, match="ONNX model hash mismatch"):
            SceneClassifier(str(model_file), str(cat_file))
            
    finally:
        ort.InferenceSession = original_session

def test_mapping_keys_exist_in_categories():
    from src.scene_analysis import SceneClassifier, PLACES365_MAPPING
    model_path = Path("private_data/scenes/models/resnet18_places365.onnx")
    cat_path = Path("private_data/scenes/models/categories_places365.txt")
    
    if not model_path.exists() or not cat_path.exists():
        pytest.skip("Models not downloaded, skipping mapping validation.")
        
    clf = SceneClassifier(str(model_path), str(cat_path))
    valid_categories = set(clf.categories)
    
    missing = []
    for raw_key in PLACES365_MAPPING.keys():
        if raw_key not in valid_categories:
            missing.append(raw_key)
            
    assert not missing, f"Invalid PLACES365_MAPPING keys not in official vocab: {missing}"

def test_pub_indoor_mapping_survives_threshold(tmp_path: Path):
    worker, db = setup_worker_and_db(tmp_path)

    media_id = db.reserve_media(
        sha256="hash6", short_hash="hash6", original_path="test6.jpg", original_filename="test6.jpg",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(media_id, None, 1, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01", scene_state="PENDING")
    
    worker.config.scenes.minimum_confidence = 0.25
    
    fake_clf = MagicMock()
    # Output raw pub/indoor with 0.3006
    fake_clf.classify.return_value = [{"label": "pub/indoor", "confidence": 0.3006}]
    worker._fake_classifier = fake_clf
    
    worker.run_pending()
    
    with db.connect() as conn:
        row = conn.execute("SELECT scene_state, labels_json FROM media WHERE id=?", (media_id,)).fetchone()
        assert row["scene_state"] == "COMPLETED"
        labels = json.loads(row["labels_json"])
        assert "indoor" in labels
        assert len(labels) == 1

from unittest.mock import patch

@patch('src.scene_analysis.SceneClassifier')
def test_lazy_initialization_screenshot_only(mock_classifier, tmp_path: Path):
    worker, db = setup_worker_and_db(tmp_path)
    # mock extract_heuristic_scene_labels
    
    media_id = db.reserve_media(
        sha256="hash1", short_hash="hash1", original_path="test1.png", original_filename="test1.png",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(media_id, None, 1, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01", scene_state="PENDING")
    
    worker._fake_classifier = None # Must be None to test real initialization logic
    
    with patch('src.scene_analysis.extract_heuristic_scene_labels', return_value=["screenshot"]), \
         patch('src.scene_analysis.is_photographic', return_value=False):
        worker.run_pending()
        
    mock_classifier.assert_not_called()
    with db.connect() as conn:
        assert conn.execute("SELECT scene_state FROM media WHERE id=?", (media_id,)).fetchone()[0] == "COMPLETED"

@patch('src.scene_analysis.SceneClassifier')
def test_lazy_initialization_document_only(mock_classifier, tmp_path: Path):
    worker, db = setup_worker_and_db(tmp_path)
    
    media_id = db.reserve_media(
        sha256="hash2", short_hash="hash2", original_path="test2.pdf", original_filename="test2.pdf",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(media_id, None, 1, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01", scene_state="PENDING")
    
    worker._fake_classifier = None
    
    with patch('src.scene_analysis.extract_heuristic_scene_labels', return_value=["document"]):
        worker.run_pending()
        
    mock_classifier.assert_not_called()
    with db.connect() as conn:
        assert conn.execute("SELECT scene_state FROM media WHERE id=?", (media_id,)).fetchone()[0] == "COMPLETED"

@patch('src.scene_analysis.SceneClassifier')
def test_lazy_initialization_mixed_batch(mock_classifier, tmp_path: Path):
    worker, db = setup_worker_and_db(tmp_path)
    worker._fake_classifier = None
    
    # fake classifier instance
    mock_instance = MagicMock()
    mock_instance.classify.return_value = [{"label": "mountain", "confidence": 0.9}]
    mock_classifier.return_value = mock_instance
    
    m1 = db.reserve_media(
        sha256="hash_ss", short_hash="hash_ss", original_path="ss.png", original_filename="ss.png",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(m1, None, 1, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01", scene_state="PENDING")
    
    m2 = db.reserve_media(
        sha256="hash_norm1", short_hash="hash_norm1", original_path="norm1.jpg", original_filename="norm1.jpg",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(m2, None, 1, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01", scene_state="PENDING")

    m3 = db.reserve_media(
        sha256="hash_norm2", short_hash="hash_norm2", original_path="norm2.jpg", original_filename="norm2.jpg",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(m3, None, 1, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01", scene_state="PENDING")
    
    def side_effect(path, config):
        if "ss.png" in str(path):
            return ["screenshot"]
        return []
        
    with patch('src.scene_analysis.extract_heuristic_scene_labels', side_effect=side_effect), \
         patch('src.scene_analysis.is_photographic', return_value=False):
        worker.run_pending()
        
    mock_classifier.assert_called_once()
    assert mock_instance.classify.call_count == 2
    
    with db.connect() as conn:
        assert conn.execute("SELECT scene_state FROM media WHERE id=?", (m1,)).fetchone()[0] == "COMPLETED"
        assert conn.execute("SELECT scene_state FROM media WHERE id=?", (m2,)).fetchone()[0] == "COMPLETED"
        assert conn.execute("SELECT scene_state FROM media WHERE id=?", (m3,)).fetchone()[0] == "COMPLETED"

@patch('src.scene_analysis.SceneClassifier')
def test_lazy_initialization_failure(mock_classifier, tmp_path: Path):
    worker, db = setup_worker_and_db(tmp_path)
    worker._fake_classifier = None
    
    mock_classifier.side_effect = Exception("Model init failed")
    
    m1 = db.reserve_media(
        sha256="hash_norm", short_hash="hash_norm", original_path="norm.jpg", original_filename="norm.jpg",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(m1, None, 1, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01", scene_state="PENDING")
    
    with patch('src.scene_analysis.extract_heuristic_scene_labels', return_value=[]):
        worker.run_pending()
        
    with db.connect() as conn:
        row = conn.execute("SELECT scene_state, state FROM media WHERE id=?", (m1,)).fetchone()
        assert row["scene_state"] == "FAILED"
        assert row["state"] == "READY_TO_UPLOAD"
        row2 = conn.execute("SELECT scene_error_code FROM media WHERE id=?", (m1,)).fetchone()
        assert row2["scene_error_code"] == "SCENE_MODEL_INIT_FAILED"

@patch('src.scene_analysis.SceneClassifier')
def test_lazy_initialization_invalid_path_screenshot_completed(mock_classifier, tmp_path: Path):
    worker, db = setup_worker_and_db(tmp_path)
    worker._fake_classifier = None
    worker.config.scenes.model_path = "/invalid/path/that/does/not/exist.onnx"
    # Even without mocking SceneClassifier to throw, it shouldn't even be called!
    
    m1 = db.reserve_media(
        sha256="hash_ss2", short_hash="hash_ss2", original_path="ss2.png", original_filename="ss2.png",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(m1, None, 1, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01", scene_state="PENDING")
    
    with patch('src.scene_analysis.extract_heuristic_scene_labels', return_value=["screenshot"]), \
         patch('src.scene_analysis.is_photographic', return_value=False):
        worker.run_pending()
        
    mock_classifier.assert_not_called()
    with db.connect() as conn:
        assert conn.execute("SELECT scene_state FROM media WHERE id=?", (m1,)).fetchone()[0] == "COMPLETED"



def test_photographic_screenshot_invokes_ml(tmp_path):
    from src.scene_analysis import SceneAnalysisWorker, CURRENT_SCENE_ANALYSIS_VERSION
    from unittest.mock import MagicMock
    from pathlib import Path
    import json
    
    worker, db = setup_worker_and_db(tmp_path)
    
    media_id = db.reserve_media(
        sha256="hash_photo_sc", short_hash="hash_photo_sc", original_path="test_ps.png", original_filename="test_ps.png",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(media_id, None, 1, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01", scene_state="PENDING")
    
    worker.config.scenes.enable_screenshot_heuristics = True
    
    fake_clf = MagicMock()
    fake_clf.classify.return_value = [{"label": "mountain", "confidence": 0.9}]
    worker._fake_classifier = fake_clf
    
    with patch('src.scene_analysis.extract_heuristic_scene_labels', return_value=["screenshot"]), \
         patch('src.scene_analysis.is_photographic', return_value=True):
        worker.run_pending()
        
    fake_clf.classify.assert_called_once()
    
    with db.connect() as conn:
        row = conn.execute("SELECT scene_state, labels_json FROM media WHERE id=?", (media_id,)).fetchone()
        assert row["scene_state"] == "COMPLETED"
        labels = json.loads(row["labels_json"])
        assert "screenshot" in labels
        assert "mountains" in labels

def test_scene_analysis_persists_version_4(tmp_path):
    from src.scene_analysis import SceneAnalysisWorker, CURRENT_SCENE_ANALYSIS_VERSION
    from unittest.mock import MagicMock
    from tests.test_scene_analysis import setup_worker_and_db
    
    assert CURRENT_SCENE_ANALYSIS_VERSION == 4
    
    worker, db = setup_worker_and_db(tmp_path)
    
    media_id = db.reserve_media(
        sha256="v3test", short_hash="v3test", original_path="v3test.jpg", original_filename="v3test.jpg",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(media_id, None, 1, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01", scene_state="PENDING")
    
    fake_clf = MagicMock()
    fake_clf.classify.return_value = []
    worker._fake_classifier = fake_clf
    
    worker.run_pending()
    
    with db.connect() as conn:
        row = conn.execute("SELECT scene_analysis_version FROM media WHERE id=?", (media_id,)).fetchone()
        assert row["scene_analysis_version"] == 4

def test_document_visual_heuristic_invoked(tmp_path: Path):
    from src.scene_analysis import SceneAnalysisWorker, CURRENT_SCENE_ANALYSIS_VERSION
    from src.image_heuristics import is_document_like
    from PIL import Image, ImageDraw
    from tests.test_scene_analysis import setup_worker_and_db
    from unittest.mock import MagicMock
    
    assert CURRENT_SCENE_ANALYSIS_VERSION == 4
    worker, db = setup_worker_and_db(tmp_path)
    worker.config.scenes.enable_document_heuristics = True
    worker.config.scenes.enable_screenshot_heuristics = True
    
    # 1. Create a strong document-like image
    doc_path = tmp_path / "neutral_name.jpg"
    img = Image.new('RGB', (1080, 2400), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    for i in range(120):
        d.rectangle([100, 100 + i*18, 980, 110 + i*18], fill=(0,0,0))
    img.save(doc_path)
    
    # Ensure our heuristic correctly flags it
    assert is_document_like(doc_path) == True
    
    # Run it through pipeline
    m1 = db.reserve_media(
        sha256="d1", short_hash="d1", original_path=str(doc_path), original_filename="neutral_name.jpg",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(m1, None, 1, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01", scene_state="PENDING")
    
    fake_clf = MagicMock()
    worker._fake_classifier = fake_clf
    worker.run_pending()
    
    with db.connect() as conn:
        labels_json = conn.execute("SELECT labels_json FROM media WHERE id=?", (m1,)).fetchone()["labels_json"]
        assert "document" in json.loads(labels_json)
        assert "screenshot" not in json.loads(labels_json)
    # ML is skipped because document overrides
    fake_clf.classify.assert_not_called()

def test_document_overrides_photographic_gate(tmp_path: Path):
    from src.scene_analysis import SceneAnalysisWorker
    from src.image_heuristics import is_document_like
    from PIL import Image, ImageDraw
    from tests.test_scene_analysis import setup_worker_and_db
    from unittest.mock import MagicMock
    import os
    import numpy as np
    
    worker, db = setup_worker_and_db(tmp_path)
    worker.config.scenes.enable_document_heuristics = True
    worker.config.scenes.enable_screenshot_heuristics = True
    
    doc_path = tmp_path / "Screenshot_Document_Test.png"
    img = Image.new('RGB', (1080, 2400), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    for i in range(120):
        d.rectangle([100, 100 + i*18, 980, 110 + i*18], fill=(0,0,0))
    
    # Add fake photographic complexity by pasting a random noise patch
    # to bypass the 5000 unique colors check (use grayscale to avoid high saturation penalty)
    gray_noise = np.random.randint(0, 256, (600, 400), dtype=np.uint8)
    noise = np.stack([gray_noise]*3, axis=2)
    noise_img = Image.fromarray(noise)
    img.paste(noise_img, (240, 1000))
    img.save(doc_path)
    
    assert is_document_like(doc_path) == True
    
    m1 = db.reserve_media(
        sha256="d2", short_hash="d2", original_path=str(doc_path), original_filename="Screenshot_Document_Test.png",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(m1, None, 1, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01", scene_state="PENDING")
    
    fake_clf = MagicMock()
    worker._fake_classifier = fake_clf
    worker.run_pending()
    
    with db.connect() as conn:
        labels_json = conn.execute("SELECT labels_json FROM media WHERE id=?", (m1,)).fetchone()["labels_json"]
        labels = json.loads(labels_json)
        # Because filename starts with Screenshot, it should have both!
        assert "document" in labels
        assert "screenshot" in labels
    
    # ML is skipped because document is present!
    fake_clf.classify.assert_not_called()

def test_pure_ui_screenshot_not_document(tmp_path: Path):
    from src.scene_analysis import SceneAnalysisWorker
    from src.image_heuristics import is_document_like
    from PIL import Image, ImageDraw
    from tests.test_scene_analysis import setup_worker_and_db
    from unittest.mock import MagicMock
    
    worker, db = setup_worker_and_db(tmp_path)
    worker.config.scenes.enable_document_heuristics = True
    worker.config.scenes.enable_screenshot_heuristics = True
    
    ui_path = tmp_path / "Screenshot_UI.png"
    # Pure UI terminal-like
    img = Image.new('RGB', (1080, 2400), color=(0, 0, 0))
    d = ImageDraw.Draw(img)
    for i in range(50):
        d.text((20, 20 + i*30), 'PS C:\\\\> command output...', fill=(200, 200, 200))
    img.save(ui_path)
    
    assert is_document_like(ui_path) == False
    
    m1 = db.reserve_media(
        sha256="d3", short_hash="d3", original_path=str(ui_path), original_filename="Screenshot_UI.png",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(m1, None, 1, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01", scene_state="PENDING")
    
    fake_clf = MagicMock()
    worker._fake_classifier = fake_clf
    worker.run_pending()
    
    with db.connect() as conn:
        labels_json = conn.execute("SELECT labels_json FROM media WHERE id=?", (m1,)).fetchone()["labels_json"]
        labels = json.loads(labels_json)
        assert "document" not in labels
        assert "screenshot" in labels

def test_real_failed_document_fixture(tmp_path: Path):
    from src.scene_analysis import SceneAnalysisWorker, CURRENT_SCENE_ANALYSIS_VERSION
    from src.image_heuristics import is_document_like
    from tests.test_scene_analysis import setup_worker_and_db
    from unittest.mock import MagicMock
    import shutil
    import json
    import os
    
    real_path = "G:/My Drive/TelegramMediaQueueTest/Incoming/Images/uaysdyfusv jhzdfs kjzsdvkjDF vkh  k.png"
    if not os.path.exists(real_path):
        return  # skip if not present
        
    worker, db = setup_worker_and_db(tmp_path)
    worker.config.scenes.enable_document_heuristics = True
    worker.config.scenes.enable_screenshot_heuristics = True
    
    # Generic filename case
    doc_path = tmp_path / "random_8f93a.png"
    shutil.copy(real_path, doc_path)
    
    assert is_document_like(doc_path) == True
    
    m1 = db.reserve_media(
        sha256="dreal1", short_hash="dreal1", original_path=str(doc_path), original_filename="random_8f93a.png",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(m1, None, 1, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01", scene_state="PENDING")
    
    # Screenshot filename case
    doc_screen_path = tmp_path / "Screenshot_random_8f93a.png"
    shutil.copy(real_path, doc_screen_path)
    m2 = db.reserve_media(
        sha256="dreal2", short_hash="dreal2", original_path=str(doc_screen_path), original_filename="Screenshot_random_8f93a.png",
        media_type="image", size_bytes=100, modified_ns=1000, state="READY_TO_UPLOAD", timestamp="2026-01-01"
    )
    db.update_metadata(m2, None, 1, "", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01", scene_state="PENDING")
    
    fake_clf = MagicMock()
    worker._fake_classifier = fake_clf
    worker.run_pending()
    
    with db.connect() as conn:
        # Check generic filename
        labels_json = conn.execute("SELECT labels_json FROM media WHERE id=?", (m1,)).fetchone()["labels_json"]
        labels = json.loads(labels_json)
        assert "document" in labels
        assert "screenshot" not in labels
        
        # Check screenshot filename
        labels_json2 = conn.execute("SELECT labels_json FROM media WHERE id=?", (m2,)).fetchone()["labels_json"]
        labels2 = json.loads(labels_json2)
        assert "document" in labels2
        assert "screenshot" in labels2
        
    fake_clf.classify.assert_not_called()

def test_high_density_negatives(tmp_path: Path):
    from src.image_heuristics import is_document_like
    from PIL import Image, ImageDraw
    import numpy as np
    
    # Dense Code UI (dark mode, lots of edges, highly neutral, some colored syntax highlighting)
    code_ui = tmp_path / "dense_code.png"
    img = Image.new('RGB', (1080, 2400), color=(30, 30, 30))
    d = ImageDraw.Draw(img)
    for i in range(150):
        # Syntax highlighted code lines
        color = (200, 200, 200) if i % 3 != 0 else (100, 200, 255)
        d.text((20 + (i%5)*10, 20 + i*15), 'def process_data(item): return [x for x in item.keys()]', fill=color)
    img.save(code_ui)
    
    # Building Facade (lots of windows, photographic, high edge density)
    facade = tmp_path / "facade.png"
    img2 = Image.new('RGB', (1080, 2400), color=(150, 200, 250)) # Sky background
    d2 = ImageDraw.Draw(img2)
    # Draw building
    d2.rectangle([100, 100, 980, 2400], fill=(100, 100, 100))
    # Draw hundreds of windows (high edge density)
    for row in range(50):
        for col in range(10):
            d2.rectangle([120 + col*80, 120 + row*45, 180 + col*80, 150 + row*45], fill=(50, 50, 80))
    
    # Add random photographic noise to break "neutral/light" bounds
    noise = np.random.randint(0, 40, (2400, 1080, 3), dtype=np.uint8)
    arr = np.array(img2)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    img2 = Image.fromarray(arr)
    img2.save(facade)
    
    # Verify neither is classified as a document
    assert is_document_like(code_ui) == False
    assert is_document_like(facade) == False
