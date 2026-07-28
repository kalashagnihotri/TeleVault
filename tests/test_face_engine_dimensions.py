import pytest
from unittest.mock import patch, MagicMock
from src.face_engine import Cv2FaceEngine
import numpy as np

def test_detector_input_size_updates():
    # Verify portrait and landscape dimensions are updated before every detection
    mock_config = MagicMock()
    logger = MagicMock()
    
    engine = Cv2FaceEngine(mock_config, logger)
    engine._detector = MagicMock()
    engine.detector_path = "mock_path"
    
    # Portrait image (height=100, width=50)
    portrait_img = np.zeros((100, 50, 3), dtype=np.uint8)
    engine._detector_input_size = (10, 10)
    
    mock_detector = MagicMock()
    mock_detector.detect.return_value = (None, [])
    engine._create_detector = MagicMock(return_value=mock_detector)
    engine.detect_faces(portrait_img)
    engine._create_detector.assert_called_with((50, 100))
    
    # Landscape image (height=50, width=100)
    landscape_img = np.zeros((50, 100, 3), dtype=np.uint8)
    
    engine.detect_faces(landscape_img)
    engine._create_detector.assert_called_with((100, 50))

def test_engine_detect_faces_unpacking():
    mock_config = MagicMock()
    engine = Cv2FaceEngine(mock_config, MagicMock())
    engine._detector = MagicMock()
    
    # Simulate FaceDetectorYN returning a tuple: (status, numpy array of faces)
    # The array is typically shape (N, 15)
    import numpy as np
    mock_faces = np.array([
        [0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99],
        [50, 50, 80, 80, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.88]
    ])
    engine._detector.detect.return_value = (1, mock_faces)
    engine._detector_input_size = (100, 100)
    
    mock_img = np.zeros((100, 100, 3), dtype=np.uint8)
    result = engine.detect_faces(mock_img)
    
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0][2] == 100
    assert result[1][2] == 80
