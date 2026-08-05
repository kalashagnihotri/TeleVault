import pytest
import sqlite3
from pathlib import Path
from src.database import ArchiveDatabase
import sys
import numpy as np
from unittest.mock import patch, MagicMock
from src.diagnostic_face_match import main
from src.config import FaceConfig


def test_missing_database_not_created(tmp_path):
    db_path = tmp_path / "missing.sqlite3"
    with pytest.raises(FileNotFoundError):
        ArchiveDatabase(db_path, read_only=True)
    assert not db_path.exists()

def test_missing_parent_folder_not_created(tmp_path):
    db_path = tmp_path / "missing_dir" / "missing.sqlite3"
    with pytest.raises(FileNotFoundError):
        ArchiveDatabase(db_path, read_only=True)
    assert not (tmp_path / "missing_dir").exists()

def test_existing_database_opens_in_ro_and_attempted_writes_fail(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    
    # Create a real DB
    db_write = ArchiveDatabase(db_path)
    with db_write.connect() as conn:
        conn.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY)")
        conn.commit()
        
    assert db_path.exists()
    
    # Open in read_only mode
    db_ro = ArchiveDatabase(db_path, read_only=True)
    
    # Attempted writes fail (transaction)
    with pytest.raises(RuntimeError, match="read-only mode"):
        with db_ro.transaction() as conn:
            pass
            
    # Attempted writes fail (raw connect execution)
    with db_ro.connect() as conn:
        with pytest.raises(sqlite3.OperationalError, match="readonly database"):
            conn.execute("INSERT INTO test_table (id) VALUES (1)")
            
    # Reference and calibration reads work (even if table doesn't exist, it should raise OperationalError rather than read-only error, but let's test if it at least connects)
    # The actual methods get_active_references/calibration just do SELECT.
    with pytest.raises(sqlite3.OperationalError, match="no such table: face_references"):
        db_ro.get_active_references("dummy")

@patch("src.diagnostic_face_match.decode_image_with_exif")
@patch("src.diagnostic_face_match.Cv2FaceEngine")
@patch("src.diagnostic_face_match.FaceAnalysisWorker")
def test_cli_reaches_image_analysis_with_real_ro_db(
    mock_worker_class,
    mock_engine_class,
    mock_decode,
    monkeypatch,
    tmp_path,
    capsys
):
    # Setup dummy database
    db_path = tmp_path / "diagnostic.sqlite3"
    db_write = ArchiveDatabase(db_path)
    db_write.apply_migrations(Path("src/sql")) # Optional, but maybe not needed if we mock FaceAnalysisWorker
    
    monkeypatch.setattr(sys, "argv", ["diagnostic_face_match.py", "--source", "dummy_image.jpg", "--verbose-private"])
    
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
    
    mock_engine_instance = MagicMock()
    mock_engine_class.return_value = mock_engine_instance
    
    mock_worker_instance = MagicMock()
    mock_worker_class.return_value = mock_worker_instance
    
    from src.models import ImageFaceAnalysisResult
    mock_res = ImageFaceAnalysisResult()
    mock_worker_instance.analyze_image.return_value = mock_res
    
    # We patch Path.exists to pass the image check
    original_exists = Path.exists
    def mock_exists(self):
        if str(self) == "dummy_image.jpg":
            return True
        return original_exists(self)
        
    with patch("src.diagnostic_face_match.Path.exists", new=mock_exists):
        # We need to set the config database path to our temporary one
        from src.config import load_config
        original_load_config = load_config
        def mock_load_config():
            cfg = original_load_config()
            cfg.app.database_path = db_path
            return cfg
            
        with patch("src.diagnostic_face_match.load_config", side_effect=mock_load_config):
            main()
            
    mock_worker_instance.analyze_image.assert_called_once()
    
    # Verify it passed a Path (db_path) to ArchiveDatabase
    # The FaceAnalysisWorker constructor args
    args = mock_worker_class.call_args.args
    assert len(args) >= 2
    passed_db = args[1]
    assert isinstance(passed_db, ArchiveDatabase)
    assert passed_db.path == db_path
    assert passed_db.read_only is True

@patch("src.diagnostic_face_match.decode_image_with_exif")
@patch("src.diagnostic_face_match.Cv2FaceEngine")
@patch("src.diagnostic_face_match.setup_logger")
def test_default_errors_do_not_expose_local_paths(mock_logger, mock_engine, mock_decode, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["diagnostic_face_match.py", "--source", "dummy_image.jpg"])
    
    mock_decode.return_value = {
        "image": np.zeros((100, 100, 3), dtype=np.uint8),
    }

    original_exists = Path.exists
    def mock_exists(self):
        if str(self) == "dummy_image.jpg":
            return True
        return original_exists(self)
        
    with patch("src.diagnostic_face_match.Path.exists", new=mock_exists):
        with patch("src.diagnostic_face_match.load_config") as mock_lc:
            mock_cfg = MagicMock()
            # Set a fake database path that doesn't exist
            mock_cfg.app.database_path = Path("/fake/nonexistent/db.sqlite3")
            mock_lc.return_value = mock_cfg
            
            mock_file = MagicMock()
            mock_file.__enter__.return_value.read.return_value = b"fake"
            with patch("builtins.open", return_value=mock_file):
                with pytest.raises(SystemExit):
                    main()
                    
    captured = capsys.readouterr()
    assert "FileNotFoundError" in captured.out
    assert "/fake/nonexistent/db.sqlite3" not in captured.out
    assert "Traceback" not in captured.out
