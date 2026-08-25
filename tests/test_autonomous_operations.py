"""Test Suite for Phase 6.5G: Autonomous Operations & Archive Intelligence"""

from __future__ import annotations

import json
from pathlib import Path
from fastapi.testclient import TestClient
from PIL import Image

from src.control_center.app import app
from src.control_center.services.audit_service import get_audit_timeline, record_audit_event
from src.control_center.services.deduplication_service import compute_dhash, compute_hamming_distance, scan_for_near_duplicates
from src.control_center.services.feedback_learning_service import record_face_feedback, record_scene_feedback
from src.control_center.services.lifecycle_service import get_media_lifecycle_summary
from src.control_center.services.memory_evaluation_service import evaluate_memory_quality
from src.control_center.services.portable_archive_service import export_portable_archive_bundle
from src.control_center.services.preference_service import get_user_preferences_profile, record_interaction
from src.control_center.services.retry_engine_service import classify_failure, process_retry_queue
from src.control_center.services.scheduler_service import execute_maintenance_cycle, get_scheduler_status, toggle_scheduler_task
from src.control_center.services.search_ranking_service import rank_search_results
from src.database import ArchiveDatabase


def test_feedback_learning_and_audit_trail(tmp_path, monkeypatch):
    """Test human face & scene feedback loop and immutable audit event ledger."""
    from src.config import load_config
    config = load_config()
    test_db = tmp_path / "archive_feedback.sqlite3"
    db = ArchiveDatabase(test_db)
    db.apply_migrations(Path("sql"))

    with db.connect() as conn:
        c1 = conn.execute("INSERT INTO people (person_slug, display_name, active, created_at, updated_at) VALUES ('alice', 'Alice', 1, '2026-08-25', '2026-08-25')")
        p_id = c1.lastrowid
        c_m = conn.execute("INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, discovered_at, updated_at) VALUES ('sha_fb', 'sh_fb', 'fb.jpg', 'fb.jpg', 'image', 1000, 0, 'BACKED_UP', '[\"Dining\"]', '2026-08-25', '2026-08-25', '2026-08-25')")
        mid = c_m.lastrowid
        c_att = conn.execute("INSERT INTO face_analysis_attempts (media_id, analysis_key, analysis_version, model_identity, reference_set_hash, started_at, finished_at, outcome, detected_face_count, accepted_match_count, unknown_face_count) VALUES (?, 'k', 1, 'm', 'h', '2026-08-25', '2026-08-25', 'SUCCESS', 1, 0, 1)", (mid,))
        att_id = c_att.lastrowid
        c_face = conn.execute("INSERT INTO media_faces (media_id, attempt_id, face_index, detector_confidence, best_person_id, best_score, decision, analyzed_at) VALUES (?, ?, 0, 0.90, NULL, NULL, 'UNKNOWN', '2026-08-25')", (mid, att_id))
        fid = c_face.lastrowid
        conn.commit()

    monkeypatch.setattr(config.app, "database_path", str(test_db))
    monkeypatch.setattr("src.control_center.services.feedback_learning_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.services.audit_service.load_config", lambda: config)

    # 1. Apply face confirmation feedback
    fb_res = record_face_feedback(
        media_id=mid,
        action="CONFIRM",
        face_id=fid,
        person_id=p_id,
        new_identity="Alice"
    )
    assert fb_res["success"] is True
    assert fb_res["target_person_id"] == p_id

    # 2. Apply scene correction feedback
    sc_res = record_scene_feedback(
        media_id=mid,
        new_label="Office",
        confidence=0.99
    )
    assert sc_res["success"] is True
    assert "Office" in sc_res["labels"]

    # 3. Verify audit timeline recorded both actions
    timeline = get_audit_timeline(limit=10)
    assert timeline["total_events"] >= 2
    actions = [e["action"] for e in timeline["events"]]
    assert any("FACE_FEEDBACK" in a for a in actions)
    assert any("SCENE_FEEDBACK" in a for a in actions)


def test_autonomous_retry_engine_and_failure_classification(tmp_path, monkeypatch):
    """Test failure classification (transient vs permanent) and autonomous retry handling."""
    from src.config import load_config
    config = load_config()
    test_db = tmp_path / "archive_retry.sqlite3"
    db = ArchiveDatabase(test_db)
    db.apply_migrations(Path("sql"))

    # Classification unit test
    assert classify_failure("Telegram rate limit 429")["retryable"] is True
    assert classify_failure("database is locked")["retryable"] is True
    assert classify_failure("Corrupted JPEG file header")["retryable"] is False

    monkeypatch.setattr(config.app, "database_path", str(test_db))
    monkeypatch.setattr("src.control_center.services.retry_engine_service.load_config", lambda: config)

    # Process empty or active queue
    res = process_retry_queue()
    assert res["success"] is True


def test_perceptual_hashing_and_near_deduplication(tmp_path, monkeypatch):
    """Test dHash computation, hamming distance, and near-duplicate burst detection."""
    from src.config import load_config
    config = load_config()
    test_db = tmp_path / "archive_dedup.sqlite3"
    db = ArchiveDatabase(test_db)
    db.apply_migrations(Path("sql"))

    # Create two nearly identical test images with patterns
    img1 = tmp_path / "burst_01.jpg"
    img2 = tmp_path / "burst_02.jpg"
    
    im1 = Image.new("RGB", (100, 100), color=(120, 150, 200))
    for x in range(50):
        im1.putpixel((x, x), (255, 0, 0))
    im1.save(img1)

    im2 = Image.new("RGB", (100, 100), color=(122, 150, 200))  # Almost identical
    for x in range(50):
        im2.putpixel((x, x), (255, 0, 0))
    im2.save(img2)

    h1 = compute_dhash(str(img1))
    h2 = compute_dhash(str(img2))
    assert len(h1) == 16
    assert compute_hamming_distance(h1, h2) <= 5

    with db.connect() as conn:
        conn.execute("INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, discovered_at, updated_at) VALUES ('sha_b1', 'b1', ?, 'burst_01.jpg', 'image', 1000, 0, 'BACKED_UP', '[]', '2026-08-25', '2026-08-25', '2026-08-25')", (str(img1),))
        conn.execute("INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, discovered_at, updated_at) VALUES ('sha_b2', 'b2', ?, 'burst_02.jpg', 'image', 1000, 0, 'BACKED_UP', '[]', '2026-08-25', '2026-08-25', '2026-08-25')", (str(img2),))
        conn.commit()

    monkeypatch.setattr(config.app, "database_path", str(test_db))
    monkeypatch.setattr("src.control_center.services.deduplication_service.load_config", lambda: config)

    scan_res = scan_for_near_duplicates(distance_threshold=5)
    assert scan_res["total_images_scanned"] == 2
    assert scan_res["near_duplicate_clusters_count"] == 1


def test_portable_archive_export_bundle(tmp_path, monkeypatch):
    """Test generating a standalone portable MyArchive directory and zip bundle."""
    from src.config import load_config
    config = load_config()
    test_db = tmp_path / "archive_portable.sqlite3"
    db = ArchiveDatabase(test_db)
    db.apply_migrations(Path("sql"))

    img_f = tmp_path / "travel_photo.jpg"
    Image.new("RGB", (50, 50), color=(100, 200, 100)).save(img_f)

    with db.connect() as conn:
        conn.execute("INSERT INTO people (person_slug, display_name, active, created_at, updated_at) VALUES ('traveler', 'Traveler Bob', 1, '2026-08-25', '2026-08-25')")
        conn.execute("INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, people_json, date_taken, discovered_at, updated_at) VALUES ('sha_p', 'shp', ?, 'travel_photo.jpg', 'image', 500, 0, 'BACKED_UP', '[\"Nature\"]', '[\"Traveler Bob\"]', '2026-08-25', '2026-08-25', '2026-08-25')", (str(img_f),))
        conn.commit()

    monkeypatch.setattr(config.app, "database_path", str(test_db))
    monkeypatch.setattr("src.control_center.services.portable_archive_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.services.portable_archive_service.EXPORTS_DIR", tmp_path / "exports")

    bundle_res = export_portable_archive_bundle()
    assert bundle_res["success"] is True
    assert bundle_res["media_count"] == 1
    assert bundle_res["people_count"] == 1
    assert bundle_res["photos_copied"] == 1
    assert Path(bundle_res["bundle_path"]).exists()


def test_memory_quality_evaluation_and_lifecycle(tmp_path, monkeypatch):
    """Test 100-point AI memory quality scorecard and media lifecycle reporting."""
    from src.config import load_config
    config = load_config()
    test_db = tmp_path / "archive_eval.sqlite3"
    db = ArchiveDatabase(test_db)
    db.apply_migrations(Path("sql"))

    with db.connect() as conn:
        conn.execute("INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, face_state, scene_state, labels_json, date_taken, discovered_at, updated_at) VALUES ('sha_ev', 'shev', 'ev.jpg', 'ev.jpg', 'image', 500, 0, 'BACKED_UP', 'ANALYZED', 'ANALYZED', '[\"Trip\"]', '2026-08-25', '2026-08-25', '2026-08-25')")
        conn.commit()

    monkeypatch.setattr(config.app, "database_path", str(test_db))
    monkeypatch.setattr("src.control_center.services.lifecycle_service.load_config", lambda: config)

    # Lifecycle test
    lc = get_media_lifecycle_summary()
    assert lc["total_media"] == 1
    assert lc["lifecycle_stages"]["BACKED_UP"] == 1
    assert lc["completion_rate_pct"] == 100.0

    # Memory Quality Scorecard test
    eval_res = evaluate_memory_quality()
    assert "archive_average_memory_score" in eval_res
    assert "dimension_averages" in eval_res
