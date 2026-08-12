import pytest
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.database import ArchiveDatabase

# We will run the requeue script using run_module or subprocess, but the best way
# is to import main and mock sys.argv

def run_requeue(argv):
    with patch("sys.argv", argv):
        import scripts.requeue_face_analysis as rq
        rq.main()

def setup_db_for_requeue(db_path: Path):
    db = ArchiveDatabase(db_path)
    db.apply_migrations(Path("sql"))
    
    conn = db.connect()
    
    conn.execute("INSERT INTO media (id, original_path, original_filename, media_type, cleanup_state, state, face_state, sha256, short_hash, size_bytes, modified_ns, discovered_at, updated_at) VALUES (1, 'fake1.jpg', 'fake1.jpg', 'image', 'PENDING', 'ACTIVE', 'SUCCESS', 'h1', 's1', 1, 1, '2026-08-01', '2026-08-01')")
    conn.execute("INSERT INTO face_analysis_attempts (media_id, analysis_version, outcome, started_at, analysis_key, model_identity, reference_set_hash) VALUES (1, 3, 'SUCCESS', '2026-08-01', 'k', 'm', 'r')")
    
    conn.execute("INSERT INTO media (id, original_path, original_filename, media_type, cleanup_state, state, face_state, sha256, short_hash, size_bytes, modified_ns, discovered_at, updated_at) VALUES (2, 'fake2.jpg', 'fake2.jpg', 'image', 'PENDING', 'ACTIVE', 'SUCCESS', 'h2', 's2', 1, 1, '2026-08-01', '2026-08-01')")
    conn.execute("INSERT INTO face_analysis_attempts (media_id, analysis_version, outcome, started_at, analysis_key, model_identity, reference_set_hash) VALUES (2, 5, 'SUCCESS', '2026-08-01', 'k', 'm', 'r')")
    
    conn.execute("INSERT INTO media (id, original_path, original_filename, media_type, cleanup_state, state, face_state, sha256, short_hash, size_bytes, modified_ns, discovered_at, updated_at) VALUES (3, 'fake3.jpg', 'fake3.jpg', 'image', 'COMPLETED', 'ACTIVE', 'SUCCESS', 'h3', 's3', 1, 1, '2026-08-01', '2026-08-01')")
    conn.execute("INSERT INTO face_analysis_attempts (media_id, analysis_version, outcome, started_at, analysis_key, model_identity, reference_set_hash) VALUES (3, 3, 'SUCCESS', '2026-08-01', 'k', 'm', 'r')")
    
    conn.execute("INSERT INTO media (id, original_path, original_filename, media_type, cleanup_state, state, face_state, sha256, short_hash, size_bytes, modified_ns, discovered_at, updated_at) VALUES (4, 'fake4.jpg', 'fake4.jpg', 'video', 'PENDING', 'ACTIVE', 'SUCCESS', 'h4', 's4', 1, 1, '2026-08-01', '2026-08-01')")
    
    conn.commit()
    conn.close()
    return db

def test_requeue_dry_run(tmp_path, capsys):
    db_path = tmp_path / "test.sqlite3"
    setup_db_for_requeue(db_path)
    
    # Touch files so they exist
    (tmp_path / "fake1.jpg").touch()
    (tmp_path / "fake2.jpg").touch()
    (tmp_path / "fake3.jpg").touch()
    
    with patch("scripts.requeue_face_analysis.load_config") as mock_load:
        config = MagicMock()
        config.app.database_path = db_path
        config.app.log_directory = tmp_path
        mock_load.return_value = config
        
        with patch("scripts.requeue_face_analysis.Path.is_file", return_value=True):
            run_requeue(["requeue_face_analysis.py"])
            
    out, err = capsys.readouterr()
    
    assert "Mode            : DRY-RUN" in out
    assert "Scanned         : 3" in out # 3 images
    assert "Already Current : 1" in out # media_id 2 has version 5
    assert "Cleaned         : 1" in out # media_id 3 is COMPLETED
    assert "Eligible        : 1" in out # media_id 1
    
    db = ArchiveDatabase(db_path)
    conn = db.connect()
    state = conn.execute("SELECT face_state FROM media WHERE id = 1").fetchone()["face_state"]
    conn.close()
    assert state == "SUCCESS" # Dry-run did not change it

def test_requeue_commit(tmp_path, capsys):
    db_path = tmp_path / "test.sqlite3"
    setup_db_for_requeue(db_path)
    
    with patch("scripts.requeue_face_analysis.load_config") as mock_load:
        config = MagicMock()
        config.app.database_path = db_path
        config.app.log_directory = tmp_path
        mock_load.return_value = config
        
        with patch("scripts.requeue_face_analysis.Path.is_file", return_value=True):
            run_requeue(["requeue_face_analysis.py", "--commit"])
            
    out, err = capsys.readouterr()
    
    assert "Mode            : COMMIT" in out
    assert "Eligible        : 1" in out # media_id 1
    assert "Requeued        : 1" in out
    
    db = ArchiveDatabase(db_path)
    conn = db.connect()
    state = conn.execute("SELECT face_state FROM media WHERE id = 1").fetchone()["face_state"]
    conn.close()
    if state != "PENDING":
        print(out)
        print(err)
    assert state == "PENDING" # Updated!
