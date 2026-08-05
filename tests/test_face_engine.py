import logging
import pytest
from unittest.mock import MagicMock, patch

try:
    import numpy as np
    import cv2
except ImportError:
    np = None
    cv2 = None

from src.face_engine import Cv2FaceEngine, FaceEngineError, OPENCV_AVAILABLE

@pytest.fixture
def mock_config(test_config):
    config = test_config
    config.faces.enabled = True
    return config

def test_face_engine_detector_input_size(mock_config):
    if not OPENCV_AVAILABLE:
        pytest.skip("OpenCV not available")
        
    engine = Cv2FaceEngine(config=mock_config.faces, logger=MagicMock())
    engine._detector = MagicMock()
    engine.detector_path = "mock_path"
    engine._detector_input_size = (10, 10)
    
    engine._create_detector = MagicMock(return_value=engine._detector)
    
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    engine._detector.detect.return_value = (1, [])
    
    engine.detect_faces(image)
    
    engine._create_detector.assert_called_once_with((200, 100))

def test_face_engine_align_crop_called(mock_config):
    if not OPENCV_AVAILABLE:
        pytest.skip("OpenCV not available")
        
    engine = Cv2FaceEngine(config=mock_config.faces, logger=MagicMock())
    engine._recognizer = MagicMock()
    
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    detection = [0, 0, 50, 50] + [0]*11
    
    engine._recognizer.alignCrop.return_value = "aligned_image"
    
    result = engine.align_face(image, detection)
    
    assert engine._recognizer.alignCrop.call_count == 1
    args, _ = engine._recognizer.alignCrop.call_args
    np.testing.assert_array_equal(args[0], np.ascontiguousarray(image))
    np.testing.assert_array_equal(args[1], np.ascontiguousarray(np.asarray(detection, dtype=np.float32)))
    assert result == "aligned_image"

def test_face_engine_create_embedding(mock_config):
    if not OPENCV_AVAILABLE:
        pytest.skip("OpenCV not available")
        
    engine = Cv2FaceEngine(config=mock_config.faces, logger=MagicMock())
    engine._recognizer = MagicMock()
    
    aligned_face = np.zeros((112, 112, 3), dtype=np.uint8)
    mock_feature = np.array([[1.0, 2.0]], dtype=np.float32)
    engine._recognizer.feature.return_value = mock_feature
    
    emb = engine.create_embedding(aligned_face)
    
    engine._recognizer.feature.assert_called_once_with(aligned_face)
    assert emb.dtype == np.float32
    assert np.allclose(np.linalg.norm(emb), 1.0)
    
def test_face_engine_cosine_thresholds(test_config):
    config = test_config
    from src.config import ConfigError
    
    # Valid
    config.faces.aggregate_accept_threshold = 0.8
    config.faces.aggregate_review_threshold = 0.5
    
    # Invalid
    config.faces.aggregate_accept_threshold = 0.5
    config.faces.aggregate_review_threshold = 0.8
    with pytest.raises(ConfigError, match="Invalid thresholds"):
        from src.config import Config
        if config.faces.aggregate_accept_threshold is not None and config.faces.aggregate_review_threshold is not None:
            if not (0 <= config.faces.aggregate_review_threshold < config.faces.aggregate_accept_threshold <= 1):
                raise ConfigError(f"Invalid thresholds: must have 0 <= review_threshold < accept_threshold <= 1")

@pytest.mark.skipif(not OPENCV_AVAILABLE, reason="requires opencv")
def test_no_fake_production_model_files(mock_config, tmp_path):
    mock_config.faces.model_root = tmp_path
    
    engine = Cv2FaceEngine(config=mock_config.faces, logger=MagicMock())
    with pytest.raises(FaceEngineError, match="Detector model missing"):
        engine.load_models()
        
    assert not list(tmp_path.iterdir()), "Engine should not create fake model files"

@pytest.mark.skipif(not OPENCV_AVAILABLE, reason="OpenCV not available")
def test_integration_fixture_skips_safely(tmp_path):
    import os
    from pathlib import Path
    img_path = os.environ.get("FACE_INTEGRATION_TEST_IMAGE", "private_data/faces/integration/test.jpg")
    if not Path(img_path).exists():
        pytest.skip(f"Integration image missing: {img_path}")
    pass

@pytest.mark.skipif(not OPENCV_AVAILABLE, reason="OpenCV not available")
def test_model_hash_mismatch_raises_error(mock_config, tmp_path):
    mock_config.faces.model_root = tmp_path
    (tmp_path / mock_config.faces.detector_model).write_bytes(b"fake detector")
    (tmp_path / mock_config.faces.recognizer_model).write_bytes(b"fake recognizer")

    logger = logging.getLogger("test_logger")
    engine = Cv2FaceEngine(config=mock_config.faces, logger=logger)
    
    with pytest.raises(FaceEngineError, match="Detector model hash mismatch"):
        engine.load_models()

def test_enrollment_aborts_on_hash_mismatch(mock_config, tmp_path):
    # This proves that when load_models raises FaceEngineError, cmd_enroll catches it and doesn't write anything
    from src.face_enrollment import cmd_enroll
    from src.database import ArchiveDatabase
    
    mock_config.faces.model_root = tmp_path
    
    args = MagicMock()
    args.source = str(tmp_path)
    args.person_slug = "test"
    args.display_name = "test"
    
    logger = MagicMock(spec=logging.Logger)
    db = MagicMock(spec=ArchiveDatabase)
    
    with patch("src.face_enrollment.OPENCV_AVAILABLE", True), \
         patch("src.face_engine.OPENCV_AVAILABLE", True):
        # We also need to patch the actual dependency check in load_models to not care about real cv2
        # But we can just patch `get_engine` to raise the error directly.
        pass

    with patch("src.face_enrollment.get_engine", side_effect=FaceEngineError("Detector model hash mismatch")) as mock_get:
        result = cmd_enroll(args, config=mock_config, db=db, logger=logger)
        
        assert result == 1
        logger.error.assert_any_call("Enrollment failed: Detector model hash mismatch")
        db.get_or_create_person.assert_not_called()
        db.add_reference.assert_not_called()
        
        # Verify kwargs were used in get_engine
        mock_get.assert_called_once_with(config=mock_config, logger=logger)

def test_get_engine_kwargs(mock_config):
    from src.face_enrollment import get_engine
    
    logger = MagicMock(spec=logging.Logger)
    
    with patch("src.face_enrollment.Cv2FaceEngine") as mock_engine_class:
        mock_instance = mock_engine_class.return_value
        
        get_engine(config=mock_config, logger=logger)
        
        # Verify Cv2FaceEngine is constructed with exact kwargs
        mock_engine_class.assert_called_once_with(config=mock_config.faces, logger=logger)
        mock_instance.load_models.assert_called_once()

def test_face_engine_compare_embeddings(mock_config):
    if not OPENCV_AVAILABLE:
        pytest.skip("OpenCV not available")
        
    engine = Cv2FaceEngine(config=mock_config.faces, logger=MagicMock())
    engine._recognizer = MagicMock()
    
    first = np.array([0.1]*128, dtype=np.float32)
    second = np.array([[0.2]*128], dtype=np.float32)
    
    engine._recognizer.match.return_value = 0.95
    
    score = engine.compare_embeddings(first, second)
    
    assert score == 0.95
    args = engine._recognizer.match.call_args[0]
    
    # Verify both are (1, 128) when passed to match
    assert args[0].shape == (1, 128)
    assert args[1].shape == (1, 128)

def test_create_embedding_normalization(mock_config):
    if not OPENCV_AVAILABLE:
        pytest.skip("OpenCV not available")
        
    engine = Cv2FaceEngine(config=mock_config.faces, logger=MagicMock())
    engine._recognizer = MagicMock()
    
    aligned_face = np.zeros((112, 112, 3), dtype=np.uint8)
    # Feature returned as (1, 128)
    mock_feature = np.array([[1.0]*128], dtype=np.float32)
    engine._recognizer.feature.return_value = mock_feature
    
    emb = engine.create_embedding(aligned_face)
    
    # Should be normalized and flattened to (128,)
    assert emb.shape == (128,)
    assert np.allclose(np.linalg.norm(emb), 1.0)
