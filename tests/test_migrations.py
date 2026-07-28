import pytest
import sqlite3
from pathlib import Path
from src.database import ArchiveDatabase

@pytest.fixture
def temp_sql_dir(tmp_path: Path):
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    (sql_dir / "001_initial.sql").write_text("""
        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sha256 TEXT NOT NULL UNIQUE,
            short_hash TEXT NOT NULL,
            original_path TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            media_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            modified_ns INTEGER NOT NULL,
            state TEXT NOT NULL,
            discovered_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            date_taken TEXT,
            has_gps INTEGER DEFAULT 0,
            location_label TEXT,
            people_json TEXT,
            labels_json TEXT
        );
        CREATE TABLE IF NOT EXISTS telegram_archive (
            media_id INTEGER PRIMARY KEY,
            group_id TEXT NOT NULL,
            topic_id TEXT NOT NULL,
            preview_message_id TEXT,
            original_message_id TEXT,
            telegram_file_id TEXT,
            upload_confirmed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS processing_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_id INTEGER,
            event_type TEXT NOT NULL,
            event_time TEXT NOT NULL,
            detail_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(media_id) REFERENCES media(id)
        );
        CREATE INDEX IF NOT EXISTS idx_media_state ON media(state);
        CREATE INDEX IF NOT EXISTS idx_media_updated_at ON media(updated_at);
    """)
    (sql_dir / "002_phase3_uploads.sql").write_text("""
        ALTER TABLE telegram_archive ADD COLUMN retry_stage TEXT;

        CREATE TABLE IF NOT EXISTS upload_attempts (
            attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_id INTEGER NOT NULL,
            attempt_type TEXT NOT NULL CHECK(attempt_type IN ('preview', 'original', 'original_only')),
            attempt_started_at TEXT NOT NULL,
            attempt_finished_at TEXT,
            request_filename TEXT,
            request_size INTEGER,
            group_id TEXT,
            topic_id TEXT,
            last_http_status INTEGER,
            outcome TEXT,
            telegram_message_id TEXT,
            error_code TEXT,
            error_message TEXT,
            next_retry_at TEXT,
            uncertain_since TEXT,
            FOREIGN KEY(media_id) REFERENCES media(id)
        );

        CREATE INDEX IF NOT EXISTS idx_upload_attempts_media_id ON upload_attempts(media_id);
    """)
    (sql_dir / "003_route_key.sql").write_text("""
        ALTER TABLE telegram_archive ADD COLUMN route_key TEXT;
    """)
    return sql_dir

def test_fresh_database_receives_all_migrations(tmp_path, temp_sql_dir):
    db_path = tmp_path / "fresh.sqlite"
    db = ArchiveDatabase(db_path)
    
    db.apply_migrations(temp_sql_dir)
    
    with db.connect() as conn:
        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        assert applied == {"001", "002", "003"}
        
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "media" in tables
        assert "telegram_archive" in tables
        assert "upload_attempts" in tables

def test_existing_phase2_database_upgrades_cleanly(tmp_path, temp_sql_dir):
    db_path = tmp_path / "phase2.sqlite"
    db = ArchiveDatabase(db_path)
    
    # Simulate legacy apply_schema for 001
    script_001 = (temp_sql_dir / "001_initial.sql").read_text()
    with db.connect() as conn:
        conn.executescript(script_001)
        
    db.apply_migrations(temp_sql_dir)
    
    with db.connect() as conn:
        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        assert applied == {"001", "002", "003"}
        
        columns = [r["name"] for r in conn.execute("PRAGMA table_info(telegram_archive)")]
        assert "retry_stage" in columns
        
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "upload_attempts" in tables

def test_database_with_002_already_applied_is_adopted(tmp_path, temp_sql_dir):
    db_path = tmp_path / "full_002.sqlite"
    db = ArchiveDatabase(db_path)
    
    # Simulate legacy apply_schema for 001 and 002
    script_001 = (temp_sql_dir / "001_initial.sql").read_text()
    script_002 = (temp_sql_dir / "002_phase3_uploads.sql").read_text()
    with db.connect() as conn:
        conn.executescript(script_001)
        conn.executescript(script_002)
        
    # Running apply_migrations should not crash with "duplicate column retry_stage"
    db.apply_migrations(temp_sql_dir)
    
    with db.connect() as conn:
        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        assert applied == {"001", "002", "003"}

def test_partially_applied_002_is_repaired(tmp_path, temp_sql_dir):
    db_path = tmp_path / "partial.sqlite"
    db = ArchiveDatabase(db_path)
    
    # Apply 001 and ONLY the ALTER TABLE part of 002
    script_001 = (temp_sql_dir / "001_initial.sql").read_text()
    with db.connect() as conn:
        conn.executescript(script_001)
        conn.execute("ALTER TABLE telegram_archive ADD COLUMN retry_stage TEXT;")
        conn.commit()
        
    db.apply_migrations(temp_sql_dir)
    
    with db.connect() as conn:
        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        assert applied == {"001", "002", "003"}
        
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "upload_attempts" in tables

def test_start_application_twice(tmp_path, temp_sql_dir):
    db_path = tmp_path / "twice.sqlite"
    db = ArchiveDatabase(db_path)
    
    # First run
    db.apply_migrations(temp_sql_dir)
    
    # Second run should skip everything, not throw error
    db.apply_migrations(temp_sql_dir)
    
    with db.connect() as conn:
        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        assert applied == {"001", "002", "003"}

def test_existing_records_remain_unchanged(tmp_path, temp_sql_dir):
    db_path = tmp_path / "records.sqlite"
    db = ArchiveDatabase(db_path)
    
    # Setup legacy Phase 2
    script_001 = (temp_sql_dir / "001_initial.sql").read_text()
    with db.connect() as conn:
        conn.executescript(script_001)
        conn.execute(
            "INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, discovered_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("hash1", "hash", "p", "p", "image", 1, 1, "READY_TO_UPLOAD", "now", "now")
        )
        conn.execute("INSERT INTO telegram_archive (media_id, group_id, topic_id) VALUES (1, 'g1', 't1')")
        conn.commit()
        
    # Apply migrations
    db.apply_migrations(temp_sql_dir)
    
    with db.connect() as conn:
        media = conn.execute("SELECT * FROM media").fetchone()
        assert media["sha256"] == "hash1"
        assert media["state"] == "READY_TO_UPLOAD"
        
        archive = conn.execute("SELECT * FROM telegram_archive").fetchone()
        assert archive["group_id"] == "g1"
        assert archive["retry_stage"] is None

def test_partially_applied_002_missing_columns_is_repaired(tmp_path, temp_sql_dir):
    db_path = tmp_path / "partial_cols.sqlite"
    db = ArchiveDatabase(db_path)
    
    script_001 = (temp_sql_dir / "001_initial.sql").read_text()
    with db.connect() as conn:
        conn.executescript(script_001)
        conn.execute("ALTER TABLE telegram_archive ADD COLUMN retry_stage TEXT;")
        # Create upload_attempts with missing columns
        conn.executescript("""
            CREATE TABLE upload_attempts (
                attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                media_id INTEGER NOT NULL,
                attempt_type TEXT NOT NULL,
                attempt_started_at TEXT NOT NULL
            );
        """)
        conn.commit()
        
    db.apply_migrations(temp_sql_dir)
    
    with db.connect() as conn:
        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        assert applied == {"001", "002", "003"}
        
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(upload_attempts)").fetchall()}
        assert "uncertain_since" in columns
        assert "error_message" in columns
        assert len(columns) == 16

from src.config import Config, AppConfig, TelegramConfig, TelegramTopicsConfig, QueueConfig, SecretsConfig
from pathlib import Path

def create_mock_config(tmp_path: Path):
    from tests.conftest import make_test_config
    return make_test_config(tmp_path)

def test_legacy_routing_repair_updates_route_key_and_state(tmp_path, temp_sql_dir):
    db_path = tmp_path / 'repair.sqlite'
    db = ArchiveDatabase(db_path)
    
    script_001 = (temp_sql_dir / '001_initial.sql').read_text()
    script_002 = (temp_sql_dir / '002_phase3_uploads.sql').read_text()
    script_003 = (temp_sql_dir / '003_route_key.sql').read_text()
    with db.connect() as conn:
        conn.executescript(script_001)
        conn.executescript(script_002)
        conn.executescript(script_003)
        
        conn.execute(
            "INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, discovered_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ('hash1', 'hash', 'p', 'p', 'image', 1, 1, 'NEEDS_REVIEW', 'now', 'now')
        )
        conn.execute("INSERT INTO telegram_archive (media_id, group_id, topic_id, route_key) VALUES (1, '', 'everyday', NULL)")
        
        conn.execute(
            "INSERT INTO upload_attempts (media_id, attempt_type, attempt_started_at) VALUES (1, 'preview', 'now')"
        )
        conn.commit()

    config = create_mock_config(tmp_path)
    db.repair_legacy_routing(config)
    
    with db.connect() as conn:
        archive = conn.execute("SELECT * FROM telegram_archive WHERE media_id = 1").fetchone()
        assert archive['route_key'] == 'everyday'
        assert archive['topic_id'] == '6'
        assert archive['group_id'] == '-12345'
        
        media = conn.execute("SELECT * FROM media WHERE id = 1").fetchone()
        assert media['state'] == 'READY_TO_UPLOAD'

def test_repair_dry_run_does_nothing(tmp_path, temp_sql_dir):
    db_path = tmp_path / 'dryrun.sqlite'
    db = ArchiveDatabase(db_path)
    db.apply_migrations(temp_sql_dir)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, discovered_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ('hash2', 'hash', 'p', 'p', 'image', 1, 1, 'NEEDS_REVIEW', 'now', 'now')
        )
        conn.execute("INSERT INTO telegram_archive (media_id, group_id, topic_id) VALUES (1, '', 'everyday')")
        conn.commit()
    config = create_mock_config(tmp_path)
    config.app.dry_run = True
    db.repair_legacy_routing(config)
    
    with db.connect() as conn:
        archive = conn.execute("SELECT * FROM telegram_archive WHERE media_id = 1").fetchone()
        assert archive['topic_id'] == 'everyday'
        assert archive['route_key'] is None
