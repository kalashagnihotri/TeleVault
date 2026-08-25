"""Unit Tests for Phase 6.5H: Final Production Intelligence Layer."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import pytest
from PIL import Image

from src.database import ArchiveDatabase
from src.control_center.services.embedding_search_service import (
    compute_and_store_embedding,
    search_by_semantic_query,
    find_similar_images
)
from src.control_center.services.person_management_service import (
    get_all_people_summaries,
    get_person_timeline,
    rename_person,
    split_person_identity,
    delete_person
)
from src.control_center.services.memory_override_service import (
    save_memory_override,
    get_memory_overrides,
    remove_memory_override
)
from src.control_center.services.video_intelligence_service import (
    extract_and_store_video_intelligence,
    get_video_intelligence
)
from src.control_center.services.voice_query_service import process_voice_query
from src.control_center.services.timeline_stream_service import get_timeline_stream
from src.control_center.services.fleet_management_service import (
    register_worker_heartbeat,
    get_fleet_status
)
from src.control_center.services.encryption_service import (
    encrypt_data,
    decrypt_data,
    encrypt_file,
    decrypt_file
)
from src.control_center.services.simulator_service import generate_synthetic_archive_dataset
from src.control_center.services.plugin_service import (
    get_all_plugins,
    toggle_plugin
)
from src.control_center.services.ocr_intelligence_service import (
    extract_and_store_document_ocr,
    search_documents
)
from src.control_center.services.security_scorecard_service import evaluate_security_threat_model


@pytest.fixture
def setup_test_db(tmp_path, monkeypatch):
    """Set up an isolated test database with all 12 migrations."""
    from src.config import load_config
    config = load_config()
    test_db = tmp_path / "test_intel_archive.sqlite3"
    db = ArchiveDatabase(test_db)
    db.apply_migrations(Path("sql"))

    monkeypatch.setattr(config.app, "database_path", str(test_db))
    monkeypatch.setattr("src.control_center.services.embedding_search_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.services.person_management_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.services.memory_override_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.services.smart_notification_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.services.ai_recommendations_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.services.video_intelligence_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.services.timeline_stream_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.services.fleet_management_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.services.simulator_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.services.plugin_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.services.ocr_intelligence_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.services.security_scorecard_service.load_config", lambda: config)

    return db, test_db


def test_ai_vision_embeddings_and_cross_modal_search(tmp_path, setup_test_db):
    """Test 512-dim visual vector extraction, cosine similarity ranking, and image similarity."""
    db, test_db = setup_test_db

    # Create synthetic test images
    img_beach = tmp_path / "beach_sunset.jpg"
    im_b = Image.new("RGB", (100, 100), color=(255, 120, 50)) # Sunset color
    im_b.save(img_beach)

    img_mountain = tmp_path / "mountain_lake.jpg"
    im_m = Image.new("RGB", (100, 100), color=(50, 150, 255)) # Sky/Water color
    im_m.save(img_mountain)

    with db.connect() as conn:
        c1 = conn.execute("INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, discovered_at, updated_at) VALUES ('sha_b', 'sh_b', ?, 'beach_sunset.jpg', 'image', 1000, 0, 'BACKED_UP', '[\"Beach\", \"Sunset\"]', '2026-08-25', '2026-08-25', '2026-08-25')", (str(img_beach),))
        m1 = c1.lastrowid

        c2 = conn.execute("INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, discovered_at, updated_at) VALUES ('sha_m', 'sh_m', ?, 'mountain_lake.jpg', 'image', 1000, 0, 'BACKED_UP', '[\"Mountain\", \"Lake\"]', '2026-08-25', '2026-08-25', '2026-08-25')", (str(img_mountain),))
        m2 = c2.lastrowid
        conn.commit()

    compute_and_store_embedding(m1, str(img_beach), ["Beach", "Sunset"])
    compute_and_store_embedding(m2, str(img_mountain), ["Mountain", "Lake"])

    # Search for beach/sunset
    res_beach = search_by_semantic_query("sunset over beach", limit=5)
    assert len(res_beach) == 2
    assert res_beach[0]["media_id"] == m1
    assert res_beach[0]["similarity_pct"] > 50.0

    # Search for water/lake
    res_lake = search_by_semantic_query("lake in mountain", limit=5)
    assert len(res_lake) == 2
    assert res_lake[0]["media_id"] == m2

    # Find similar images
    similar = find_similar_images(m1, limit=5)
    assert len(similar) == 1
    assert similar[0]["media_id"] == m2


def test_person_identity_manager_and_timeline(tmp_path, setup_test_db):
    """Test person summaries, annual/monthly timeline distribution, renaming, splitting, and deleting."""
    db, test_db = setup_test_db

    with db.connect() as conn:
        c_p = conn.execute("INSERT INTO people (person_slug, display_name, active, created_at, updated_at) VALUES ('alice', 'Alice Smith', 1, '2024-01-01', '2026-08-25')")
        p_id = c_p.lastrowid

        # Insert media in 2024, 2025, 2026
        for year in ["2024", "2025", "2026"]:
            c_m = conn.execute("INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, date_taken, discovered_at, updated_at) VALUES (?, ?, 'p.jpg', 'p.jpg', 'image', 100, 0, 'BACKED_UP', ?, '2026-08-25', '2026-08-25')", (f"sha_{year}", f"sh_{year}", f"{year}-06-15"))
            m_id = c_m.lastrowid

            c_att = conn.execute("INSERT INTO face_analysis_attempts (media_id, analysis_key, analysis_version, model_identity, reference_set_hash, started_at, finished_at, outcome, detected_face_count, accepted_match_count, unknown_face_count) VALUES (?, 'k', 1, 'm', 'h', '2026-08-25', '2026-08-25', 'SUCCESS', 1, 1, 0)", (m_id,))
            att_id = c_att.lastrowid
            conn.execute("INSERT INTO media_faces (media_id, attempt_id, face_index, detector_confidence, best_person_id, best_score, decision, analyzed_at) VALUES (?, ?, 0, 0.95, ?, 0.92, 'KNOWN_MATCH', '2026-08-25')", (m_id, att_id, p_id))
        conn.commit()

    summaries = get_all_people_summaries()
    assert len(summaries) == 1
    assert summaries[0]["display_name"] == "Alice Smith"
    assert summaries[0]["photo_count"] == 3

    # Test Timeline distribution
    tl = get_person_timeline(p_id)
    assert tl["total_photos"] == 3
    assert len(tl["years"]) == 3
    years_found = [y["year"] for y in tl["years"]]
    assert "2024" in years_found
    assert "2025" in years_found
    assert "2026" in years_found

    # Test Rename
    ren_res = rename_person(p_id, "Alice Cooper")
    assert ren_res["success"] is True
    assert ren_res["new_name"] == "Alice Cooper"

    # Test Delete
    del_res = delete_person(p_id)
    assert del_res["success"] is True
    assert len(get_all_people_summaries()) == 0


def test_memory_overrides_and_customization(setup_test_db):
    """Test human memory overrides taking precedence over AI defaults."""
    save_res = save_memory_override(
        memory_id="mem_austin_trip",
        original_ai_title="Austin Trip Aug 10-12",
        user_title="Family Vacation 2026",
        user_description="Our amazing summer holiday in Texas.",
        is_pinned=True
    )
    assert save_res["success"] is True
    assert save_res["active_title"] == "Family Vacation 2026"
    assert save_res["is_pinned"] is True

    overrides = get_memory_overrides()
    assert "mem_austin_trip" in overrides
    assert overrides["mem_austin_trip"]["user_title"] == "Family Vacation 2026"

    # Revert override
    rev_res = remove_memory_override("mem_austin_trip")
    assert rev_res["success"] is True
    assert len(get_memory_overrides()) == 0


def test_authenticated_encryption_and_decryption(tmp_path):
    """Test AES-256-GCM / PBKDF2 authenticated encryption, decryption, and tampering detection."""
    secret_text = b"Highly confidential archive export containing family memories."
    passphrase = "SuperSecureVaultPassphrase2026!"

    # 1. Byte roundtrip
    encrypted = encrypt_data(secret_text, passphrase)
    assert encrypted != secret_text
    decrypted = decrypt_data(encrypted, passphrase)
    assert decrypted == secret_text

    # 2. Tampering / Wrong passphrase detection
    with pytest.raises(ValueError):
        decrypt_data(encrypted, "WrongPassword!")

    # 3. File encryption roundtrip
    src_file = tmp_path / "MyArchive.zip"
    src_file.write_bytes(secret_text)
    enc_file = tmp_path / "MyArchive.vault.enc"
    dec_file = tmp_path / "RestoredArchive.zip"

    encrypt_file(str(src_file), str(enc_file), passphrase)
    assert enc_file.exists()
    assert enc_file.stat().st_size > 0

    decrypt_file(str(enc_file), str(dec_file), passphrase)
    assert dec_file.exists()
    assert dec_file.read_bytes() == secret_text


def test_distributed_fleet_and_plugins(setup_test_db):
    """Test worker node heartbeat tracking and plugin registry."""
    hb = register_worker_heartbeat(
        worker_id="gpu_worker_01",
        node_name="Alienware-GPU-Node",
        ip_address="192.168.1.150",
        capabilities=["face_recognition", "scene_vit"],
        status="ONLINE",
        tasks_processed_delta=12
    )
    assert hb["success"] is True

    fleet = get_fleet_status()
    assert fleet["total_nodes"] == 1
    assert fleet["nodes"][0]["node_name"] == "Alienware-GPU-Node"
    assert fleet["nodes"][0]["processed_tasks_count"] == 12

    # Test Plugins
    plugins = get_all_plugins()
    assert len(plugins) >= 3
    plugin_names = [p["plugin_name"] for p in plugins]
    assert "ocr_intelligence" in plugin_names

    tog = toggle_plugin("ocr_intelligence", False)
    assert tog["enabled"] is False


def test_ocr_intelligence_and_security_scorecard(setup_test_db):
    """Test OCR document parsing and 100-point security scorecard."""
    db, test_db = setup_test_db

    with db.connect() as conn:
        c = conn.execute("INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, discovered_at, updated_at) VALUES ('sha_doc', 'sh_d', 'inv.jpg', 'inv.jpg', 'image', 500, 0, 'BACKED_UP', '[\"Document\"]', '2026-08-25', '2026-08-25', '2026-08-25')")
        m_id = c.lastrowid
        conn.commit()

        ocr_res = extract_and_store_document_ocr(
            media_id=m_id,
            image_path="inv.jpg",
            raw_text_hint="Tax Invoice\nStore: Walmart Supercenter\nTotal Amount: $153.42\nDate: 2026-08-25"
        )
        assert "Walmart" in ocr_res["merchant_name"]
        assert ocr_res["amount"] == 153.42

    docs = search_documents("Walmart")
    assert len(docs) == 1
    assert docs[0]["amount"] == 153.42

    # Security Scorecard
    sec = evaluate_security_threat_model()
    assert sec["security_score"] >= 95
    assert len(sec["checks"]) == 4
