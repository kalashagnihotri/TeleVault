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

def test_move_db_commit_failure_remains_reconcilable(fs_setup):
    config, db, incoming, completed = fs_setup
    config.cleanup.mode = "move"
    
    mid, source_path, file_hash = create_mock_media(db, incoming, "crash_test.jpg")
    
    now = datetime.now(timezone.utc).isoformat()
    with db.connect() as conn:
        conn.execute("UPDATE telegram_archive SET upload_confirmed_at = ?, telegram_file_id = 'file', original_message_id = 'msg' WHERE media_id = ?", (now, mid))
        
    cleanup = ArchiveCleanup(config, db, setup_logger(config))
    
    original_finish = db.finish_cleanup_attempt
    raised = False
    
    def mock_finish(media_id, attempt_id, outcome, state, *args, **kwargs):
        nonlocal raised
        if outcome == "SUCCESS" and state == "CLEANED" and not raised:
            raised = True
            raise RuntimeError("simulated cleanup DB commit failure")
        return original_finish(media_id, attempt_id, outcome, state, *args, **kwargs)
        
    db.finish_cleanup_attempt = mock_finish
    
    run_time = datetime.now(timezone.utc).isoformat()
    cleanup.run_cleanup(run_time)
    
    assert not source_path.exists()
    dest_path = completed / "crash_test.jpg"
    assert dest_path.exists()
    assert sha256_file(dest_path) == file_hash
    
    with db.connect() as conn:
        state = conn.execute("SELECT cleanup_state FROM media WHERE id = ?", (mid,)).fetchone()["cleanup_state"]
        assert state == "IN_PROGRESS", f"Expected IN_PROGRESS, got {state}"
        
    db.finish_cleanup_attempt = original_finish
    
    cleanup.reconcile_in_progress()
    
    with db.connect() as conn:
        state = conn.execute("SELECT cleanup_state FROM media WHERE id = ?", (mid,)).fetchone()["cleanup_state"]
        assert state == "CLEANED"
        
    assert dest_path.exists()
    assert not source_path.exists()

def test_existing_destination_db_commit_failure_remains_reconcilable(fs_setup):
    config, db, incoming, completed = fs_setup
    config.cleanup.mode = "move"
    
    mid, source_path, file_hash = create_mock_media(db, incoming, "existing_crash.jpg")
    
    # Destination already exists with identical hash
    dest_path = completed / "existing_crash.jpg"
    dest_path.write_text("test data")
    
    now = datetime.now(timezone.utc).isoformat()
    with db.connect() as conn:
        conn.execute("UPDATE telegram_archive SET upload_confirmed_at = ?, telegram_file_id = 'file', original_message_id = 'msg' WHERE media_id = ?", (now, mid))
        
    cleanup = ArchiveCleanup(config, db, setup_logger(config))
    
    original_finish = db.finish_cleanup_attempt
    raised = False
    
    def mock_finish(media_id, attempt_id, outcome, state, *args, **kwargs):
        nonlocal raised
        if outcome == "SUCCESS" and state == "CLEANED" and not raised:
            raised = True
            raise RuntimeError("simulated cleanup DB commit failure")
        return original_finish(media_id, attempt_id, outcome, state, *args, **kwargs)
        
    db.finish_cleanup_attempt = mock_finish
    
    run_time = datetime.now(timezone.utc).isoformat()
    cleanup.run_cleanup(run_time)
    
    assert not source_path.exists()
    assert dest_path.exists()
    assert sha256_file(dest_path) == file_hash
    
    with db.connect() as conn:
        state = conn.execute("SELECT cleanup_state FROM media WHERE id = ?", (mid,)).fetchone()["cleanup_state"]
        assert state == "IN_PROGRESS", f"Expected IN_PROGRESS, got {state}"
        
    db.finish_cleanup_attempt = original_finish
    
    cleanup.reconcile_in_progress()
    
    with db.connect() as conn:
        state = conn.execute("SELECT cleanup_state FROM media WHERE id = ?", (mid,)).fetchone()["cleanup_state"]
        assert state == "CLEANED"
        
    assert dest_path.exists()
    assert sha256_file(dest_path) == file_hash
    assert not source_path.exists()

def test_source_changed_is_never_moved_or_deleted(fs_setup):
    config, db, incoming, completed = fs_setup
    config.cleanup.mode = "move"
    
    mid, source_path, file_hash = create_mock_media(db, incoming, "changed_test.jpg")
    source_path.write_text("modified contents")
    
    cleanup = ArchiveCleanup(config, db, setup_logger(config))
    run_time = datetime.now(timezone.utc).isoformat()
    cleanup.run_cleanup(run_time)
    
    assert source_path.exists()
    assert source_path.read_text() == "modified contents"
    dest_path = completed / "changed_test.jpg"
    assert not dest_path.exists()
    
    with db.connect() as conn:
        state = conn.execute("SELECT cleanup_state FROM media WHERE id = ?", (mid,)).fetchone()["cleanup_state"]
        assert state == "SOURCE_CHANGED"
        
        attempt_count = conn.execute("SELECT COUNT(*) as cnt FROM cleanup_attempts WHERE media_id = ?", (mid,)).fetchone()["cnt"]
        assert attempt_count == 0

def test_missing_source_is_recorded_without_destination_change(fs_setup):
    config, db, incoming, completed = fs_setup
    config.cleanup.mode = "move"
    
    mid, source_path, file_hash = create_mock_media(db, incoming, "missing_test.jpg")
    source_path.unlink()
    
    cleanup = ArchiveCleanup(config, db, setup_logger(config))
    run_time = datetime.now(timezone.utc).isoformat()
    cleanup.run_cleanup(run_time)
    
    dest_path = completed / "missing_test.jpg"
    assert not dest_path.exists()
    
    with db.connect() as conn:
        state = conn.execute("SELECT cleanup_state FROM media WHERE id = ?", (mid,)).fetchone()["cleanup_state"]
        assert state == "SOURCE_MISSING"
        
        attempt_count = conn.execute("SELECT COUNT(*) as cnt FROM cleanup_attempts WHERE media_id = ?", (mid,)).fetchone()["cnt"]
        assert attempt_count == 0

def test_cross_volume_copy_verifies_hash_before_source_removal(fs_setup, monkeypatch):
    config, db, incoming, completed = fs_setup
    config.cleanup.mode = "move"
    
    mid, source_path, file_hash = create_mock_media(db, incoming, "cross_volume.jpg")
    
    import os
    original_rename = os.rename
    
    def mock_rename(src, dst):
        if str(src) == str(source_path):
            raise OSError("Simulated cross-volume boundary")
        return original_rename(src, dst)
        
    monkeypatch.setattr(os, "rename", mock_rename)
    
    cleanup = ArchiveCleanup(config, db, setup_logger(config))
    run_time = datetime.now(timezone.utc).isoformat()
    cleanup.run_cleanup(run_time)
    
    assert not source_path.exists()
    dest_path = completed / "cross_volume.jpg"
    assert dest_path.exists()
    assert sha256_file(dest_path) == file_hash
    
    tmp_files = list(completed.glob("*.tmp"))
    assert len(tmp_files) == 0
    
    with db.connect() as conn:
        state = conn.execute("SELECT cleanup_state FROM media WHERE id = ?", (mid,)).fetchone()["cleanup_state"]
        assert state == "CLEANED"
        
        attempt = conn.execute("SELECT outcome FROM cleanup_attempts WHERE media_id = ? ORDER BY attempt_id DESC LIMIT 1", (mid,)).fetchone()
        assert attempt["outcome"] == "SUCCESS"

def test_cross_volume_hash_mismatch_preserves_source(fs_setup, monkeypatch):
    config, db, incoming, completed = fs_setup
    config.cleanup.mode = "move"
    
    mid, source_path, file_hash = create_mock_media(db, incoming, "cross_hash_fail.jpg")
    
    import os, shutil
    original_rename = os.rename
    original_copy2 = shutil.copy2
    
    def mock_rename(src, dst):
        if str(src) == str(source_path):
            raise OSError("Simulated cross-volume boundary")
        return original_rename(src, dst)
        
    def mock_copy2(src, dst):
        original_copy2(src, dst)
        Path(dst).write_text("corrupted copy")
        
    monkeypatch.setattr(os, "rename", mock_rename)
    monkeypatch.setattr(shutil, "copy2", mock_copy2)
    
    cleanup = ArchiveCleanup(config, db, setup_logger(config))
    run_time = datetime.now(timezone.utc).isoformat()
    cleanup.run_cleanup(run_time)
    
    assert source_path.exists()
    assert sha256_file(source_path) == file_hash
    dest_path = completed / "cross_hash_fail.jpg"
    assert not dest_path.exists()
    
    tmp_files = list(completed.glob("*.tmp"))
    assert len(tmp_files) == 0
    
    with db.connect() as conn:
        state = conn.execute("SELECT cleanup_state FROM media WHERE id = ?", (mid,)).fetchone()["cleanup_state"]
        assert state == "FAILED"
        
        attempt = conn.execute("SELECT outcome, error_code FROM cleanup_attempts WHERE media_id = ? ORDER BY attempt_id DESC LIMIT 1", (mid,)).fetchone()
        assert attempt["outcome"] == "ERROR"
        assert attempt["error_code"] == "move_error"

def test_reconcile_destination_hash_mismatch_needs_review(fs_setup):
    config, db, incoming, completed = fs_setup
    
    mid, source_path, file_hash = create_mock_media(db, incoming, "recon_hash_fail.jpg")
    
    dest_path = completed / "recon_hash_fail.jpg"
    dest_path.write_text("wrong contents")
    source_path.unlink()
    
    now = datetime.now(timezone.utc).isoformat()
    with db.connect() as conn:
        conn.execute("UPDATE media SET cleanup_state = 'IN_PROGRESS' WHERE id = ?", (mid,))
        conn.execute("INSERT INTO cleanup_attempts (media_id, mode, source_path, destination_path, attempt_started_at) VALUES (?, 'move', ?, ?, ?)", (mid, str(source_path), str(dest_path), now))
        
    cleanup = ArchiveCleanup(config, db, setup_logger(config))
    cleanup.reconcile_in_progress()
    
    with db.connect() as conn:
        state = conn.execute("SELECT cleanup_state FROM media WHERE id = ?", (mid,)).fetchone()["cleanup_state"]
        assert state == "NEEDS_REVIEW"
        
        attempt = conn.execute("SELECT outcome, error_code FROM cleanup_attempts WHERE media_id = ? ORDER BY attempt_id DESC LIMIT 1", (mid,)).fetchone()
        assert attempt["outcome"] == "ERROR"
        assert attempt["error_code"] == "hash_mismatch"
        
    assert dest_path.exists()
    assert dest_path.read_text() == "wrong contents"

def test_reconcile_both_paths_missing_marks_source_missing(fs_setup):
    config, db, incoming, completed = fs_setup
    
    mid, source_path, file_hash = create_mock_media(db, incoming, "recon_missing.jpg")
    dest_path = completed / "recon_missing.jpg"
    
    source_path.unlink()
    
    now = datetime.now(timezone.utc).isoformat()
    with db.connect() as conn:
        conn.execute("UPDATE media SET cleanup_state = 'IN_PROGRESS' WHERE id = ?", (mid,))
        conn.execute("INSERT INTO cleanup_attempts (media_id, mode, source_path, destination_path, attempt_started_at) VALUES (?, 'move', ?, ?, ?)", (mid, str(source_path), str(dest_path), now))
        
    cleanup = ArchiveCleanup(config, db, setup_logger(config))
    cleanup.reconcile_in_progress()
    
    with db.connect() as conn:
        state = conn.execute("SELECT cleanup_state FROM media WHERE id = ?", (mid,)).fetchone()["cleanup_state"]
        assert state == "SOURCE_MISSING"
        
        attempt = conn.execute("SELECT outcome, error_code FROM cleanup_attempts WHERE media_id = ? ORDER BY attempt_id DESC LIMIT 1", (mid,)).fetchone()
        assert attempt["outcome"] == "ERROR"
        assert attempt["error_code"] == "missing"

def test_move_failure_preserves_source(fs_setup, monkeypatch):
    config, db, incoming, completed = fs_setup
    config.cleanup.mode = "move"
    
    mid, source_path, file_hash = create_mock_media(db, incoming, "move_fail.jpg")
    
    import os, shutil
    
    def mock_rename(src, dst):
        raise OSError("Simulated atomic rename failure")
        
    def mock_copy2(src, dst):
        raise OSError("Simulated cross-volume copy failure")
        
    monkeypatch.setattr(os, "rename", mock_rename)
    monkeypatch.setattr(shutil, "copy2", mock_copy2)
    
    cleanup = ArchiveCleanup(config, db, setup_logger(config))
    run_time = datetime.now(timezone.utc).isoformat()
    cleanup.run_cleanup(run_time)
    
    assert source_path.exists()
    assert sha256_file(source_path) == file_hash
    dest_path = completed / "move_fail.jpg"
    assert not dest_path.exists()
    
    with db.connect() as conn:
        state = conn.execute("SELECT cleanup_state FROM media WHERE id = ?", (mid,)).fetchone()["cleanup_state"]
        assert state == "FAILED"
        
        attempt = conn.execute("SELECT outcome, error_code FROM cleanup_attempts WHERE media_id = ? ORDER BY attempt_id DESC LIMIT 1", (mid,)).fetchone()
        assert attempt["outcome"] == "ERROR"
        assert attempt["error_code"] == "move_error"

def test_run_cleanup_applies_backup_safety_window_internally(fs_setup):
    config, db, incoming, completed = fs_setup
    config.cleanup.mode = "move"
    config.cleanup.backup_safety_days = 7
    
    mid, source_path, file_hash = create_mock_media(db, incoming, "safety_test.jpg")
    
    now_dt = datetime.now(timezone.utc)
    # Upload confirmed 1 day ago
    upload_time = now_dt - timedelta(days=1)
    
    with db.connect() as conn:
        conn.execute("UPDATE telegram_archive SET upload_confirmed_at = ?, telegram_file_id = 'file', original_message_id = 'msg' WHERE media_id = ?", (upload_time.isoformat(), mid))
        conn.execute("UPDATE media SET cleanup_state = 'ELIGIBLE' WHERE id = ?", (mid,))
        
    cleanup = ArchiveCleanup(config, db, setup_logger(config))
    cleanup.run_cleanup(now_dt.isoformat())
    
    assert source_path.exists()
    dest_path = completed / "safety_test.jpg"
    assert not dest_path.exists()
    
    with db.connect() as conn:
        state = conn.execute("SELECT cleanup_state FROM media WHERE id = ?", (mid,)).fetchone()["cleanup_state"]
        assert state == "ELIGIBLE"
        
        attempt_count = conn.execute("SELECT COUNT(*) as cnt FROM cleanup_attempts WHERE media_id = ?", (mid,)).fetchone()["cnt"]
        assert attempt_count == 0

def test_run_cleanup_with_old_upload_succeeds(fs_setup):
    config, db, incoming, completed = fs_setup
    config.cleanup.mode = "move"
    config.cleanup.backup_safety_days = 7
    
    mid, source_path, file_hash = create_mock_media(db, incoming, "old_upload.jpg")
    
    now_dt = datetime.now(timezone.utc)
    # Upload confirmed 8 days ago
    upload_time = now_dt - timedelta(days=8)
    
    with db.connect() as conn:
        conn.execute("UPDATE telegram_archive SET upload_confirmed_at = ?, telegram_file_id = 'file', original_message_id = 'msg' WHERE media_id = ?", (upload_time.isoformat(), mid))
        conn.execute("UPDATE media SET cleanup_state = 'ELIGIBLE' WHERE id = ?", (mid,))
        
    cleanup = ArchiveCleanup(config, db, setup_logger(config))
    cleanup.run_cleanup(now_dt.isoformat())
    
    assert not source_path.exists()
    dest_path = completed / "old_upload.jpg"
    assert dest_path.exists()
    
    with db.connect() as conn:
        state = conn.execute("SELECT cleanup_state FROM media WHERE id = ?", (mid,)).fetchone()["cleanup_state"]
        assert state == "CLEANED"
        
        attempt_count = conn.execute("SELECT COUNT(*) as cnt FROM cleanup_attempts WHERE media_id = ?", (mid,)).fetchone()["cnt"]
        assert attempt_count > 0

def test_get_cleanup_candidates_receives_correct_timestamp(fs_setup, monkeypatch):
    config, db, incoming, completed = fs_setup
    config.cleanup.mode = "move"
    config.cleanup.backup_safety_days = 7
    
    cleanup = ArchiveCleanup(config, db, setup_logger(config))
    
    now_dt = datetime.now(timezone.utc)
    
    captured_timestamp = None
    original_get = db.get_cleanup_candidates
    
    def mock_get(eligible_before_utc):
        nonlocal captured_timestamp
        captured_timestamp = eligible_before_utc
        return []
        
    monkeypatch.setattr(db, "get_cleanup_candidates", mock_get)
    
    cleanup.run_cleanup(now_dt.isoformat())
    
    expected = (now_dt - timedelta(days=7)).isoformat()
    assert captured_timestamp == expected
