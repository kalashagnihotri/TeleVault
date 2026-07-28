import os
import shutil
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta

from src.config import load_config
from src.database import ArchiveDatabase
from src.cleanup import ArchiveCleanup
from src.logger import setup_logger
from src.hashing import sha256_file

@pytest.fixture
def fs_setup(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    incoming = tmp_path / "incoming"
    completed = tmp_path / "completed"
    incoming.mkdir()
    completed.mkdir()
    
    import yaml
    config_path = tmp_path / "config.yaml"
    config_data = {
        "app": {"database_path": str(db_path), "dry_run": False},
        "queue": {
            "incoming_images": str(incoming),
            "completed": str(completed)
        },
        "cleanup": {
            "enabled": True,
            "mode": "move",
            "backup_safety_days": 0,
            "verify_hash_before_cleanup": True,
            "confirm_permanent_delete": True
        }
    }
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
        
    config = load_config(config_path)
    db = ArchiveDatabase(db_path)
    db.apply_migrations(Path("sql"))
    
    return config, db, incoming, completed

def create_mock_media(db, incoming_dir, filename, content="test data"):
    file_path = incoming_dir / filename
    file_path.write_text(content)
    file_hash = sha256_file(file_path)
    
    now = datetime.now(timezone.utc)
    upload_time = now - timedelta(days=1)
    
    with db.connect() as conn:
        cursor = conn.execute(
            "INSERT INTO media (sha256, short_hash, original_path, original_filename, state, media_type, size_bytes, modified_ns, discovered_at, updated_at) VALUES (?, ?, ?, ?, 'BACKED_UP', 'image', 100, 100, ?, ?)",
            (file_hash, file_hash[:8], str(file_path), filename, now.isoformat(), now.isoformat())
        )
        mid = cursor.lastrowid
        conn.execute("INSERT INTO telegram_archive (media_id, telegram_file_id, original_message_id, upload_confirmed_at) VALUES (?, 'file_id', '123', ?)", (mid, upload_time.isoformat()))
        conn.execute("UPDATE media SET cleanup_state = 'ELIGIBLE' WHERE id = ?", (mid,))
        
    return mid, file_path, file_hash

def test_same_volume_move_success(fs_setup):
    config, db, incoming, completed = fs_setup
    mid, source_path, file_hash = create_mock_media(db, incoming, "test1.jpg")
    
    cleanup = ArchiveCleanup(config, db, setup_logger(config))
    run_time = datetime.now(timezone.utc).isoformat()
    cleanup.run_cleanup(run_time)
    
    assert not source_path.exists()
    dest_path = completed / "test1.jpg"
    assert dest_path.exists()
    assert sha256_file(dest_path) == file_hash
    
    with db.connect() as conn:
        state = conn.execute("SELECT cleanup_state FROM media WHERE id = ?", (mid,)).fetchone()["cleanup_state"]
        assert state == "CLEANED"
        
        attempt = conn.execute("SELECT outcome FROM cleanup_attempts WHERE media_id = ?", (mid,)).fetchone()["outcome"]
        assert attempt == "SUCCESS"

def test_dry_run_verification(fs_setup):
    config, db, incoming, completed = fs_setup
    config.app.dry_run = True # Enable dry run
    mid, source_path, file_hash = create_mock_media(db, incoming, "test_dry.jpg")
    
    cleanup = ArchiveCleanup(config, db, setup_logger(config))
    run_time = datetime.now(timezone.utc).isoformat()
    cleanup.run_cleanup(run_time)
    
    assert source_path.exists()
    assert not (completed / "test_dry.jpg").exists()
    
    with db.connect() as conn:
        state = conn.execute("SELECT cleanup_state FROM media WHERE id = ?", (mid,)).fetchone()["cleanup_state"]
        assert state == "ELIGIBLE"
        attempts = conn.execute("SELECT COUNT(*) FROM cleanup_attempts").fetchone()[0]
        assert attempts == 0

def test_destination_exists_same_hash(fs_setup):
    config, db, incoming, completed = fs_setup
    mid, source_path, file_hash = create_mock_media(db, incoming, "duplicate.jpg")
    
    dest_path = completed / "duplicate.jpg"
    dest_path.write_text("test data") # Same content
    
    cleanup = ArchiveCleanup(config, db, setup_logger(config))
    run_time = datetime.now(timezone.utc).isoformat()
    cleanup.run_cleanup(run_time)
    
    assert not source_path.exists() # Source should be removed
    assert dest_path.exists()
    
    with db.connect() as conn:
        state = conn.execute("SELECT cleanup_state FROM media WHERE id = ?", (mid,)).fetchone()["cleanup_state"]
        assert state == "CLEANED"
        attempt = conn.execute("SELECT mode FROM cleanup_attempts WHERE media_id = ?", (mid,)).fetchone()["mode"]
        assert attempt == "move_collision"

def test_destination_exists_different_hash_fallback(fs_setup):
    config, db, incoming, completed = fs_setup
    mid, source_path, file_hash = create_mock_media(db, incoming, "collision.jpg", content="new data")
    
    dest_path = completed / "collision.jpg"
    dest_path.write_text("old data") # Different content
    
    cleanup = ArchiveCleanup(config, db, setup_logger(config))
    run_time = datetime.now(timezone.utc).isoformat()
    cleanup.run_cleanup(run_time)
    
    assert not source_path.exists()
    assert dest_path.exists()
    assert dest_path.read_text() == "old data" # Did not overwrite
    
    short_hash = file_hash[:8]
    fallback_path = completed / f"collision_{short_hash}.jpg"
    assert fallback_path.exists()
    assert fallback_path.read_text() == "new data"
    
def test_delete_mode(fs_setup):
    config, db, incoming, completed = fs_setup
    config.cleanup.mode = "delete"
    mid, source_path, file_hash = create_mock_media(db, incoming, "delete_me.jpg")
    
    cleanup = ArchiveCleanup(config, db, setup_logger(config))
    run_time = datetime.now(timezone.utc).isoformat()
    cleanup.run_cleanup(run_time)
    
    assert not source_path.exists()
    
    with db.connect() as conn:
        state = conn.execute("SELECT cleanup_state FROM media WHERE id = ?", (mid,)).fetchone()["cleanup_state"]
        assert state == "CLEANED"
        attempt = conn.execute("SELECT mode FROM cleanup_attempts WHERE media_id = ?", (mid,)).fetchone()["mode"]
        assert attempt == "delete"

def test_startup_reconciliation_crash_both_exist(fs_setup):
    config, db, incoming, completed = fs_setup
    mid, source_path, file_hash = create_mock_media(db, incoming, "crash.jpg")
    dest_path = completed / "crash.jpg"
    dest_path.write_text("test data") # Simulate copy succeeded but crash before unlink
    
    now = datetime.now(timezone.utc).isoformat()
    with db.connect() as conn:
        conn.execute("UPDATE media SET cleanup_state = 'IN_PROGRESS' WHERE id = ?", (mid,))
        conn.execute("INSERT INTO cleanup_attempts (media_id, mode, source_path, destination_path, attempt_started_at) VALUES (?, 'move', ?, ?, ?)", (mid, str(source_path), str(dest_path), now))
        
    cleanup = ArchiveCleanup(config, db, setup_logger(config))
    cleanup.reconcile_in_progress()
    
    assert not source_path.exists() # Reconciliation should have removed source
    assert dest_path.exists()
    
    with db.connect() as conn:
        state = conn.execute("SELECT cleanup_state FROM media WHERE id = ?", (mid,)).fetchone()["cleanup_state"]
        assert state == "CLEANED"

def test_startup_reconciliation_crash_source_missing(fs_setup):
    config, db, incoming, completed = fs_setup
    mid, source_path, file_hash = create_mock_media(db, incoming, "crash_done.jpg")
    dest_path = completed / "crash_done.jpg"
    dest_path.write_text("test data") 
    source_path.unlink() # Simulate fully moved but crash before DB update
    
    now = datetime.now(timezone.utc).isoformat()
    with db.connect() as conn:
        conn.execute("UPDATE media SET cleanup_state = 'IN_PROGRESS' WHERE id = ?", (mid,))
        conn.execute("INSERT INTO cleanup_attempts (media_id, mode, source_path, destination_path, attempt_started_at) VALUES (?, 'move', ?, ?, ?)", (mid, str(source_path), str(dest_path), now))
        
    cleanup = ArchiveCleanup(config, db, setup_logger(config))
    cleanup.reconcile_in_progress()
    
    with db.connect() as conn:
        state = conn.execute("SELECT cleanup_state FROM media WHERE id = ?", (mid,)).fetchone()["cleanup_state"]
        assert state == "CLEANED"
