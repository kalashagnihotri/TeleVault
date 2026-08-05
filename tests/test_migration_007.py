import pytest
import sqlite3
from pathlib import Path
from src.database import ArchiveDatabase

def test_migration_007_fresh_database(tmp_path):
    db_path = tmp_path / 'test.sqlite'
    sql_dir = Path('sql')
    
    db = ArchiveDatabase(db_path)
    db.apply_migrations(sql_dir)
    
    with db.connect() as conn:
        cols = {r['name'] for r in conn.execute('PRAGMA table_info(face_calibrations)').fetchall()}
    
    assert 'individual_strong_support_threshold' in cols

def test_migration_007_existing_database_without_column(tmp_path):
    db_path = tmp_path / 'test.sqlite'
    sql_dir = Path('sql')
    
    # Initialize up to 006
    db = ArchiveDatabase(db_path)
    with db.connect() as conn:
        conn.execute('CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)')
        for sql_file in sorted(sql_dir.glob('*.sql')):
            version = sql_file.stem.split('_')[0]
            if version == '007':
                continue
            conn.executescript(sql_file.read_text(encoding='utf-8'))
            conn.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))", (version,))
        conn.commit()
    
    # Now apply migrations which should trigger 007
    db.apply_migrations(sql_dir)
    
    with db.connect() as conn:
        cols = {r['name'] for r in conn.execute('PRAGMA table_info(face_calibrations)').fetchall()}
        applied = {r['version'] for r in conn.execute('SELECT version FROM schema_migrations').fetchall()}
        
    assert 'individual_strong_support_threshold' in cols
    assert '007' in applied

def test_migration_007_existing_column_idempotent(tmp_path):
    db_path = tmp_path / 'test.sqlite'
    sql_dir = Path('sql')
    
    db = ArchiveDatabase(db_path)
    db.apply_migrations(sql_dir)
    
    # Run it again, should be idempotent
    db.apply_migrations(sql_dir)
    
    with db.connect() as conn:
        cols = {r['name'] for r in conn.execute('PRAGMA table_info(face_calibrations)').fetchall()}
        applied = {r['version'] for r in conn.execute('SELECT version FROM schema_migrations').fetchall()}
        
    assert 'individual_strong_support_threshold' in cols
    assert '007' in applied
    
def test_migration_007_incompatible_column_causes_failure(tmp_path):
    db_path = tmp_path / 'test.sqlite'
    sql_dir = Path('sql')
    
    # Initialize up to 006
    db = ArchiveDatabase(db_path)
    with db.connect() as conn:
        conn.execute('CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)')
        for sql_file in sorted(sql_dir.glob('*.sql')):
            version = sql_file.stem.split('_')[0]
            if version == '007':
                continue
            conn.executescript(sql_file.read_text(encoding='utf-8'))
            conn.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))", (version,))
        # Manually add column to simulate a user modifying the DB
        conn.execute('ALTER TABLE face_calibrations ADD COLUMN individual_strong_support_threshold REAL NOT NULL DEFAULT 0.0')
        conn.commit()
        
    # Apply migrations, it should adopt 007 without duplicate error
    db.apply_migrations(sql_dir)
    
    with db.connect() as conn:
        cols = {r['name'] for r in conn.execute('PRAGMA table_info(face_calibrations)').fetchall()}
        applied = {r['version'] for r in conn.execute('SELECT version FROM schema_migrations').fetchall()}
        
    assert 'individual_strong_support_threshold' in cols
    assert '007' in applied
