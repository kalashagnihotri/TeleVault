import pytest
import sqlite3
from pathlib import Path
from src.database import ArchiveDatabase

def test_recover_failed_original_uploads_caption_bug(tmp_path):
    db_path = tmp_path / 'recover.sqlite'
    db = ArchiveDatabase(db_path)

    script_001 = (Path("sql") / '001_initial.sql').read_text()
    script_002 = (Path("sql") / '002_phase3_uploads.sql').read_text()
    script_003 = (Path("sql") / '003_route_key.sql').read_text()
    script_004 = (Path("sql") / '004_nullable_route_ids.sql').read_text()
    with db.connect() as conn:
        conn.executescript(script_001)
        conn.executescript(script_002)
        conn.executescript(script_003)
        conn.executescript(script_004)

        # Create record in NEEDS_REVIEW that failed on caption TypeError
        conn.execute(
            "INSERT INTO media (id, sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, discovered_at, updated_at, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (1, 'h1', 'sh1', 'p', 'p', 'image', 1, 1, 'NEEDS_REVIEW', 'now', 'now', "unexpected keyword argument 'caption'")
        )
        # Add telegram_archive with preview_message_id
        conn.execute(
            "INSERT INTO telegram_archive (media_id, preview_message_id) VALUES (1, '100')"
        )
        # Add upload_attempt showing the error
        conn.execute(
            "INSERT INTO upload_attempts (media_id, attempt_type, attempt_started_at, error_message) VALUES (1, 'original', 'now', 'unexpected keyword argument ''caption''')"
        )

        # Create record in NEEDS_REVIEW with same error but also uncertain_since
        conn.execute(
            "INSERT INTO media (id, sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, discovered_at, updated_at, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (2, 'h2', 'sh2', 'p2', 'p2', 'image', 1, 1, 'NEEDS_REVIEW', 'now', 'now', "unexpected keyword argument 'caption'")
        )
        conn.execute(
            "INSERT INTO telegram_archive (media_id, preview_message_id) VALUES (2, '101')"
        )
        conn.execute(
            "INSERT INTO upload_attempts (media_id, attempt_type, attempt_started_at, error_message, uncertain_since) VALUES (2, 'original', 'now', 'unexpected keyword argument ''caption''', 'now')"
        )
        conn.commit()

    db.recover_failed_original_uploads()

    with db.connect() as conn:
        m1 = conn.execute("SELECT state, error_code, error_message FROM media WHERE id = 1").fetchone()
        assert m1["state"] == "PREVIEW_CONFIRMED"
        assert m1["error_code"] is None
        assert m1["error_message"] is None

        m2 = conn.execute("SELECT state FROM media WHERE id = 2").fetchone()
        assert m2["state"] == "NEEDS_REVIEW", "Should not recover uncertain record"
