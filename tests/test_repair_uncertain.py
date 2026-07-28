from src.database import ArchiveDatabase
from src.config import Config, AppConfig, TelegramConfig, TelegramTopicsConfig, SecretsConfig
from pathlib import Path

def create_mock_config(tmp_path: Path):
    from tests.conftest import make_test_config
    return make_test_config(tmp_path)

def test_repair_does_not_hide_uncertain_attempts(tmp_path):
    db_path = tmp_path / 'repair_uncertain.sqlite'
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

        conn.execute(
            "INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, discovered_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ('hash3', 'hash3', 'p', 'p', 'image', 1, 1, 'NEEDS_REVIEW', 'now', 'now')
        )
        conn.execute("INSERT INTO telegram_archive (media_id, group_id, topic_id, route_key) VALUES (1, '', 'everyday', NULL)")

        # Attempt 1: Routing error
        conn.execute(
            "INSERT INTO upload_attempts (media_id, attempt_type, attempt_started_at, error_message) VALUES (1, 'preview', 'now', 'invalid literal for int()')"
        )
        # Attempt 2: Uncertain (has uncertain_since)
        conn.execute(
            "INSERT INTO upload_attempts (media_id, attempt_type, attempt_started_at, uncertain_since) VALUES (1, 'original', 'now', 'now')"
        )
        conn.commit()

    config = create_mock_config(tmp_path)
    db.repair_legacy_routing(config)

    with db.connect() as conn:
        media = conn.execute("SELECT * FROM media WHERE id = 1").fetchone()
        assert media['state'] == 'NEEDS_REVIEW', "Record should remain in NEEDS_REVIEW because of the uncertain attempt"
