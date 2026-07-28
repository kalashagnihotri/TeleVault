from src.config import Config, AppConfig, TelegramConfig, TelegramTopicsConfig, QueueConfig, SecretsConfig
from pathlib import Path
from src.database import ArchiveDatabase

def create_mock_config(tmp_path: Path):
    from tests.conftest import make_test_config
    return make_test_config(tmp_path)

def test_ready_to_upload_has_null_group_and_topic_ids(tmp_path):
    db_path = tmp_path / 'scanner_regression.sqlite'
    db = ArchiveDatabase(db_path)
    db.apply_migrations(Path("sql"))
    
    # Simulate scanner reserving and updating metadata
    now = "2026-07-27T12:00:00Z"
    mid = db.reserve_media("hashx", "shorth", "p", "p", "image", 1, 1, "RESERVED", now)
    
    db.update_metadata(mid, None, 0, "Misc", "[]", "[]", "everyday", "READY_TO_UPLOAD", now)
    
    with db.connect() as conn:
        archive = conn.execute("SELECT * FROM telegram_archive WHERE media_id = ?", (mid,)).fetchone()
        
        # Verify route_key is properly set
        assert archive['route_key'] == 'everyday'
        
        # Verify NO empty strings are stored, must be strictly NULL
        assert archive['group_id'] is None
        assert archive['topic_id'] is None
