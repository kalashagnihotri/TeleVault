with open('tests/test_migrations.py', 'a') as f:
    f.write('''
from src.config import Config, AppConfig, TelegramConfig, TelegramTopicsConfig, QueueConfig, SecretsConfig
from pathlib import Path

def create_mock_config():
    return Config(
        app=AppConfig(dry_run=False, database_path=Path(''), log_directory=Path(''), cache_directory=Path(''), private_data_directory=Path('')),
        queue=QueueConfig(incoming_images=Path(''), incoming_videos=Path(''), completed=Path(''), failed=Path(''), stable_seconds=0, scan_interval_seconds=0, cleanup_safety_days=0),
        telegram=TelegramConfig(group_id='-12345', topics=TelegramTopicsConfig(people=1, family_groups=2, travel_nature=3, everyday=6, screenshots_documents=5, videos=8, misc=9), caption_max_length=900, api_mode='hosted', hosted_upload_limit_mb=50, local_upload_limit_mb=2000),
        secrets=SecretsConfig(bot_token='', api_id='', api_hash='')
    )

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
            "INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, discovered_at, updated_at, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ('hash1', 'hash', 'p', 'p', 'image', 1, 1, 'NEEDS_REVIEW', 'now', 'now', "invalid literal for int() with base 10: ''")
        )
        conn.execute("INSERT INTO telegram_archive (media_id, group_id, topic_id, route_key) VALUES (1, '', 'everyday', NULL)")
        
        conn.execute(
            "INSERT INTO upload_attempts (media_id, attempt_type, attempt_started_at) VALUES (1, 'preview', 'now')"
        )
        conn.commit()

    config = create_mock_config()
    db.repair_legacy_routing(config)
    
    with db.connect() as conn:
        archive = conn.execute("SELECT * FROM telegram_archive WHERE media_id = 1").fetchone()
        assert archive['route_key'] == 'everyday'
        assert archive['topic_id'] == '6'
        assert archive['group_id'] == '-12345'
        
        media = conn.execute("SELECT * FROM media WHERE id = 1").fetchone()
        assert media['state'] == 'READY_TO_UPLOAD'
        assert media['error_message'] is None

def test_repair_dry_run_does_nothing(tmp_path, temp_sql_dir):
    db_path = tmp_path / 'dryrun.sqlite'
    db = ArchiveDatabase(db_path)
    db.apply_migrations(temp_sql_dir)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, discovered_at, updated_at, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ('hash2', 'hash', 'p', 'p', 'image', 1, 1, 'NEEDS_REVIEW', 'now', 'now', "invalid literal for int() with base 10: ''")
        )
        conn.execute("INSERT INTO telegram_archive (media_id, group_id, topic_id) VALUES (1, '', 'everyday')")
        conn.commit()
    config = create_mock_config()
    config.app.dry_run = True
    db.repair_legacy_routing(config)
    
    with db.connect() as conn:
        archive = conn.execute("SELECT * FROM telegram_archive WHERE media_id = 1").fetchone()
        assert archive['topic_id'] == 'everyday'
        assert archive['route_key'] is None
''')
