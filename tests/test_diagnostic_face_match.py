import sys
import numpy as np
from unittest.mock import patch, MagicMock

import pytest

from src.diagnostic_face_match import main
from src.models import ImageFaceAnalysisResult
from src.config import FaceConfig


@patch("src.diagnostic_face_match.decode_image_with_exif")
@patch("src.diagnostic_face_match.Cv2FaceEngine")
@patch("src.diagnostic_face_match.FaceAnalysisWorker")
@patch("src.diagnostic_face_match.ArchiveDatabase")
def test_diagnostic_face_match_smoke(
    mock_db,
    mock_worker_class,
    mock_engine_class,
    mock_decode,
    monkeypatch
):
    # Mock CLI arguments
    monkeypatch.setattr(sys, "argv", ["diagnostic_face_match.py", "--source", "dummy_image.jpg"])
    
    # Mock image decode
    mock_decode.return_value = {
        "image": np.zeros((100, 100, 3), dtype=np.uint8),
        "raw_width": 100,
        "raw_height": 100,
        "normalized_width": 100,
        "normalized_height": 100,
        "exif_orientation": 1,
        "was_normalized": False
    }
    
    # Mock FaceEngine
    mock_engine_instance = MagicMock()
    mock_engine_class.return_value = mock_engine_instance
    
    # Mock FaceAnalysisWorker
    mock_worker_instance = MagicMock()
    mock_worker_class.return_value = mock_worker_instance
    mock_res = ImageFaceAnalysisResult()
    mock_worker_instance.analyze_image.return_value = mock_res
    
    # We must patch Path.exists so the source check passes
    with patch("src.diagnostic_face_match.Path.exists", return_value=True):
        # We must also patch the open for the hash, or just run with --verbose-private to skip hash calculation
        monkeypatch.setattr(sys, "argv", ["diagnostic_face_match.py", "--source", "dummy_image.jpg", "--verbose-private"])
        main()
        
    # Verify Cv2FaceEngine was constructed with config.faces and logger
    mock_engine_class.assert_called_once()
    kwargs = mock_engine_class.call_args.kwargs
    assert "config" in kwargs
    assert isinstance(kwargs["config"], FaceConfig)
    assert "logger" in kwargs
    assert kwargs["logger"] is not None
    assert kwargs["logger"].name == "diagnostic"
    
    # Verify models loaded successfully
    mock_engine_instance.load_models.assert_called_once()
    
    # Verify reached face analysis
    mock_worker_instance.analyze_image.assert_called_once()
