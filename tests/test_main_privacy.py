import pytest
import sys
import logging
from unittest.mock import patch, MagicMock

from src.main import run_pipeline, cli
from src.logging_utils import RuntimeOptions

@pytest.mark.asyncio
async def test_run_pipeline_privacy_leak():
    logger = logging.getLogger("test_privacy")
    logger.setLevel(logging.DEBUG)
    
    class CaptureHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []
        def emit(self, record):
            self.records.append(record)
            
    handler = CaptureHandler()
    logger.addHandler(handler)
    
    mock_config = MagicMock()
    mock_opts = RuntimeOptions(verbose_private=False)
    
    # Force an exception to trigger the exception block
    with patch("src.main.ArchiveDatabase", side_effect=TypeError("Strings must be encoded before hashing")):
        result = await run_pipeline(mock_config, logger, mock_opts)
        
    assert result == 1
    
    info_text = "\n".join(r.getMessage() for r in handler.records if r.levelno >= logging.INFO)
    debug_text = "\n".join(r.getMessage() for r in handler.records if r.levelno == logging.DEBUG)
    
    # Public assertions
    assert "Application failed: stage=INITIALIZATION error=TypeError" in info_text
    assert "Traceback" not in info_text
    assert "Strings must be encoded before hashing" not in info_text
    assert sys.executable not in info_text
    assert "J:\\" not in info_text
    assert "G:\\" not in info_text
    
    # Private assertions should be empty because verbose_private=False
    assert "Traceback" not in debug_text
    assert sys.executable not in debug_text

@pytest.mark.asyncio
async def test_run_pipeline_privacy_leak_verbose_private():
    logger = logging.getLogger("test_privacy_verbose")
    logger.setLevel(logging.DEBUG)
    
    class CaptureHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []
        def emit(self, record):
            self.records.append(record)
            
    handler = CaptureHandler()
    logger.addHandler(handler)
    
    mock_config = MagicMock()
    mock_opts = RuntimeOptions(verbose_private=True)
    
    with patch("src.main.ArchiveDatabase", side_effect=TypeError("Strings must be encoded before hashing")):
        result = await run_pipeline(mock_config, logger, mock_opts)
        
    assert result == 1
    
    info_text = "\n".join(r.getMessage() for r in handler.records if r.levelno >= logging.INFO)
    debug_text = "\n".join(r.getMessage() for r in handler.records if r.levelno == logging.DEBUG)
    
    # Public assertions remain identical
    assert "Application failed: stage=INITIALIZATION error=TypeError" in info_text
    assert "Traceback" not in info_text
    assert "Strings must be encoded before hashing" not in info_text
    assert sys.executable not in info_text
    assert "J:\\" not in info_text
    assert "G:\\" not in info_text
    
    # Private assertions show tracebacks
    assert "Traceback" in debug_text or any(r.exc_info for r in handler.records if r.levelno == logging.DEBUG)

def test_cli_catches_initialization_errors(capsys):
    with patch("src.main.main", side_effect=Exception("Config missing")):
        result = cli()
        
    assert result == 1
    captured = capsys.readouterr()
    assert "Application failed during initialization." in captured.err
    assert "Config missing" not in captured.err
    assert "Traceback" not in captured.err

@pytest.mark.asyncio
async def test_run_pipeline_model_hashes_privacy():
    logger = logging.getLogger("test_model_privacy")
    logger.setLevel(logging.DEBUG)
    
    class CaptureHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []
        def emit(self, record):
            self.records.append(record)
            
    handler = CaptureHandler()
    logger.addHandler(handler)
    
    mock_config = MagicMock()
    mock_config.app.dry_run = True
    mock_opts = RuntimeOptions(verbose_private=False)
    
    # We want to mock OPENCV_AVAILABLE to True and Cv2FaceEngine to capture what it does
    with patch("src.face_engine.OPENCV_AVAILABLE", True), \
         patch("src.face_engine.Cv2FaceEngine") as MockEngine, \
         patch("src.main.ArchiveDatabase") as MockDB:
        
        mock_engine_instance = MockEngine.return_value
        mock_engine_instance.detector_hash = "8f2383e4" + "a" * 56
        mock_engine_instance.recognizer_hash = "0ba9fbfa" + "b" * 56
        mock_engine_instance.model_identity.return_value = "YuNet_8f2383e4-SFace_0ba9fbfa-cv2"
        
        # Prevent it from crashing or running the actual pipeline
        MockDB.return_value = MagicMock()
        
        result = await run_pipeline(mock_config, logger, mock_opts)
        
    info_text = "\n".join(r.getMessage() for r in handler.records if r.levelno >= logging.INFO)
    debug_text = "\n".join(r.getMessage() for r in handler.records if r.levelno == logging.DEBUG)
    
    # Public assertions
    assert "SHA256: 8f2383e4" in info_text
    assert "SHA256: 0ba9fbfa" in info_text
    assert "8f2383e4" + "a" * 56 not in info_text
    assert "0ba9fbfa" + "b" * 56 not in info_text
    assert "Model Identity: YuNet_8f2383e4-SFace_0ba9fbfa-cv2" in info_text
    
    # Private assertions should be empty because verbose_private=False
    assert "Detector full SHA256" not in debug_text
    assert "Recognizer full SHA256" not in debug_text

@pytest.mark.asyncio
async def test_run_pipeline_model_hashes_privacy_verbose():
    logger = logging.getLogger("test_model_privacy_verbose")
    logger.setLevel(logging.DEBUG)
    
    class CaptureHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []
        def emit(self, record):
            self.records.append(record)
            
    handler = CaptureHandler()
    logger.addHandler(handler)
    
    mock_config = MagicMock()
    mock_config.app.dry_run = True
    mock_opts = RuntimeOptions(verbose_private=True)
    
    with patch("src.face_engine.OPENCV_AVAILABLE", True), \
         patch("src.face_engine.Cv2FaceEngine") as MockEngine, \
         patch("src.main.ArchiveDatabase") as MockDB:
        
        mock_engine_instance = MockEngine.return_value
        mock_engine_instance.detector_hash = "8f2383e4" + "a" * 56
        mock_engine_instance.recognizer_hash = "0ba9fbfa" + "b" * 56
        mock_engine_instance.model_identity.return_value = "YuNet_8f2383e4-SFace_0ba9fbfa-cv2"
        
        # Prevent it from crashing or running the actual pipeline
        MockDB.return_value = MagicMock()
        
        result = await run_pipeline(mock_config, logger, mock_opts)
        
    info_text = "\n".join(r.getMessage() for r in handler.records if r.levelno >= logging.INFO)
    debug_text = "\n".join(r.getMessage() for r in handler.records if r.levelno == logging.DEBUG)
    
    # Public assertions remain identical
    assert "SHA256: 8f2383e4" in info_text
    assert "SHA256: 0ba9fbfa" in info_text
    assert "8f2383e4" + "a" * 56 not in info_text
    assert "0ba9fbfa" + "b" * 56 not in info_text
    assert "Model Identity: YuNet_8f2383e4-SFace_0ba9fbfa-cv2" in info_text
    
    # Private assertions show full hashes
    assert f"Detector full SHA256: {'8f2383e4' + 'a' * 56}" in debug_text
    assert f"Recognizer full SHA256: {'0ba9fbfa' + 'b' * 56}" in debug_text
