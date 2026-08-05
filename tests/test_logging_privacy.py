import logging
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from src.logging_utils import RuntimeOptions, safe_candidate_id, log_private, ProcessingStage
from src.logger import setup_logger

def get_test_config(tmp_path):
    config = MagicMock()
    config.app.log_directory = tmp_path / "test_logs"
    config.app.log_directory.mkdir(parents=True, exist_ok=True)
    return config

def test_safe_candidate_id():
    assert safe_candidate_id("abcdef123456") == "abcdef12"
    assert safe_candidate_id("A B C d e f 1 2 3") == "a b c d "
    assert safe_candidate_id(None, fallback_number=42) == "unhashed-0042"
    assert safe_candidate_id(None) == "unhashed"

def test_setup_logger_isolation(tmp_path):
    cfg = get_test_config(tmp_path)
    logger = setup_logger(cfg, verbose_private=False)
    assert logger.level == logging.INFO
    assert not logger.propagate
    
    # Third party
    assert logging.getLogger("urllib3").level == logging.WARNING
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("telegram").level == logging.WARNING
    assert logging.getLogger("asyncio").level == logging.WARNING

def test_setup_logger_verbose_private(tmp_path):
    cfg = get_test_config(tmp_path)
    logger = setup_logger(cfg, verbose_private=True)
    assert logger.level == logging.DEBUG

def test_log_private(caplog):
    caplog.set_level(logging.DEBUG)
    logger = logging.getLogger("test_private")
    
    log_private(logger, False, "Secret %s", "value")
    assert "Secret value" not in caplog.text
    
    log_private(logger, True, "Secret %s", "value")
    assert "Secret value" in caplog.text

def test_scanner_hash_fallback_logging(caplog):
    caplog.set_level(logging.DEBUG)
    logger = logging.getLogger("test_scanner")
    opts = RuntimeOptions(verbose_private=True)
    
    try:
        raise ValueError("Simulated hash failure")
    except Exception as e:
        candidate_id = safe_candidate_id(None, fallback_number=1)
        logger.error("Candidate [%s] failed: stage=%s error=%s", candidate_id, ProcessingStage.HASH.value, type(e).__name__)
        log_private(logger, opts.verbose_private, "Candidate [%s] private HASH failure: path=%r", candidate_id, "private_path.jpg", exc_info=True)
        
    public_records = [r for r in caplog.records if r.levelno >= logging.INFO]
    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    
    assert len(public_records) == 1
    assert "unhashed-0001" in public_records[0].message
    assert "ValueError" in public_records[0].message
    assert "private_path" not in public_records[0].message
    assert "Simulated hash failure" not in public_records[0].message
    
    assert len(debug_records) == 1
    assert "private_path" in debug_records[0].message
    assert debug_records[0].exc_info is not None

def test_no_fstrings_exposed_in_exception(caplog):
    caplog.set_level(logging.INFO)
    logger = logging.getLogger("test_uploader")
    
    try:
        raise RuntimeError("Secret Token XXXXX")
    except Exception as e:
        short_hash = "abcdef12"
        logger.error("Candidate [%s] failed: stage=%s error=%s", short_hash, ProcessingStage.UPLOAD.value, type(e).__name__)
        
    assert "Secret Token XXXXX" not in caplog.text
    assert "RuntimeError" in caplog.text
