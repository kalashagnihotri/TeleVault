import asyncio
import logging
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, AsyncMock

from src.config import Config, AppConfig, QueueConfig, TelegramConfig, TelegramTopicsConfig, SecretsConfig
from src.database import ArchiveDatabase
from src.telegram_client import TelegramResult
from src.uploader import ArchiveUploader

@pytest.fixture
def test_config(tmp_path: Path):
    from tests.conftest import make_test_config
    config = make_test_config(tmp_path)
    config.app.cache_directory.mkdir(parents=True, exist_ok=True)
    return config

def setup_db(db_path: Path):
    db = ArchiveDatabase(db_path)
    db.apply_migrations(Path("sql"))
    return db

def insert_dummy_media(db: ArchiveDatabase, tmp_path: Path, state="READY_TO_UPLOAD", retry_stage=None, index=0):
    now = datetime.now(timezone.utc).isoformat()
    p = tmp_path / f"path_{index}.jpg"
    p.write_bytes(b"dummy original")
    
    mid = db.reserve_media(f"sha256_{index}", "shorth", str(p), p.name, "image", 1024, 0, state, now)
    db.update_metadata(mid, None, 0, "Misc", "[]", "[]", "misc", state, now)
    with db.connect() as conn:
        conn.execute("UPDATE telegram_archive SET group_id = '123' WHERE media_id = ?", (mid,))
        if retry_stage:
            conn.execute("UPDATE telegram_archive SET retry_stage = ? WHERE media_id = ?", (retry_stage, mid))
        conn.commit()
    return mid

@pytest.mark.asyncio
async def test_original_document_caption_and_reply_logic(test_config, tmp_path: Path):
    db = setup_db(test_config.app.database_path)
    
    # 1. Normal flow: Preview succeeds -> Original omits caption, includes reply_to
    mid1 = insert_dummy_media(db, tmp_path, index=1)
    # 2. Original-only fallback: Preview fails -> Original includes caption, omits reply_to
    mid2 = insert_dummy_media(db, tmp_path, index=2)
    
    client = AsyncMock()
    client.send_photo_preview.return_value = TelegramResult(100, {"chat": {"id": 123}, "photo": [{"file_id": "1"}]})
    client.send_original_document.return_value = TelegramResult(101, {"chat": {"id": 123}, "document": {"file_id": "2"}})
    
    uploader = ArchiveUploader(test_config, db, client, logging.getLogger("test"))
    
    def mock_gen_preview_logic(src, dst):
        if "path_2" in str(src):
            return False # Fail for mid2
        dst.write_bytes(b"dummy")
        return True # Succeed for mid1
        
    with patch("src.uploader.generate_image_preview", side_effect=mock_gen_preview_logic):
        await uploader.upload_once()
        
    assert client.send_original_document.call_count == 2
    
    # Call 1 (for mid1): has reply_to, caption is None
    call_args_1 = client.send_original_document.call_args_list[0].kwargs
    assert call_args_1["reply_to_message_id"] == 100
    assert call_args_1["caption"] is None
    
    # Call 2 (for mid2): no reply_to (None), caption is populated
    call_args_2 = client.send_original_document.call_args_list[1].kwargs
    assert call_args_2["reply_to_message_id"] is None
    assert call_args_2["caption"] is not None
    assert "path_2.jpg" in call_args_2["caption"]

    with db.connect() as conn:
        s1 = conn.execute("SELECT state FROM media WHERE id = ?", (mid1,)).fetchone()["state"]
        s2 = conn.execute("SELECT state FROM media WHERE id = ?", (mid2,)).fetchone()["state"]
        
    assert s1 == "BACKED_UP"
    assert s2 == "BACKED_UP"
