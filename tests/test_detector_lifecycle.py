import pytest
import numpy as np
from PIL import Image
from unittest.mock import patch, MagicMock
from src.face_engine import Cv2FaceEngine

def test_engine_recreates_detector_on_dimension_change():
    mock_config = MagicMock()
    mock_config.detector_confidence = 0.90
    
    logger = MagicMock()
    engine = Cv2FaceEngine(mock_config, logger)
    engine.detector_path = "dummy.onnx"
    
    # We will mock _create_detector to verify how many times it's called
    mock_detector = MagicMock()
    # Need to simulate the return from detector.detect(image)
    mock_detector.detect.return_value = (1, np.array([[0,0,10,10,0,0,0,0,0,0,0,0,0,0,0.99]]))
    
    engine._create_detector = MagicMock(return_value=mock_detector)
    
    img_100x50 = np.zeros((100, 50, 3), dtype=np.uint8)
    img_100x50_2 = np.zeros((100, 50, 3), dtype=np.uint8)
    img_50x100 = np.zeros((50, 100, 3), dtype=np.uint8)
    
    # 1. First call, creates detector
    res1 = engine.detect_faces(img_100x50)
    assert engine._create_detector.call_count == 1
    engine._create_detector.assert_called_with((50, 100))
    
    # 2. Second call with SAME dimensions, does NOT recreate
    res2 = engine.detect_faces(img_100x50_2)
    assert engine._create_detector.call_count == 1
    
    # 3. Third call with DIFFERENT dimensions, recreates detector
    res3 = engine.detect_faces(img_50x100)
    assert engine._create_detector.call_count == 2
    engine._create_detector.assert_called_with((100, 50))
    
def test_engine_enforces_safe_normalization():
    mock_config = MagicMock()
    engine = Cv2FaceEngine(mock_config, MagicMock())
    engine.detector_path = "dummy.onnx"
    engine._create_detector = MagicMock()
    
    # Invalid dtype
    invalid_dtype = np.zeros((100, 100, 3), dtype=np.float32)
    with pytest.raises(Exception, match="Image must be a 3-channel uint8"):
        engine.detect_faces(invalid_dtype)
        
    # Invalid shape
    invalid_shape = np.zeros((100, 100), dtype=np.uint8)
    with pytest.raises(Exception, match="Image must be a 3-channel uint8"):
        engine.detect_faces(invalid_shape)
        
    invalid_channels = np.zeros((100, 100, 4), dtype=np.uint8)
    with pytest.raises(Exception, match="Image must be a 3-channel uint8"):
        engine.detect_faces(invalid_channels)
