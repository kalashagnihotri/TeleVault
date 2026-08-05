import os
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import json

from src.face_enrollment import cmd_enroll, cmd_rebuild, cmd_calibrate, cmd_deactivate, check_write_permission, cmd_list
from src.database import ArchiveDatabase
from src.face_engine import FaceEngineError

@pytest.fixture
def memory_db(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    db = ArchiveDatabase(db_path)
    
    # We must mock migrations or use actual migrations
    from src.config import load_config
    # actually, just applying migrations using the existing method
    # we need the sql dir
    sql_dir = Path(__file__).parent.parent / "sql"
    if sql_dir.exists():
        db.apply_migrations(sql_dir)
        
    return db

@pytest.fixture
def mock_engine_config(tmp_path):
    config = MagicMock()
    config.faces.enabled = True
    config.faces.reference_root = tmp_path
    config.faces.aggregate_method = "top_k_mean"
    config.faces.aggregate_top_k = 3
    config.faces.minimum_strong_support = 2
    config.faces.policy_identity = "mock_policy"
    config.faces.minimum_face_size_px = 20
    config.faces.minimum_references_per_person = 1
    config.app.dry_run = True
    return config

def test_check_write_permission_logic():
    logger = MagicMock()
    config = MagicMock()
    args = MagicMock()
    
    # no --commit, dry_run true: plan only
    args.commit = False
    config.app.dry_run = True
    assert check_write_permission(args, config, logger) is False
    
    # no --commit, dry_run false: plan only
    args.commit = False
    config.app.dry_run = False
    assert check_write_permission(args, config, logger) is False
    
    # --commit, dry_run true: refuse
    args.commit = True
    config.app.dry_run = True
    with pytest.raises(SystemExit) as e:
        check_write_permission(args, config, logger)
    assert e.value.code == 2
    
    # --commit, dry_run false: allow
    args.commit = True
    config.app.dry_run = False
    assert check_write_permission(args, config, logger) is True

@patch("src.face_enrollment.get_engine")
@patch("src.face_enrollment.OPENCV_AVAILABLE", True)
@patch("cv2.imread")
def test_enroll_dry_run_creates_zero_records(mock_imread, mock_get_engine, memory_db, mock_engine_config, tmp_path):
    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    
    # Make a dummy image
    img = tmp_path / "test.jpg"
    img.write_bytes(b"dummy")
    
    mock_imread.return_value = "dummy_image"
    mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
    mock_engine.align_face.return_value = "aligned"
    mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"0" * 512)
    mock_engine.model_identity.return_value = "test_model"

    args = MagicMock()
    args.person_slug = "test-person"
    args.display_name = "Test Person"
    args.source = str(tmp_path)
    args.commit = False

    logger = MagicMock()
    
    result = cmd_enroll(args, mock_engine_config, memory_db, logger)
    assert result == 0
    
    # Verify DB has zero people and zero references
    with memory_db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM face_references").fetchone()[0] == 0
        
@patch("src.face_enrollment.get_engine")
@patch("src.face_enrollment.OPENCV_AVAILABLE", True)
@patch("cv2.imread")
def test_rejected_reference_dry_run_creates_zero_rows(mock_imread, mock_get_engine, memory_db, mock_engine_config, tmp_path):
    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    
    # Make a dummy image
    img = tmp_path / "bad.jpg"
    img.write_bytes(b"dummy")
    
    mock_imread.return_value = None # unreadable
    
    args = MagicMock()
    args.person_slug = "test-person"
    args.display_name = "Test Person"
    args.source = str(tmp_path)
    args.commit = False

    logger = MagicMock()
    
    result = cmd_enroll(args, mock_engine_config, memory_db, logger)
    assert result == 0
    
    with memory_db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM face_references").fetchone()[0] == 0

@patch("src.face_enrollment.check_write_permission")
def test_rebuild_dry_run_creates_zero_rows(mock_check, memory_db, mock_engine_config, tmp_path):
    mock_check.return_value = False
    
    person_slug = "slug1"
    person_folder = tmp_path / person_slug
    person_folder.mkdir()
    img_path = person_folder / "1.jpg"
    img_path.write_bytes(b"dummy")
    
    # Populate dummy person and references
    person_id = memory_db.get_or_create_person(person_slug, "Name")
    memory_db.add_reference(person_id, "hash1", str(img_path), 0.99, 100, 100, "{}", b"blob1", 128, "modelA")
    
    args = MagicMock()
    args.person_slug = person_slug
    args.commit = False
    
    logger = MagicMock()
    
    # We must patch get_engine to not crash
    mock_engine = MagicMock()
    mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
    mock_engine.align_face.return_value = "aligned"
    mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"0" * 512)
    mock_engine.model_identity.return_value = "modelA"

    with patch("src.face_enrollment.get_engine", return_value=mock_engine), \
         patch("cv2.imread", return_value="dummy_image"), \
         patch("src.face_enrollment.OPENCV_AVAILABLE", True):
        result = cmd_rebuild(args, mock_engine_config, memory_db, logger)
    
    assert result == 0
    
    with memory_db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM face_references").fetchone()[0] == 1
        assert conn.execute("SELECT active FROM face_references").fetchone()[0] == 1

def test_deactivate_dry_run_does_not_change_active_status(memory_db, mock_engine_config):
    person_id = memory_db.get_or_create_person("slug1", "Name")
    
    args = MagicMock()
    args.person_slug = "slug1"
    args.commit = False
    logger = MagicMock()
    
    result = cmd_deactivate(args, mock_engine_config, memory_db, logger)
    assert result == 0
    
    with memory_db.connect() as conn:
        assert conn.execute("SELECT active FROM people WHERE person_slug='slug1'").fetchone()[0] == 1

@patch("src.face_enrollment.OPENCV_AVAILABLE", True)
@patch("src.face_enrollment.get_engine")
def test_calibrate_dry_run_creates_zero_rows(mock_get_engine, memory_db, mock_engine_config):
    mock_get_engine.return_value.model_identity.return_value = "modelA"
    mock_get_engine.return_value.compare_embeddings.return_value = 0.9
    
    p1 = memory_db.get_or_create_person("p1", "P1")
    p2 = memory_db.get_or_create_person("p2", "P2")
    # Must be valid length for float32 (multiple of 4 bytes)
    memory_db.add_reference(p1, "h1", "p1.jpg", 0.99, 100, 100, "{}", b"0" * 512, 128, "modelA")
    memory_db.add_reference(p1, "h3", "p1_b.jpg", 0.99, 100, 100, "{}", b"0" * 512, 128, "modelA")
    memory_db.add_reference(p2, "h2", "p2.jpg", 0.99, 100, 100, "{}", b"0" * 512, 128, "modelA")
    memory_db.add_reference(p2, "h4", "p2_b.jpg", 0.99, 100, 100, "{}", b"0" * 512, 128, "modelA")
    
    mock_engine_config.faces.minimum_references_per_person = 2
    
    args = MagicMock()
    args.negatives_dir = None
    args.allow_failed_holdout = False
    args.commit = False
    args.commit = False
    logger = MagicMock()
    
    result = cmd_calibrate(args, mock_engine_config, memory_db, logger)
    assert result == 0
    
    with memory_db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0

def test_list_remains_read_only(memory_db, mock_engine_config):
    memory_db.get_or_create_person("p1", "P1")
    args = MagicMock()
    logger = MagicMock()
    
    result = cmd_list(args, mock_engine_config, memory_db, logger)
    assert result == 0

@patch("src.face_enrollment.OPENCV_AVAILABLE", True)
@patch("src.face_enrollment.get_engine")
@patch("cv2.imread")
def test_successful_commit_writes_records(mock_imread, mock_get_engine, memory_db, mock_engine_config, tmp_path):
    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    
    img = tmp_path / "test.jpg"
    img.write_bytes(b"dummy")
    
    mock_imread.return_value = "dummy_image"
    mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
    mock_engine.align_face.return_value = "aligned"
    mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"0" * 512)
    mock_engine.model_identity.return_value = "test_model"

    args = MagicMock()
    args.person_slug = "test-person"
    args.display_name = "Test Person"
    args.source = str(tmp_path)
    args.commit = True

    mock_engine_config.app.dry_run = False
    logger = MagicMock()
    
    result = cmd_enroll(args, mock_engine_config, memory_db, logger)
    assert result == 0
    
    with memory_db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM face_references").fetchone()[0] == 1
        
@patch("src.face_enrollment.OPENCV_AVAILABLE", True)
@patch("src.face_enrollment.get_engine")
@patch("cv2.imread")
def test_failure_on_later_reference_creates_no_partial_rows(mock_imread, mock_get_engine, memory_db, mock_engine_config, tmp_path):
    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    
    img1 = tmp_path / "good.jpg"
    img1.write_bytes(b"dummy1")
    
    img2 = tmp_path / "bad.jpg"
    img2.write_bytes(b"dummy2")
    
    def side_effect(img, face):
        if "bad" in str(img):
            raise FaceEngineError("Simulated failure")
        return "aligned"
        
    mock_imread.return_value = "dummy_image"
    mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
    mock_engine.align_face.side_effect = side_effect
    mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"0" * 512)
    mock_engine.model_identity.return_value = "test_model"

    args = MagicMock()
    args.person_slug = "test-person"
    args.display_name = "Test Person"
    args.source = str(tmp_path)
    args.commit = True

    mock_engine_config.app.dry_run = False
    logger = MagicMock()
    
    # We want to simulate a transaction failure
    # Wait, align_face raising FaceEngineError just skips the file and adds to rejected.
    # To cause a transaction failure, we can patch db.transaction to fail, or just mock db.
    
    # Let's mock conn.execute inside the transaction to throw an exception
    original_execute = memory_db.connect().execute
    
    def failing_execute(*eargs, **kwargs):
        if "face_references" in eargs[0]:
            raise Exception("Transaction error")
        return original_execute(*eargs, **kwargs)
        
    with patch.object(ArchiveDatabase, 'transaction') as mock_tx:
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        # Create schema
        sql_dir = Path(__file__).parent.parent / "sql"
        memory_db.apply_migrations(sql_dir) # already applied, just to get connection
        # Mock transaction
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = failing_execute
        
        # We need a context manager
        from contextlib import contextmanager
        @contextmanager
        def failing_tx():
            yield mock_conn
            
        mock_tx.side_effect = failing_tx
        
        result = cmd_enroll(args, mock_engine_config, memory_db, logger)
        assert result == 1
        
        # Original DB should have zero rows
        with memory_db.connect() as real_conn:
            assert real_conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 0

@patch("src.face_enrollment.OPENCV_AVAILABLE", True)
@patch("src.face_enrollment.get_engine")
@patch("cv2.imread")
def test_four_valid_references_minimum_five_produces_zero_committed_rows(mock_imread, mock_get_engine, memory_db, mock_engine_config, tmp_path):
    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    
    for i in range(4):
        img = tmp_path / f"test_{i}.jpg"
        img.write_bytes(b"dummy")
    
    mock_imread.return_value = "dummy_image"
    mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
    mock_engine.align_face.return_value = "aligned"
    mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"0" * 512)
    mock_engine.model_identity.return_value = "test_model"

    mock_engine_config.faces.minimum_references_per_person = 5
    mock_engine_config.app.dry_run = False

    args = MagicMock()
    args.person_slug = "test-person"
    args.display_name = "Test Person"
    args.source = str(tmp_path)
    args.commit = True

    logger = MagicMock()
    
    result = cmd_enroll(args, mock_engine_config, memory_db, logger)
    assert result == 1
    
    with memory_db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM face_references").fetchone()[0] == 0

@patch("src.face_enrollment.OPENCV_AVAILABLE", True)
@patch("src.face_enrollment.get_engine")
@patch("cv2.imread")
def test_failed_rebuild_too_few_references_preserves_old_references(mock_imread, mock_get_engine, memory_db, mock_engine_config, tmp_path):
    person_slug = "slug1"
    person_folder = tmp_path / person_slug
    person_folder.mkdir()
    
    # Setup old person and reference
    person_id = memory_db.get_or_create_person(person_slug, "Name")
    memory_db.add_reference(person_id, "hash1", str(person_folder / "1.jpg"), 0.99, 100, 100, "{}", b"0" * 512, 128, "modelA")
    memory_db.add_reference(person_id, "hash2", str(person_folder / "2.jpg"), 0.99, 100, 100, "{}", b"0" * 512, 128, "modelA")
    
    # We only have 2 active old refs. We want minimum 5.
    mock_engine_config.faces.minimum_references_per_person = 5
    mock_engine_config.app.dry_run = False
    mock_engine_config.faces.reference_root = tmp_path

    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    
    # Create the files so they exist
    (person_folder / "1.jpg").write_bytes(b"dummy")
    (person_folder / "2.jpg").write_bytes(b"dummy")
    
    mock_imread.return_value = "dummy_image"
    mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
    mock_engine.align_face.return_value = "aligned"
    mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"0" * 512)
    mock_engine.model_identity.return_value = "modelA"

    args = MagicMock()
    args.person_slug = person_slug
    args.commit = True
    
    logger = MagicMock()
    
    result = cmd_rebuild(args, mock_engine_config, memory_db, logger)
    assert result == 1
    
    # Check old references are still active
    with memory_db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM face_references").fetchone()[0] == 2
        assert conn.execute("SELECT active FROM face_references WHERE source_sha256 = 'hash1'").fetchone()[0] == 1
        assert conn.execute("SELECT active FROM face_references WHERE source_sha256 = 'hash2'").fetchone()[0] == 1

@patch("src.face_enrollment.OPENCV_AVAILABLE", True)
@patch("src.face_enrollment.get_engine")
@patch("cv2.imread")
def test_rebuild_discovers_eight_files_and_reactivates(mock_imread, mock_get_engine, memory_db, mock_engine_config, tmp_path):
    person_slug = "person-eight"
    person_folder = tmp_path / person_slug
    person_folder.mkdir()
    
    person_id = memory_db.get_or_create_person(person_slug, "Name")
    
    # Old DB had 4 references. 
    # Let's say one is completely gone, one is still there, one is duplicate hash?
    # We'll just put 4 in DB, and create 8 files in folder.
    import hashlib
    hash0 = hashlib.sha256(b"dummy0").hexdigest()
    hash1 = hashlib.sha256(b"dummy1").hexdigest()
    hash2 = hashlib.sha256(b"dummy2").hexdigest()

    memory_db.add_reference(person_id, hash0, str(person_folder / "0.jpg"), 0.99, 100, 100, "{}", b"0" * 512, 128, "modelA")
    memory_db.add_reference(person_id, hash1, str(person_folder / "1.jpg"), 0.99, 100, 100, "{}", b"0" * 512, 128, "modelA")
    memory_db.add_reference(person_id, hash2, str(person_folder / "2.jpg"), 0.99, 100, 100, "{}", b"0" * 512, 128, "modelA")
    # This one will be removed
    memory_db.add_reference(person_id, "hash99", str(person_folder / "missing.jpg"), 0.99, 100, 100, "{}", b"0" * 512, 128, "modelA")

    # Folder has 8 files (0 to 7)
    for i in range(8):
        img = person_folder / f"{i}.jpg"
        img.write_bytes(f"dummy{i}".encode())
        
    mock_engine_config.faces.minimum_references_per_person = 5
    mock_engine_config.app.dry_run = False
    mock_engine_config.faces.reference_root = tmp_path

    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    
    mock_imread.return_value = "dummy_image"
    mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
    mock_engine.align_face.return_value = "aligned"
    mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"0" * 512)
    mock_engine.model_identity.return_value = "modelA"

    args = MagicMock()
    args.person_slug = person_slug
    args.commit = True
    
    logger = MagicMock()
    
    result = cmd_rebuild(args, mock_engine_config, memory_db, logger)
    assert result == 0
    
    with memory_db.connect() as conn:
        # 8 new/reactivated + 1 missing = 9 total rows (no duplicate inserts for 0,1,2)
        total_rows = conn.execute("SELECT COUNT(*) FROM face_references WHERE person_id = ?", (person_id,)).fetchone()[0]
        assert total_rows == 9
        
        # 8 active
        active_count = conn.execute("SELECT COUNT(*) FROM face_references WHERE person_id = ? AND active = 1", (person_id,)).fetchone()[0]
        assert active_count == 8
        
        # hash99 should be inactive
        missing_active = conn.execute("SELECT active FROM face_references WHERE source_sha256 = 'hash99'").fetchone()[0]
        assert missing_active == 0

@patch("src.face_enrollment.OPENCV_AVAILABLE", True)
@patch("src.face_enrollment.get_engine")
def test_rebuild_rejects_escape_path(mock_get_engine, memory_db, mock_engine_config, tmp_path):
    mock_engine_config.faces.reference_root = tmp_path / "valid_root"
    mock_engine_config.faces.reference_root.mkdir()
    mock_engine_config.app.dry_run = False
    
    args = MagicMock()
    # Try to escape
    args.person_slug = "../escaped"
    args.commit = True
    
    logger = MagicMock()
    
    result = cmd_rebuild(args, mock_engine_config, memory_db, logger)
    assert result == 1
    
@patch("src.face_enrollment.OPENCV_AVAILABLE", True)
@patch("src.face_enrollment.get_engine")
@patch("cv2.imread")
def test_rebuild_discovers_uppercase_and_sorts(mock_imread, mock_get_engine, memory_db, mock_engine_config, tmp_path):
    person_slug = "upper"
    person_folder = tmp_path / person_slug
    person_folder.mkdir()
    
    person_id = memory_db.get_or_create_person(person_slug, "Name")
    
    (person_folder / "B.JPEG").write_bytes(b"dummy1")
    (person_folder / "c.PNG").write_bytes(b"dummy2")
    (person_folder / "A.JPG").write_bytes(b"dummy3")
    
    mock_engine_config.faces.minimum_references_per_person = 1
    mock_engine_config.app.dry_run = False
    mock_engine_config.faces.reference_root = tmp_path

    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    
    mock_imread.return_value = "dummy_image"
    mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
    mock_engine.align_face.return_value = "aligned"
    mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"0" * 512)
    mock_engine.model_identity.return_value = "modelA"

    args = MagicMock()
    args.person_slug = person_slug
    args.commit = True
    
    logger = MagicMock()
    
    result = cmd_rebuild(args, mock_engine_config, memory_db, logger)
    assert result == 0
    
    with memory_db.connect() as conn:
        refs = conn.execute("SELECT source_path FROM face_references WHERE person_id = ? ORDER BY enrolled_at ASC, reference_id ASC", (person_id,)).fetchall()
        paths = [r["source_path"] for r in refs]
        # Should be processed A, B, c due to deterministic sorting
        assert "A.JPG" in paths[0]
        assert "B.JPEG" in paths[1]
        assert "c.PNG" in paths[2]

@patch("src.face_enrollment.OPENCV_AVAILABLE", True)
@patch("src.face_enrollment.get_engine")
@patch("cv2.imread")
def test_five_valid_references_allows_commit(mock_imread, mock_get_engine, memory_db, mock_engine_config, tmp_path):
    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    
    for i in range(5):
        img = tmp_path / f"test_{i}.jpg"
        img.write_bytes(b"dummy")
    
    mock_imread.return_value = "dummy_image"
    mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
    mock_engine.align_face.return_value = "aligned"
    mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"0" * 512)
    mock_engine.model_identity.return_value = "test_model"

    mock_engine_config.faces.minimum_references_per_person = 5
    mock_engine_config.app.dry_run = False

    args = MagicMock()
    args.person_slug = "test-person"
    args.display_name = "Test Person"
    args.source = str(tmp_path)
    args.commit = True

    logger = MagicMock()
    
    result = cmd_enroll(args, mock_engine_config, memory_db, logger)
    assert result == 0
    
    with memory_db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM face_references").fetchone()[0] == 5

@patch("src.face_enrollment.OPENCV_AVAILABLE", True)
@patch("src.face_enrollment.get_engine")
@patch("cv2.imread")
def test_log_privacy_regression(mock_imread, mock_get_engine, memory_db, mock_engine_config, tmp_path):
    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    
    # We will pass 1 bad image, 1 good image
    bad_img = tmp_path / "private_bad.jpg"
    bad_img.write_bytes(b"bad")
    good_img = tmp_path / "private_good.jpg"
    good_img.write_bytes(b"good")
    
    def side_effect(img):
        if "bad" in str(img):
            return None
        return "dummy_image"
        
    mock_imread.side_effect = side_effect
    mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
    mock_engine.align_face.return_value = "aligned"
    mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"0" * 512)
    mock_engine.model_identity.return_value = "test_model"
    
    mock_engine_config.faces.minimum_references_per_person = 1
    mock_engine_config.app.dry_run = False
    
    args = MagicMock()
    args.person_slug = "private-person-slug"
    args.display_name = "Private Display Name"
    args.source = str(tmp_path)
    args.commit = True

    import logging
    # We capture logs programmatically
    logger = logging.getLogger("test_privacy")
    logger.setLevel(logging.DEBUG)
    
    class LogCaptureHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []
            
        def emit(self, record):
            self.records.append(record)
            
    handler = LogCaptureHandler()
    logger.addHandler(handler)
    
    result = cmd_enroll(args, mock_engine_config, memory_db, logger)
    assert result == 0
    
    # Analyze records
    info_warnings = [r for r in handler.records if r.levelno in (logging.INFO, logging.WARNING, logging.ERROR)]
    debug_logs = [r for r in handler.records if r.levelno == logging.DEBUG]
    
    for r in info_warnings:
        msg = r.getMessage()
        assert "private_bad.jpg" not in msg, f"Leak in {r.levelname}: {msg}"
        assert "private_good.jpg" not in msg, f"Leak in {r.levelname}: {msg}"
        assert "private-person-slug" not in msg, f"Leak in {r.levelname}: {msg}"
        assert "Private Display Name" not in msg, f"Leak in {r.levelname}: {msg}"
        
    # verify the private paths DID appear in debug
    debug_messages = " ".join([r.getMessage() for r in debug_logs])
    assert "private_bad.jpg" in debug_messages
    assert "private_good.jpg" in debug_messages
    assert "private-person-slug" in debug_messages
