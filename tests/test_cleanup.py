import os
import sqlite3
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta

from src.config import load_config, ConfigError
from src.database import ArchiveDatabase
from src.cleanup import ArchiveCleanup, CleanupError
from src.logger import setup_logger

@pytest.fixture
def test_db_path(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    return db_path

@pytest.fixture
def mock_config(tmp_path):
    import yaml
    config_path = tmp_path / "config.yaml"
    config_data = {
        "app": {"database_path": str(tmp_path / "db.sqlite3")},
        "queue": {
            "incoming_images": str(tmp_path / "incoming"),
            "completed": str(tmp_path / "completed")
        },
        "cleanup": {
            "enabled": True,
            "mode": "move",
            "backup_safety_days": 0,
            "verify_hash_before_cleanup": True
        }
    }
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
    return load_config(config_path)

def test_cleanup_disabled_by_default(tmp_path, caplog):
    import yaml
    import logging
    config_path = tmp_path / "config.yaml"
    config_data = {
        "app": {"database_path": str(tmp_path / "db.sqlite3")},
        "queue": {
            "incoming_images": str(tmp_path / "incoming"),
            "completed": str(tmp_path / "completed"),
            "cleanup_safety_days": 10
        }
    }
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
    
    with caplog.at_level(logging.WARNING, logger="telegram_media"):
        config = load_config(config_path)
        
    assert config.cleanup.enabled is False
    assert config.cleanup.backup_safety_days == 10
    
    assert any("DeprecationWarning: 'cleanup' config block is missing" in record.message for record in caplog.records)

def test_verify_hash_before_cleanup_mandatory(tmp_path):
    import yaml
    config_path = tmp_path / "config.yaml"
    config_data = {
        "app": {"database_path": str(tmp_path / "db.sqlite3")},
        "queue": {
            "incoming_images": str(tmp_path / "incoming"),
            "completed": str(tmp_path / "completed")
        },
        "cleanup": {
            "enabled": True,
            "verify_hash_before_cleanup": False
        }
    }
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
    
    with pytest.raises(ConfigError, match="verify_hash_before_cleanup must be True"):
        load_config(config_path)

def test_invalid_path_configuration(tmp_path):
    import yaml
    config_path = tmp_path / "config.yaml"
    config_data = {
        "app": {"database_path": str(tmp_path / "db.sqlite3")},
        "queue": {
            "incoming_images": str(tmp_path / "incoming"),
            "completed": str(tmp_path / "incoming") # Same path!
        },
        "cleanup": {"enabled": True}
    }
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
    
    with pytest.raises(ConfigError):
        load_config(config_path)

def test_same_run_upload_exclusion(test_db_path, mock_config):
    db = ArchiveDatabase(test_db_path)
    db.apply_migrations(Path("sql"))
    
    # insert a BACKED_UP media record with upload_confirmed_at = now
    now = datetime.now(timezone.utc)
    
    with db.connect() as conn:
        cursor = conn.execute("INSERT INTO media (sha256, short_hash, original_path, original_filename, state, media_type, size_bytes, modified_ns, discovered_at, updated_at) VALUES ('hash1', 'sh1', 'path', 'f1', 'BACKED_UP', 'image', 100, 100, ?, ?)", (now.isoformat(), now.isoformat()))
        mid = cursor.lastrowid
        conn.execute("INSERT INTO telegram_archive (media_id, telegram_file_id, original_message_id, upload_confirmed_at) VALUES (?, 'file_id', '123', ?)", (mid, now.isoformat()))
        
    cleanup = ArchiveCleanup(mock_config, db, setup_logger(mock_config))
    
    # Even with 0 safety days, the run_started_at is strictly before upload_confirmed_at because upload happened now, run started 1 sec ago.
    run_started_at = now - timedelta(seconds=1)
    eligible_before = (run_started_at - timedelta(days=mock_config.cleanup.backup_safety_days)).isoformat()
    
    candidates = db.get_cleanup_candidates(eligible_before)
    assert len(candidates) == 0

def test_historical_failure_does_not_block(test_db_path, mock_config):
    db = ArchiveDatabase(test_db_path)
    db.apply_migrations(Path("sql"))
    
    now = datetime.now(timezone.utc)
    upload_time = now - timedelta(days=2)
    
    with db.connect() as conn:
        cursor = conn.execute("INSERT INTO media (sha256, short_hash, original_path, original_filename, state, media_type, size_bytes, modified_ns, discovered_at, updated_at) VALUES ('hash1', 'sh1', 'path', 'f1', 'BACKED_UP', 'image', 100, 100, ?, ?)", (now.isoformat(), now.isoformat()))
        mid = cursor.lastrowid
        conn.execute("INSERT INTO telegram_archive (media_id, telegram_file_id, original_message_id, upload_confirmed_at) VALUES (?, 'file_id', '123', ?)", (mid, upload_time.isoformat()))
        
        # historical failure
        conn.execute("INSERT INTO upload_attempts (media_id, attempt_type, attempt_started_at, attempt_finished_at, outcome) VALUES (?, 'original', ?, ?, 'ERROR')", (mid, upload_time.isoformat(), upload_time.isoformat()))
        
    run_started_at = now
    eligible_before = (run_started_at - timedelta(days=mock_config.cleanup.backup_safety_days)).isoformat()
    
    candidates = db.get_cleanup_candidates(eligible_before)
    assert len(candidates) == 1

def test_uncertain_upload_blocks(test_db_path, mock_config):
    db = ArchiveDatabase(test_db_path)
    db.apply_migrations(Path("sql"))
    
    now = datetime.now(timezone.utc)
    upload_time = now - timedelta(days=2)
    
    with db.connect() as conn:
        cursor = conn.execute("INSERT INTO media (sha256, short_hash, original_path, original_filename, state, media_type, size_bytes, modified_ns, discovered_at, updated_at) VALUES ('hash1', 'sh1', 'path', 'f1', 'BACKED_UP', 'image', 100, 100, ?, ?)", (now.isoformat(), now.isoformat()))
        mid = cursor.lastrowid
        conn.execute("INSERT INTO telegram_archive (media_id, telegram_file_id, original_message_id, upload_confirmed_at) VALUES (?, 'file_id', '123', ?)", (mid, upload_time.isoformat()))
        
        # uncertain attempt
        conn.execute("INSERT INTO upload_attempts (media_id, attempt_type, attempt_started_at, attempt_finished_at, outcome, uncertain_since) VALUES (?, 'original', ?, ?, 'UNCERTAIN', ?)", (mid, upload_time.isoformat(), upload_time.isoformat(), upload_time.isoformat()))
        
    run_started_at = now
    eligible_before = (run_started_at - timedelta(days=mock_config.cleanup.backup_safety_days)).isoformat()
    
    candidates = db.get_cleanup_candidates(eligible_before)
    assert len(candidates) == 0

