import logging
from pathlib import Path
from unittest.mock import patch

from src.config import Config, AppConfig, QueueConfig, TelegramConfig, TelegramTopicsConfig, SecretsConfig
from src.database import ArchiveDatabase
from src.scanner import QueueScanner

def test_scanner_single_sleep_behavior(tmp_path: Path) -> None:
    # Setup paths
    db_path = tmp_path / "test.sqlite3"
    logs_dir = tmp_path / "logs"
    queue_in = tmp_path / "incoming/images"
    queue_in.mkdir(parents=True)
    
    from tests.conftest import make_test_config
    config = make_test_config(tmp_path)
    config.queue.incoming_images = queue_in
    config.app.database_path = db_path
    
    # Setup DB
    db = ArchiveDatabase(db_path)
    with db.connect() as conn:
        conn.execute("""
        CREATE TABLE media (
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
        )
        """)
        conn.execute("""
        CREATE TABLE telegram_archive (
            media_id INTEGER PRIMARY KEY,
            group_id TEXT NOT NULL,
            topic_id TEXT NOT NULL,
            route_key TEXT
        )
        """)
        conn.commit()

    # Create 3 dummy files
    for i in range(3):
        (queue_in / f"test{i}.jpg").write_text(f"dummy data {i}")
        
    logger = logging.getLogger("test_scanner")
    logger.addHandler(logging.NullHandler())
    
    scanner = QueueScanner(config, db, logger)
    
    with patch("time.sleep") as mock_sleep:
        scanner.scan_once()
        
        # It should sleep exactly ONCE for 1 second, regardless of 3 files
        mock_sleep.assert_called_once_with(1)
        
    with db.connect() as conn:
        count = conn.execute("SELECT count(*) FROM media").fetchone()[0]
    assert count == 3, "Should have successfully reserved all 3 media files."
