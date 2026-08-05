import pytest
import os
import shutil
import hashlib
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.prepare_lfw_negatives import (
    select_negatives,
    SelectedSource,
    InsufficientValidIdentitiesError,
    PROJECT,
    CALIBRATION_DIR,
    HOLDOUT_DIR,
    main
)

@pytest.fixture
def mock_config():
    config = MagicMock()
    config.faces.minimum_face_size_px = 96
    return config

@pytest.fixture
def mock_engine():
    engine = MagicMock()
    # Default valid face
    engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.95]]
    engine.align_face.return_value = "aligned"
    emb = MagicMock()
    emb.size = 128
    engine.create_embedding.return_value = emb
    return engine

@pytest.fixture
def lfw_cache(tmp_path):
    lfw_root = tmp_path / "lfw" / "lfw"
    lfw_root.mkdir(parents=True, exist_ok=True)
    return lfw_root

def create_identity(lfw_root, name, num_images, offset=0, content=None):
    ident_dir = lfw_root / name
    ident_dir.mkdir(parents=True, exist_ok=True)
    images = []
    for i in range(num_images):
        img_path = ident_dir / f"{name}_{(i+offset):04d}.jpg"
        if content is None:
            c = os.urandom(16)
        else:
            c = content if isinstance(content, bytes) else content.encode()
        with open(img_path, "wb") as f:
            f.write(c)
        images.append(img_path)
    return images

@patch("scripts.prepare_lfw_negatives.fetch_lfw_people")
@patch("scripts.prepare_lfw_negatives.find_lfw_root")
@patch("scripts.prepare_lfw_negatives.decode_image_with_exif")
def test_selection_disjoint_identities(mock_decode, mock_find, mock_fetch, mock_config, mock_engine, lfw_cache):
    mock_find.return_value = lfw_cache
    mock_decode.return_value = {"image": np.zeros((100,100,3), dtype=np.uint8)}
    
    for i in range(10):
        create_identity(lfw_cache, f"person_{i}", 1)
        
    selections, report = select_negatives(mock_config, mock_engine, seed=42, calibration_count=5, holdout_count=5, logger=__import__('unittest.mock').mock.MagicMock(), opts=__import__('unittest.mock').mock.MagicMock())
    
    cal_identities = {s.identity_key for s in selections[:5]}
    hld_identities = {s.identity_key for s in selections[5:]}
    
    assert cal_identities.isdisjoint(hld_identities)
    assert len(cal_identities) == 5
    assert len(hld_identities) == 5

@patch("scripts.prepare_lfw_negatives.fetch_lfw_people")
@patch("scripts.prepare_lfw_negatives.find_lfw_root")
@patch("scripts.prepare_lfw_negatives.decode_image_with_exif")
def test_every_selected_identity_is_unique(mock_decode, mock_find, mock_fetch, mock_config, mock_engine, lfw_cache):
    mock_find.return_value = lfw_cache
    mock_decode.return_value = {"image": np.zeros((100,100,3), dtype=np.uint8)}
    
    for i in range(5):
        create_identity(lfw_cache, f"person_{i}", 2)
        
    selections, report = select_negatives(mock_config, mock_engine, seed=42, calibration_count=2, holdout_count=2, logger=__import__('unittest.mock').mock.MagicMock(), opts=__import__('unittest.mock').mock.MagicMock())
    identities = [s.identity_key for s in selections]
    assert len(identities) == len(set(identities))

@patch("scripts.prepare_lfw_negatives.fetch_lfw_people")
@patch("scripts.prepare_lfw_negatives.find_lfw_root")
@patch("scripts.prepare_lfw_negatives.decode_image_with_exif")
def test_reject_duplicate_hash(mock_decode, mock_find, mock_fetch, mock_config, mock_engine, lfw_cache):
    mock_find.return_value = lfw_cache
    mock_decode.return_value = {"image": np.zeros((100,100,3), dtype=np.uint8)}
    
    c = b"same_content"
    create_identity(lfw_cache, "person_0", 1, content=c)
    create_identity(lfw_cache, "person_1", 1, content=c)
    create_identity(lfw_cache, "person_2", 1, content=c)
    create_identity(lfw_cache, "person_3", 1, content=b"diff3")
    create_identity(lfw_cache, "person_4", 1, content=b"diff4")
    
    with pytest.raises(InsufficientValidIdentitiesError):
        # We need 4, but 3 of the 5 share the same hash, so only 3 unique valid identities exist.
        select_negatives(mock_config, mock_engine, seed=42, calibration_count=2, holdout_count=2, logger=__import__('unittest.mock').mock.MagicMock(), opts=__import__('unittest.mock').mock.MagicMock())

@patch("scripts.prepare_lfw_negatives.fetch_lfw_people")
@patch("scripts.prepare_lfw_negatives.find_lfw_root")
@patch("scripts.prepare_lfw_negatives.decode_image_with_exif")
def test_selection_tries_later_images_on_failure(mock_decode, mock_find, mock_fetch, mock_config, mock_engine, lfw_cache):
    mock_find.return_value = lfw_cache
    
    def decode_side_effect(path):
        if "person_0_0000" in path:
            raise ValueError("Decode error")
        return {"image": np.zeros((100,100,3), dtype=np.uint8)}
    mock_decode.side_effect = decode_side_effect
    
    create_identity(lfw_cache, "person_0", 2)
    create_identity(lfw_cache, "person_1", 1)
    create_identity(lfw_cache, "person_2", 1)
    create_identity(lfw_cache, "person_3", 1)
    
    selections, report = select_negatives(mock_config, mock_engine, seed=42, calibration_count=2, holdout_count=2, logger=__import__('unittest.mock').mock.MagicMock(), opts=__import__('unittest.mock').mock.MagicMock())
    assert len(selections) == 4
    # person_0 should still be selected because the second image succeeded
    assert any(s.identity_key == "person_0" for s in selections)

@patch("scripts.prepare_lfw_negatives.fetch_lfw_people")
@patch("scripts.prepare_lfw_negatives.find_lfw_root")
@patch("scripts.prepare_lfw_negatives.decode_image_with_exif")
def test_reject_multiple_faces(mock_decode, mock_find, mock_fetch, mock_config, mock_engine, lfw_cache):
    mock_find.return_value = lfw_cache
    mock_decode.return_value = {"image": np.zeros((100,100,3), dtype=np.uint8)}
    
    mock_engine.detect_faces.return_value = [
        [0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.95],
        [50, 50, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.95]
    ]
    
    create_identity(lfw_cache, "person_0", 1)
    
    with pytest.raises(InsufficientValidIdentitiesError):
        select_negatives(mock_config, mock_engine, seed=42, calibration_count=1, holdout_count=0, logger=__import__('unittest.mock').mock.MagicMock(), opts=__import__('unittest.mock').mock.MagicMock())

@patch("scripts.prepare_lfw_negatives.fetch_lfw_people")
@patch("scripts.prepare_lfw_negatives.find_lfw_root")
@patch("scripts.prepare_lfw_negatives.decode_image_with_exif")
def test_reject_alignment_failure(mock_decode, mock_find, mock_fetch, mock_config, mock_engine, lfw_cache):
    mock_find.return_value = lfw_cache
    mock_decode.return_value = {"image": np.zeros((100,100,3), dtype=np.uint8)}
    mock_engine.align_face.side_effect = ValueError("Alignment failed")
    
    create_identity(lfw_cache, "person_0", 1)
    with pytest.raises(InsufficientValidIdentitiesError):
        select_negatives(mock_config, mock_engine, seed=42, calibration_count=1, holdout_count=0, logger=__import__('unittest.mock').mock.MagicMock(), opts=__import__('unittest.mock').mock.MagicMock())

@patch("scripts.prepare_lfw_negatives.fetch_lfw_people")
@patch("scripts.prepare_lfw_negatives.find_lfw_root")
@patch("scripts.prepare_lfw_negatives.decode_image_with_exif")
def test_reject_embedding_failure(mock_decode, mock_find, mock_fetch, mock_config, mock_engine, lfw_cache):
    mock_find.return_value = lfw_cache
    mock_decode.return_value = {"image": np.zeros((100,100,3), dtype=np.uint8)}
    mock_engine.create_embedding.return_value = None
    
    create_identity(lfw_cache, "person_0", 1)
    with pytest.raises(InsufficientValidIdentitiesError):
        select_negatives(mock_config, mock_engine, seed=42, calibration_count=1, holdout_count=0, logger=__import__('unittest.mock').mock.MagicMock(), opts=__import__('unittest.mock').mock.MagicMock())

@patch("scripts.prepare_lfw_negatives.fetch_lfw_people")
@patch("scripts.prepare_lfw_negatives.find_lfw_root")
@patch("scripts.prepare_lfw_negatives.decode_image_with_exif")
def test_tiny_background_faces_allowed(mock_decode, mock_find, mock_fetch, mock_config, mock_engine, lfw_cache):
    mock_find.return_value = lfw_cache
    mock_decode.return_value = {"image": np.zeros((100,100,3), dtype=np.uint8)}
    
    mock_engine.detect_faces.return_value = [
        [0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.95],
        [0, 0, 50, 50, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.95], # tiny face
        [0, 0, 20, 20, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.95]  # tiny face
    ]
    
    create_identity(lfw_cache, "person_0", 1)
    selections, report = select_negatives(mock_config, mock_engine, seed=42, calibration_count=1, holdout_count=0, logger=__import__('unittest.mock').mock.MagicMock(), opts=__import__('unittest.mock').mock.MagicMock())
    assert len(selections) == 1

@patch("scripts.prepare_lfw_negatives.load_config")
@patch("scripts.prepare_lfw_negatives.setup_logger")
@patch("scripts.prepare_lfw_negatives.Cv2FaceEngine")
@patch("scripts.prepare_lfw_negatives.select_negatives")
def test_insufficient_identities_leaves_folders_unchanged(mock_select, mock_engine, mock_logger, mock_load, tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.prepare_lfw_negatives.CALIBRATION_DIR", tmp_path / "calibration")
    monkeypatch.setattr("scripts.prepare_lfw_negatives.HOLDOUT_DIR", tmp_path / "holdout")
    monkeypatch.setattr("scripts.prepare_lfw_negatives.PROJECT", tmp_path)
    
    (tmp_path / "calibration").mkdir()
    (tmp_path / "holdout").mkdir()
    (tmp_path / "calibration" / "old.jpg").touch()
    
    mock_select.side_effect = InsufficientValidIdentitiesError("Failed")
    
    import sys
    with patch.object(sys, "argv", ["prepare_lfw_negatives.py", "--calibration-count", "1", "--holdout-count", "1"]):
        assert main() == 1
        
    assert (tmp_path / "calibration" / "old.jpg").exists()
    assert not list(tmp_path.glob(".calibration_staging*"))

@patch("scripts.prepare_lfw_negatives.load_config")
@patch("scripts.prepare_lfw_negatives.setup_logger")
@patch("scripts.prepare_lfw_negatives.Cv2FaceEngine")
@patch("scripts.prepare_lfw_negatives.select_negatives")
@patch("shutil.copy2")
def test_copy_failure_rollback(mock_copy, mock_select, mock_engine, mock_logger, mock_load, tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.prepare_lfw_negatives.CALIBRATION_DIR", tmp_path / "calibration")
    monkeypatch.setattr("scripts.prepare_lfw_negatives.HOLDOUT_DIR", tmp_path / "holdout")
    monkeypatch.setattr("scripts.prepare_lfw_negatives.PROJECT", tmp_path)
    
    (tmp_path / "calibration").mkdir()
    (tmp_path / "holdout").mkdir()
    (tmp_path / "calibration" / "old.jpg").touch()
    
    # Fail on first copy
    mock_copy.side_effect = PermissionError("Access denied")
    
    mock_select.return_value = ([
        SelectedSource("id1", Path("p1"), "hash1"),
        SelectedSource("id2", Path("p2"), "hash2")
    ], {'seed': 42, 'identities_available': 0, 'identities_examined': 0, 'identities_exhausted': 0, 'images_examined': 0, 'decode_errors': 0, 'zero_detections': 0, 'tiny_only': 0, 'multiple_accepted_faces': 0, 'duplicate_content': 0, 'alignment_errors': 0, 'embedding_errors': 0, 'accepted_calibration': 0, 'accepted_holdout': 0})
    
    import sys
    with patch.object(sys, "argv", ["prepare_lfw_negatives.py", "--calibration-count", "1", "--holdout-count", "1"]):
        assert main() == 1
        
    assert (tmp_path / "calibration" / "old.jpg").exists()

def test_invalid_counts():
    import sys
    with patch.object(sys, "argv", ["prepare_lfw_negatives.py", "--calibration-count", "0", "--holdout-count", "0"]):
        assert main() == 1
        
@patch("scripts.prepare_lfw_negatives.fetch_lfw_people")
@patch("scripts.prepare_lfw_negatives.find_lfw_root")
@patch("scripts.prepare_lfw_negatives.decode_image_with_exif")
def test_same_seed_same_selection(mock_decode, mock_find, mock_fetch, mock_config, mock_engine, lfw_cache):
    mock_find.return_value = lfw_cache
    mock_decode.return_value = {"image": np.zeros((100,100,3), dtype=np.uint8)}
    
    for i in range(10):
        create_identity(lfw_cache, f"person_{i}", 1, content=str(i))
        
    s1, _ = select_negatives(mock_config, mock_engine, seed=42, calibration_count=3, holdout_count=3, logger=__import__('unittest.mock').mock.MagicMock(), opts=__import__('unittest.mock').mock.MagicMock())
    s2, _ = select_negatives(mock_config, mock_engine, seed=42, calibration_count=3, holdout_count=3, logger=__import__('unittest.mock').mock.MagicMock(), opts=__import__('unittest.mock').mock.MagicMock())
    s3, _ = select_negatives(mock_config, mock_engine, seed=100, calibration_count=3, holdout_count=3, logger=__import__('unittest.mock').mock.MagicMock(), opts=__import__('unittest.mock').mock.MagicMock())
    
    assert [s.identity_key for s in s1] == [s.identity_key for s in s2]
    assert [s.identity_key for s in s1] != [s.identity_key for s in s3]

@pytest.mark.integration
@pytest.mark.requires_face_models
def test_exported_negatives_pass_production_detector():
    from src.config import load_config
    from src.face_engine import Cv2FaceEngine, OPENCV_AVAILABLE
    from src.image_utils import decode_image_with_exif
    from src.logger import setup_logger
    import numpy as np
    
    if not OPENCV_AVAILABLE:
        pytest.skip("OpenCV models not available")
        
    if not CALIBRATION_DIR.exists() or not HOLDOUT_DIR.exists():
        pytest.skip("Exported folders not available")
        
    config = load_config()
    logger = setup_logger(config)
    engine = Cv2FaceEngine(config.faces, logger)
    engine.load_models()
    
    exported_files = list(CALIBRATION_DIR.glob("*.jpg")) + list(HOLDOUT_DIR.glob("*.jpg"))
    if not exported_files:
        pytest.skip("No exported files")
        
    for exported_file in exported_files:
        image = decode_image_with_exif(str(exported_file))["image"]
        raw_faces = engine.detect_faces(image)

        accepted = [
            face
            for face in raw_faces
            if int(face[2]) >= config.faces.minimum_face_size_px
            and int(face[3]) >= config.faces.minimum_face_size_px
        ]

        assert len(accepted) == 1

        aligned = engine.align_face(image, accepted[0])
        embedding = engine.create_embedding(aligned)

        assert embedding.shape == (128,)
        assert embedding.dtype == np.float32
        assert np.isfinite(embedding).all()
import pytest
import os
import shutil
import hashlib
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, patch
import uuid

from scripts.prepare_lfw_negatives import (
    select_negatives,
    SelectedSource,
    InsufficientValidIdentitiesError,
    PROJECT,
    CALIBRATION_DIR,
    HOLDOUT_DIR,
    main
)

def create_identity(lfw_root, name, num_images, offset=0, content=None):
    ident_dir = lfw_root / name
    ident_dir.mkdir(parents=True, exist_ok=True)
    images = []
    for i in range(num_images):
        img_path = ident_dir / f"{name}_{(i+offset):04d}.jpg"
        if content is None:
            c = os.urandom(16)
        else:
            c = content if isinstance(content, bytes) else content.encode()
        with open(img_path, "wb") as f:
            f.write(c)
        images.append(img_path)
    return images

@patch("scripts.prepare_lfw_negatives.load_config")
@patch("scripts.prepare_lfw_negatives.setup_logger")
@patch("scripts.prepare_lfw_negatives.Cv2FaceEngine")
@patch("scripts.prepare_lfw_negatives.select_negatives")
@patch("shutil.copy2")
def test_failure_while_installing_second_split_rolls_back(mock_copy, mock_select, mock_engine, mock_logger, mock_load, tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.prepare_lfw_negatives.CALIBRATION_DIR", tmp_path / "calibration")
    monkeypatch.setattr("scripts.prepare_lfw_negatives.HOLDOUT_DIR", tmp_path / "holdout")
    monkeypatch.setattr("scripts.prepare_lfw_negatives.PROJECT", tmp_path)
    
    (tmp_path / "calibration").mkdir()
    (tmp_path / "holdout").mkdir()
    (tmp_path / "calibration" / "old_cal.jpg").touch()
    (tmp_path / "holdout" / "old_hld.jpg").touch()
    
    # Mock rename to fail only when renaming holdout staging
    original_rename = Path.rename
    def mock_rename(self, target):
        if "holdout" in str(target) and "staging" in str(self):
            raise OSError("Fake rename failure")
        return original_rename(self, target)
    
    monkeypatch.setattr(Path, "rename", mock_rename)
    
    mock_select.return_value = ([
        SelectedSource("id1", Path("p1"), "hash1"),
        SelectedSource("id2", Path("p2"), "hash2")
    ], {'seed': 42, 'identities_available': 0, 'identities_examined': 0, 'identities_exhausted': 0, 'images_examined': 0, 'decode_errors': 0, 'zero_detections': 0, 'tiny_only': 0, 'multiple_accepted_faces': 0, 'duplicate_content': 0, 'alignment_errors': 0, 'embedding_errors': 0, 'accepted_calibration': 0, 'accepted_holdout': 0})
    
    import sys
    with patch.object(sys, "argv", ["prepare_lfw_negatives.py", "--calibration-count", "1", "--holdout-count", "1"]):
        assert main() == 1
        
    assert (tmp_path / "calibration" / "old_cal.jpg").exists()
    assert (tmp_path / "holdout" / "old_hld.jpg").exists()

@patch("scripts.prepare_lfw_negatives.load_config")
@patch("scripts.prepare_lfw_negatives.setup_logger")
@patch("scripts.prepare_lfw_negatives.Cv2FaceEngine")
@patch("scripts.prepare_lfw_negatives.select_negatives")
def test_stale_staging_directories_not_reused(mock_select, mock_engine, mock_logger, mock_load, tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.prepare_lfw_negatives.CALIBRATION_DIR", tmp_path / "calibration")
    monkeypatch.setattr("scripts.prepare_lfw_negatives.HOLDOUT_DIR", tmp_path / "holdout")
    monkeypatch.setattr("scripts.prepare_lfw_negatives.PROJECT", tmp_path)
    
    (tmp_path / "calibration").mkdir()
    (tmp_path / "holdout").mkdir()
    
    stale_dir = tmp_path / "private_negatives" / ".calibration_staging_stale"
    stale_dir.mkdir(parents=True)
    (stale_dir / "stale.jpg").touch()
    
    mock_select.return_value = ([
        SelectedSource("id1", tmp_path / "src1", "hash1"),
        SelectedSource("id2", tmp_path / "src2", "hash2")
    ], {'seed': 42, 'identities_available': 0, 'identities_examined': 0, 'identities_exhausted': 0, 'images_examined': 0, 'decode_errors': 0, 'zero_detections': 0, 'tiny_only': 0, 'multiple_accepted_faces': 0, 'duplicate_content': 0, 'alignment_errors': 0, 'embedding_errors': 0, 'accepted_calibration': 0, 'accepted_holdout': 0})
    
    (tmp_path / "src1").touch()
    (tmp_path / "src2").touch()
    
    import sys
    with patch.object(sys, "argv", ["prepare_lfw_negatives.py", "--calibration-count", "1", "--holdout-count", "1"]):
        assert main() == 0
        
    # The stale file should NOT be in the final calibration folder
    assert not (tmp_path / "calibration" / "stale.jpg").exists()

@patch("scripts.prepare_lfw_negatives.load_config")
@patch("scripts.prepare_lfw_negatives.setup_logger")
@patch("scripts.prepare_lfw_negatives.Cv2FaceEngine")
@patch("scripts.prepare_lfw_negatives.select_negatives")
def test_exported_files_byte_identical(mock_select, mock_engine, mock_logger, mock_load, tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.prepare_lfw_negatives.CALIBRATION_DIR", tmp_path / "calibration")
    monkeypatch.setattr("scripts.prepare_lfw_negatives.HOLDOUT_DIR", tmp_path / "holdout")
    monkeypatch.setattr("scripts.prepare_lfw_negatives.PROJECT", tmp_path)
    
    src1 = tmp_path / "src1"
    src1.write_bytes(b"content1")
    src2 = tmp_path / "src2"
    src2.write_bytes(b"content2")
    
    mock_select.return_value = ([
        SelectedSource("id1", src1, "hash1"),
        SelectedSource("id2", src2, "hash2")
    ], {'seed': 42, 'identities_available': 0, 'identities_examined': 0, 'identities_exhausted': 0, 'images_examined': 0, 'decode_errors': 0, 'zero_detections': 0, 'tiny_only': 0, 'multiple_accepted_faces': 0, 'duplicate_content': 0, 'alignment_errors': 0, 'embedding_errors': 0, 'accepted_calibration': 0, 'accepted_holdout': 0})
    
    import sys
    with patch.object(sys, "argv", ["prepare_lfw_negatives.py", "--calibration-count", "1", "--holdout-count", "1"]):
        assert main() == 0
        
    cal_file = next((tmp_path / "calibration").glob("*.jpg"))
    hld_file = next((tmp_path / "holdout").glob("*.jpg"))
    assert cal_file.read_bytes() == b"content1"
    assert hld_file.read_bytes() == b"content2"

@patch("scripts.prepare_lfw_negatives.fetch_lfw_people")
@patch("scripts.prepare_lfw_negatives.find_lfw_root")
@patch("scripts.prepare_lfw_negatives.decode_image_with_exif")
def test_mocked_source_cache_remains_unchanged(mock_decode, mock_find, mock_fetch, tmp_path):
    # This proves selection treats cache as read-only.
    lfw_cache = tmp_path / "lfw"
    lfw_cache.mkdir()
    
    create_identity(lfw_cache, "person_0", 1, content=b"unchanged")
    orig_stat = (lfw_cache / "person_0" / "person_0_0000.jpg").stat()
    
    mock_find.return_value = lfw_cache
    mock_decode.return_value = {"image": np.zeros((100,100,3), dtype=np.uint8)}
    
    config = MagicMock()
    config.faces.minimum_face_size_px = 96
    engine = MagicMock()
    engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.95]]
    engine.align_face.return_value = "aligned"
    engine.create_embedding.return_value = MagicMock(size=128)
    
    logger = MagicMock()
    opts = MagicMock()
    select_negatives(config, engine, seed=42, calibration_count=1, holdout_count=0, logger=logger, opts=opts)
    
    assert (lfw_cache / "person_0" / "person_0_0000.jpg").read_bytes() == b"unchanged"
    assert (lfw_cache / "person_0" / "person_0_0000.jpg").stat().st_mtime == orig_stat.st_mtime

@patch("scripts.prepare_lfw_negatives.fetch_lfw_people")
@patch("scripts.prepare_lfw_negatives.find_lfw_root")
@patch("scripts.prepare_lfw_negatives.decode_image_with_exif")
def test_different_seeds_produce_different_selections(mock_decode, mock_find, mock_fetch, tmp_path):
    lfw_cache = tmp_path / "lfw"
    lfw_cache.mkdir()
    
    for i in range(10):
        create_identity(lfw_cache, f"person_{i}", 1, content=str(i))
        
    mock_find.return_value = lfw_cache
    mock_decode.return_value = {"image": np.zeros((100,100,3), dtype=np.uint8)}
    
    config = MagicMock()
    config.faces.minimum_face_size_px = 96
    engine = MagicMock()
    engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.95]]
    engine.align_face.return_value = "aligned"
    engine.create_embedding.return_value = MagicMock(size=128)
    
    logger = MagicMock()
    opts = MagicMock()
    s1, _ = select_negatives(config, engine, seed=42, calibration_count=2, holdout_count=2, logger=logger, opts=opts)
    s2, _ = select_negatives(config, engine, seed=100, calibration_count=2, holdout_count=2, logger=logger, opts=opts)
    
    assert [s.identity_key for s in s1] != [s.identity_key for s in s2]