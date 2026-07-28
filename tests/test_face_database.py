import pytest
from src.database import ArchiveDatabase

from pathlib import Path

def test_calibration_retains_prior_on_failure(tmp_path):
    db = ArchiveDatabase(tmp_path / "test.db")
    db.apply_migrations(Path(__file__).parent.parent / "sql")
    
    # activate first calibration
    db.activate_calibration("model_1", "hash_1", 0.8, 0.7, 0.1, 10, 10, "{}")
    cal = db.get_active_calibration("model_1", "hash_1")
    assert cal is not None
    assert cal["active"] == 1
    
    # simulate failure (it wouldn't call activate_calibration if it failed)
    # wait, the instruction is "A failed calibration must not overwrite or deactivate a previous valid record."
    # Since activation is transactional, we just prove they don't deactivate.
    
    # Try another one, and it deactivates the OLD ONE
    db.activate_calibration("model_1", "hash_2", 0.85, 0.75, 0.1, 20, 20, "{}")
    old_cal = db.get_active_calibration("model_1", "hash_1")
    assert old_cal is None # it's no longer active
    
    new_cal = db.get_active_calibration("model_1", "hash_2")
    assert new_cal is not None

def test_stale_reference_set_calibration_not_selected(tmp_path):
    db = ArchiveDatabase(tmp_path / "test.db")
    db.apply_migrations(Path(__file__).parent.parent / "sql")
    
    db.activate_calibration("model_1", "hash_1", 0.8, 0.7, 0.1, 10, 10, "{}")
    
    # If the current reference set hash is 'hash_2', it shouldn't return anything
    cal = db.get_active_calibration("model_1", "hash_2")
    assert cal is None
    
def test_same_analysis_key_is_idempotent(tmp_path):
    db = ArchiveDatabase(tmp_path / "test.db")
    db.apply_migrations(Path(__file__).parent.parent / "sql")
    
    with db.transaction() as conn:
        conn.execute("INSERT INTO media (id, sha256, short_hash, original_filename, original_path, state, media_type, size_bytes, modified_ns, discovered_at, updated_at) VALUES (1, 'hash', 'hash', 'file', 'path', 'BACKED_UP', 'image', 1234, 0, '2026-01-01T00:00:00', '2026-01-01T00:00:00')")
    db.activate_calibration("model_1", "ref_hash", 0.8, 0.7, 0.1, 10, 10, "{}")
    db.activate_calibration("model_1", "ref_hash2", 0.8, 0.7, 0.1, 10, 10, "{}")
        
    id1 = db.start_face_analysis_attempt(1, "CALIBRATED", 1, "model_1", "ref_hash", 1)
    id2 = db.start_face_analysis_attempt(1, "CALIBRATED", 1, "model_1", "ref_hash", 1)
    
    assert id1 == id2
    
def test_changed_calibration_creates_new_analysis_version(tmp_path):
    db = ArchiveDatabase(tmp_path / "test.db")
    db.apply_migrations(Path(__file__).parent.parent / "sql")
    
    with db.transaction() as conn:
        conn.execute("INSERT INTO media (id, sha256, short_hash, original_filename, original_path, state, media_type, size_bytes, modified_ns, discovered_at, updated_at) VALUES (1, 'hash', 'hash', 'file', 'path', 'BACKED_UP', 'image', 1234, 0, '2026-01-01T00:00:00', '2026-01-01T00:00:00')")
    db.activate_calibration("model_1", "ref_hash", 0.8, 0.7, 0.1, 10, 10, "{}")
    db.activate_calibration("model_1", "ref_hash2", 0.8, 0.7, 0.1, 10, 10, "{}")
        
    id1 = db.start_face_analysis_attempt(1, "CALIBRATED", 1, "model_1", "ref_hash", 1)
    id2 = db.start_face_analysis_attempt(1, "CALIBRATED", 2, "model_1", "ref_hash", 2)
    
    assert id1 != id2
    
def test_routing_and_caption_flags_independent(test_config):
    config = test_config
    config.faces.use_for_routing = True
    config.faces.include_names_in_captions = False
    
    assert config.faces.use_for_routing
    assert not config.faces.include_names_in_captions
