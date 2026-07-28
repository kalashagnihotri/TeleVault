import pytest
import numpy as np
from unittest.mock import MagicMock
from src.face_engine import Cv2FaceEngine
from src.models import ImageFaceAnalysisResult
from src.face_analysis import FaceAnalysisWorker

def test_filtering_logic_tracks_all_faces():
    # Setup mock engine
    mock_config = MagicMock()
    mock_config.faces.minimum_face_size_px = 100
    
    mock_engine = MagicMock()
    # 3 detections: 2 accepted, 1 tiny
    # [x, y, w, h, ...]
    mock_engine.detect_faces.return_value = [
        [0, 0, 150, 150, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99], # accepted
        [0, 0, 50, 50, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99],   # tiny
        [0, 0, 120, 120, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99], # accepted
    ]
    
    mock_engine.align_face.return_value = "aligned"
    mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")
    mock_engine.model_identity.return_value = "modelA"
    
    worker = FaceAnalysisWorker(mock_config, MagicMock(), mock_engine, MagicMock())
    worker.calibration_snapshot = None # forces UNKNOWN_UNCALIBRATED
    
    # Run analyze_image
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    result = worker.analyze_image(dummy_img)
    
    assert result.raw_detections == 3
    assert result.accepted_size == 2
    assert result.ignored_tiny == 1
    assert result.processing_errors == 0
    
    # Output face results should be 3 (1 tiny, 2 uncalibrated)
    assert len(result.face_results) == 3
    
    decisions = [r["decision"] for r in result.face_results]
    assert decisions.count("IGNORED_TINY") == 1
    assert decisions.count("UNKNOWN_UNCALIBRATED") == 2

def test_filtering_logic_zero_faces():
    mock_config = MagicMock()
    mock_engine = MagicMock()
    mock_engine.detect_faces.return_value = []
    
    worker = FaceAnalysisWorker(mock_config, MagicMock(), mock_engine, MagicMock())
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    result = worker.analyze_image(dummy_img)
    
    assert result.raw_detections == 0
    assert result.accepted_size == 0
    assert result.ignored_tiny == 0
    assert len(result.face_results) == 0

def test_filtering_logic_all_tiny():
    mock_config = MagicMock()
    mock_config.faces.minimum_face_size_px = 100
    mock_engine = MagicMock()
    mock_engine.detect_faces.return_value = [
        [0, 0, 50, 50, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]
    ]
    
    worker = FaceAnalysisWorker(mock_config, MagicMock(), mock_engine, MagicMock())
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    result = worker.analyze_image(dummy_img)
    
    assert result.raw_detections == 1
    assert result.accepted_size == 0
    assert result.ignored_tiny == 1
    assert len(result.face_results) == 1
    assert result.face_results[0]["decision"] == "IGNORED_TINY"
