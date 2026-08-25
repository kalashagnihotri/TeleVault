import pytest
from fastapi.testclient import TestClient
from src.control_center.app import app
import os
import sqlite3
import shutil
from pathlib import Path
from src.database import ArchiveDatabase
from src.control_center.services import (
    db_service, metrics_service, integrity_service,
    face_management_service, scene_management_service,
    disaster_recovery_service, security_service, thumbnail_service
)


@pytest.fixture(autouse=True)
def setup_teardown(tmp_path):
    test_db = tmp_path / "test_fault_injection.sqlite3"
    db_service.DB_PATH = test_db
    db_service.init_db()
    yield
    try:
        if test_db.exists():
            os.remove(test_db)
    except PermissionError:
        pass


def test_metrics_and_retry_intelligence(tmp_path, monkeypatch):
    """Test pipeline stage latency tracking, failure analytics, and intelligent retry tracking."""
    from src.config import load_config
    config = load_config()
    test_db_path = tmp_path / "archive_metrics.sqlite3"

    db = ArchiveDatabase(test_db_path)
    db.apply_migrations(Path("sql"))

    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, face_state, scene_state, labels_json, date_taken, discovered_at, updated_at)
            VALUES ('sha_m1', 'sha_m1', 'img1.jpg', 'img1.jpg', 'image', 500000, 0, 'BACKED_UP', 'DONE', 'DONE', '["nature"]', '2026-08-25', '2026-08-25', '2026-08-25'),
                   ('sha_m2', 'sha_m2', 'img2.jpg', 'img2.jpg', 'image', 600000, 0, 'FAILED', 'FAILED', 'DONE', '[]', '2026-08-25', '2026-08-25', '2026-08-25')
            """
        )
        conn.commit()

    monkeypatch.setattr(config.app, "database_path", str(test_db_path))
    monkeypatch.setattr("src.control_center.services.metrics_service.load_config", lambda: config)

    # Record stage timings
    metrics_service.record_stage_timing("metadata", 85.0)
    metrics_service.record_stage_timing("face", 910.0)
    metrics_service.record_stage_timing("scene", 2150.0)
    metrics_service.record_stage_timing("upload", 3200.0)

    # Schedule retry
    metrics_service.schedule_retry(media_id=2, filename="img2.jpg", stage="upload", reason="Telegram timeout", attempt=2, backoff_seconds=30)

    with TestClient(app) as client:
        # Pipeline metrics
        res_m = client.get("/api/metrics/pipeline")
        assert res_m.status_code == 200
        m_data = res_m.json()
        assert m_data["total_processed"] == 2
        assert m_data["successful"] == 1
        assert m_data["failed"] == 1
        assert "stage_latencies" in m_data
        assert m_data["stage_latencies"]["face"]["avg_ms"] > 0

        # Failure analytics
        res_f = client.get("/api/metrics/failures")
        assert res_f.status_code == 200
        f_data = res_f.json()
        assert f_data["failure_counts"]["face_failures"] == 1
        assert f_data["failure_counts"]["telegram_upload_failures"] == 1

        # Retry queue
        res_r = client.get("/api/metrics/retries")
        assert res_r.status_code == 200
        r_data = res_r.json()
        assert len(r_data) >= 1
        assert r_data[-1]["attempt"] == 2


def test_archive_health_integrity_scanner(tmp_path, monkeypatch):
    """Test deep integrity scanner detecting zero-byte files, hash mismatches, and unconfirmed backups."""
    from src.config import load_config
    config = load_config()
    test_db_path = tmp_path / "archive_integrity.sqlite3"

    db = ArchiveDatabase(test_db_path)
    db.apply_migrations(Path("sql"))

    # Create dummy files
    good_file = tmp_path / "good.jpg"
    good_file.write_bytes(b"VALID_IMAGE_BYTES_123456789")
    import hashlib
    good_sha = hashlib.sha256(b"VALID_IMAGE_BYTES_123456789").hexdigest()

    zero_file = tmp_path / "zero.jpg"
    zero_file.write_bytes(b"")

    with db.connect() as conn:
        # Valid backed up row
        c1 = conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, discovered_at, updated_at)
            VALUES (?, 'good', ?, 'good.jpg', 'image', 26, 0, 'BACKED_UP', '[]', '2026-08-25', '2026-08-25', '2026-08-25')
            """,
            (good_sha, str(good_file))
        )
        m1 = c1.lastrowid
        conn.execute("INSERT INTO telegram_archive (media_id, group_id, topic_id, preview_message_id, original_message_id) VALUES (?, '-1001', '1', '100', '101')", (m1,))

        # Zero-byte invalid row
        conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, discovered_at, updated_at)
            VALUES ('sha_zero', 'zero', ?, 'zero.jpg', 'image', 0, 0, 'PENDING', '[]', '2026-08-25', '2026-08-25', '2026-08-25')
            """,
            (str(zero_file),)
        )
        conn.commit()

    monkeypatch.setattr(config.app, "database_path", str(test_db_path))
    monkeypatch.setattr("src.control_center.services.integrity_service.load_config", lambda: config)

    with TestClient(app) as client:
        res = client.post("/api/integrity/scan")
        assert res.status_code == 200
        data = res.json()
        assert data["total_files_audited"] == 2
        assert data["issues_count"] >= 1
        assert any(i["error_type"] == "ZERO_BYTE_FILE" for i in data["issues"])


def test_face_review_queue_and_merge_identities(tmp_path, monkeypatch):
    """Test unknown face clustering, new identity enrollment, and identity merging."""
    from src.config import load_config
    config = load_config()
    test_db_path = tmp_path / "archive_faces_mgmt.sqlite3"

    db = ArchiveDatabase(test_db_path)
    db.apply_migrations(Path("sql"))

    with db.connect() as conn:
        c1 = conn.execute("INSERT INTO people (person_slug, display_name, active, created_at, updated_at) VALUES ('alice', 'Alice Original', 1, '2026-08-01', '2026-08-01')")
        p_alice = c1.lastrowid
        c2 = conn.execute("INSERT INTO people (person_slug, display_name, active, created_at, updated_at) VALUES ('alice_2', 'Alice Duplicate', 1, '2026-08-01', '2026-08-01')")
        p_dup = c2.lastrowid

        c_m = conn.execute("INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, discovered_at, updated_at) VALUES ('sha_f', 'shf', 'f.jpg', 'f.jpg', 'image', 1000, 0, 'BACKED_UP', '[]', '2026-08-25', '2026-08-25', '2026-08-25')")
        mid = c_m.lastrowid

        # Insert attempt row
        c_att = conn.execute("INSERT INTO face_analysis_attempts (media_id, analysis_key, analysis_version, model_identity, reference_set_hash, started_at, finished_at, outcome, detected_face_count, accepted_match_count, unknown_face_count) VALUES (?, 'k', 1, 'm', 'h', '2026-08-25', '2026-08-25', 'SUCCESS', 2, 1, 1)", (mid,))
        att_id = c_att.lastrowid

        # Unknown face
        conn.execute("INSERT INTO media_faces (media_id, attempt_id, face_index, detector_confidence, best_person_id, best_score, decision, analyzed_at) VALUES (?, ?, 0, 0.92, NULL, NULL, 'UNKNOWN', '2026-08-25')", (mid, att_id))
        # Face assigned to duplicate
        conn.execute("INSERT INTO media_faces (media_id, attempt_id, face_index, detector_confidence, best_person_id, best_score, decision, analyzed_at) VALUES (?, ?, 1, 0.95, ?, 0.88, 'KNOWN_MATCH', '2026-08-25')", (mid, att_id, p_dup))
        conn.commit()

    monkeypatch.setattr(config.app, "database_path", str(test_db_path))
    monkeypatch.setattr("src.control_center.services.face_management_service.load_config", lambda: config)

    with TestClient(app) as client:
        # 1. Fetch unknown clusters
        res_c = client.get("/api/faces/unknown_clusters")
        assert res_c.status_code == 200
        clusters = res_c.json()
        assert len(clusters) >= 1

        # 2. Merge duplicate identity into canonical Alice
        res_m = client.post("/api/faces/merge_identities", json={"source_person_id": p_dup, "target_person_id": p_alice})
        assert res_m.status_code == 200
        m_data = res_m.json()
        assert m_data["success"] is True
        assert m_data["reassigned_faces_count"] == 1


def test_disaster_recovery_restore_verification_and_export(tmp_path, monkeypatch):
    """Test full restore test into temporary database and standalone archive export."""
    from src.config import load_config
    config = load_config()
    test_db_path = tmp_path / "archive_dr.sqlite3"

    db = ArchiveDatabase(test_db_path)
    db.apply_migrations(Path("sql"))

    with db.connect() as conn:
        conn.execute("INSERT INTO people (person_slug, display_name, active, created_at, updated_at) VALUES ('dr_person', 'DR Test Person', 1, '2026-08-25', '2026-08-25')")
        conn.execute("INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, discovered_at, updated_at) VALUES ('sha_dr', 'sh_dr', 'dr.jpg', 'dr.jpg', 'image', 5000, 0, 'BACKED_UP', '[\"test\"]', '2026-08-25', '2026-08-25', '2026-08-25')")
        conn.commit()

    monkeypatch.setattr(config.app, "database_path", str(test_db_path))
    monkeypatch.setattr("src.control_center.services.disaster_recovery_service.load_config", lambda: config)

    with TestClient(app) as client:
        # Restore dry-run test
        res_r = client.post("/api/maintenance/restore/test")
        assert res_r.status_code == 200
        r_data = res_r.json()
        assert r_data["test_status"] == "PASSED"
        assert r_data["integrity_check"] == "ok"
        assert r_data["total_discrepancies"] == 0

        # Standalone archive export
        res_e = client.post("/api/maintenance/export")
        assert res_e.status_code == 200
        e_data = res_e.json()
        assert e_data["success"] is True
        assert e_data["media_exported"] == 1
        assert e_data["people_exported"] == 1



def test_secrets_audit_and_upload_security():
    """Test secrets audit scanner and file upload sanitization."""
    # Secrets audit
    audit = security_service.audit_secrets_in_logs_and_diagnostics()
    assert "status" in audit
    assert "safe_redaction_verified" in audit

    # Upload validation
    res = security_service.validate_upload_security("../malicious/../../test.png", 5000)
    assert res["valid"] is True
    assert ".." not in res["sanitized_filename"]
    assert "/" not in res["sanitized_filename"]
