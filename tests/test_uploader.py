import asyncio
import logging
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from src.config import Config, AppConfig, QueueConfig, TelegramConfig, TelegramTopicsConfig, SecretsConfig
from src.database import ArchiveDatabase
from src.telegram_client import TelegramClient, TelegramResult
from src.uploader import ArchiveUploader, ConfigurationError

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

def mock_gen_preview(src, dst):
    dst.write_bytes(b"dummy")
    return True

@pytest.mark.asyncio
async def test_migration(tmp_path: Path):
    db_path = tmp_path / "phase2.sqlite"
    db = ArchiveDatabase(db_path)
    db.apply_migrations(Path("sql"))
    mid = insert_dummy_media(db, tmp_path)
    
    aid = db.start_upload_attempt(mid, "preview", "PREVIEW_UPLOADING", "f.jpg", 100, "123", "0", "timestamp")
    
    with db.connect() as conn:
        count = conn.execute("SELECT count(*) FROM upload_attempts").fetchone()[0]
        assert count == 1

@pytest.mark.asyncio
async def test_preview_retry_resuming_only_preview(test_config, tmp_path: Path):
    db = setup_db(test_config.app.database_path)
    mid = insert_dummy_media(db, tmp_path, state="RETRY_WAIT", retry_stage="preview")
    
    with db.connect() as conn:
        conn.execute("INSERT INTO upload_attempts (media_id, attempt_type, attempt_started_at, next_retry_at) VALUES (?, 'preview', '1999-01-01', '1999-01-01')", (mid,))
        conn.commit()
        
    client = AsyncMock()
    client.send_photo_preview.return_value = TelegramResult(1, {"chat": {"id": 123}, "photo": [{"file_id": "1"}]})
    client.send_original_document.return_value = TelegramResult(2, {"chat": {"id": 123}, "document": {"file_id": "2"}})
    
    uploader = ArchiveUploader(test_config, db, client, logging.getLogger("test"))
    
    with patch("src.uploader.generate_image_preview", side_effect=mock_gen_preview):
        await uploader.upload_once()
        
    assert client.send_photo_preview.call_count == 1
    assert client.send_original_document.call_count == 1
    
    with db.connect() as conn:
        row = conn.execute("SELECT state FROM media WHERE id = ?", (mid,)).fetchone()
        assert row["state"] == "BACKED_UP"

@pytest.mark.asyncio
async def test_original_retry_resuming_only_original(test_config, tmp_path: Path):
    db = setup_db(test_config.app.database_path)
    mid = insert_dummy_media(db, tmp_path, state="RETRY_WAIT", retry_stage="original")
    with db.connect() as conn:
        conn.execute("UPDATE telegram_archive SET preview_message_id = '1' WHERE media_id = ?", (mid,))
        conn.execute("INSERT INTO upload_attempts (media_id, attempt_type, attempt_started_at, next_retry_at) VALUES (?, 'original', '1999-01-01', '1999-01-01')", (mid,))
        conn.commit()
        
    client = AsyncMock()
    client.send_original_document.return_value = TelegramResult(2, {"chat": {"id": 123}, "document": {"file_id": "2"}})
    
    uploader = ArchiveUploader(test_config, db, client, logging.getLogger("test"))
    
    with patch("src.uploader.generate_image_preview", side_effect=mock_gen_preview):
        await uploader.upload_once()
        
    assert client.send_photo_preview.call_count == 0
    assert client.send_original_document.call_count == 1

@pytest.mark.asyncio
async def test_original_only_fallback(test_config, tmp_path: Path):
    db = setup_db(test_config.app.database_path)
    mid = insert_dummy_media(db, tmp_path)
    
    client = AsyncMock()
    client.send_original_document.return_value = TelegramResult(2, {"chat": {"id": 123}, "document": {"file_id": "2"}})
    
    uploader = ArchiveUploader(test_config, db, client, logging.getLogger("test"))
    
    with patch("src.uploader.generate_image_preview", return_value=False):
        await uploader.upload_once()
        
    assert client.send_photo_preview.call_count == 0
    assert client.send_original_document.call_count == 1

@pytest.mark.asyncio
async def test_invalid_topic_record_error(test_config, tmp_path: Path):
    db = setup_db(test_config.app.database_path)
    mid1 = insert_dummy_media(db, tmp_path, index=1)
    mid2 = insert_dummy_media(db, tmp_path, index=2)
    
    client = AsyncMock()
    client.send_photo_preview.side_effect = [
        RuntimeError("message thread not found"),
        TelegramResult(1, {"chat": {"id": 123}, "photo": [{"file_id": "1"}]})
    ]
    client.send_original_document.return_value = TelegramResult(2, {"chat": {"id": 123}, "document": {"file_id": "2"}})
    
    uploader = ArchiveUploader(test_config, db, client, logging.getLogger("test"))
    with patch("src.uploader.generate_image_preview", side_effect=mock_gen_preview):
        await uploader.upload_once()
        
    with db.connect() as conn:
        s1 = conn.execute("SELECT state FROM media WHERE id = ?", (mid1,)).fetchone()["state"]
        s2 = conn.execute("SELECT state FROM media WHERE id = ?", (mid2,)).fetchone()["state"]
        
    assert s1 == "CONFIGURATION_ERROR"
    assert s2 == "BACKED_UP"

@pytest.mark.asyncio
async def test_invalid_token_stops_uploader(test_config, tmp_path: Path):
    db = setup_db(test_config.app.database_path)
    mid = insert_dummy_media(db, tmp_path)
    
    client = AsyncMock()
    client.send_photo_preview.side_effect = RuntimeError("Unauthorized")
    
    uploader = ArchiveUploader(test_config, db, client, logging.getLogger("test"))
    with patch("src.uploader.generate_image_preview", side_effect=mock_gen_preview):
        await uploader.upload_once()
        
    with db.connect() as conn:
        s = conn.execute("SELECT state FROM media WHERE id = ?", (mid,)).fetchone()["state"]
        
    assert s == "CONFIGURATION_ERROR"

@pytest.mark.asyncio
async def test_dry_run_skips_reconciliation(test_config, tmp_path: Path):
    test_config.app.dry_run = True
    db = setup_db(test_config.app.database_path)
    mid = insert_dummy_media(db, tmp_path)
    with db.connect() as conn:
        conn.execute("UPDATE media SET state = 'PREVIEW_UPLOADING' WHERE id = ?", (mid,))
        conn.commit()
        
    client = AsyncMock()
    uploader = ArchiveUploader(test_config, db, client, logging.getLogger("test"))
    await uploader.upload_once()
    
    with db.connect() as conn:
        s = conn.execute("SELECT state FROM media WHERE id = ?", (mid,)).fetchone()["state"]
    assert s == "PREVIEW_UPLOADING"


@pytest.mark.asyncio
async def test_uploader_ignores_backed_up_media(test_config, tmp_path):
    db_path = tmp_path / "test.db"
    db = setup_db(db_path)
    
    logger = MagicMock()
    mock_client = AsyncMock(spec=TelegramClient)
    
    with db.connect() as conn:
        conn.execute(
            f"INSERT INTO media (id, original_path, original_filename, size_bytes, sha256, short_hash, media_type, state, face_state, cleanup_state, modified_ns, discovered_at, updated_at) VALUES (10, 'path10', 'file10', 100, 'hash10', 'hash10', 'image', 'BACKED_UP', 'ANALYZED', 'PENDING', 0, 'now', 'now')"
        )
        # successful upload attempts
        conn.execute(
            "INSERT INTO upload_attempts (media_id, attempt_type, telegram_message_id, outcome, attempt_started_at, attempt_finished_at) VALUES (10, 'preview', 73, 'SUCCESS', 'now', 'now')"
        )
        conn.execute(
            "INSERT INTO upload_attempts (media_id, attempt_type, telegram_message_id, outcome, attempt_started_at, attempt_finished_at) VALUES (10, 'original', 74, 'SUCCESS', 'now', 'now')"
        )
        
    uploader = ArchiveUploader(test_config, db, mock_client, logger)
    await uploader.upload_once()
    
    mock_client.send_photo_preview.assert_not_called()
    mock_client.send_original_document.assert_not_called()
    
    with db.connect() as conn:
        attempts = conn.execute("SELECT attempt_type, telegram_message_id FROM upload_attempts WHERE media_id = 10").fetchall()
        assert len(attempts) == 2
