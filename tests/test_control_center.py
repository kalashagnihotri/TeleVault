import pytest
from fastapi.testclient import TestClient
from src.control_center.app import app
import os
import io
import json
import sqlite3
import asyncio
from pathlib import Path
from PIL import Image
import yaml
from src.control_center.services import (
    db_service, 
    config_service, 
    snapshot_service, 
    model_service, 
    diagnostic_service,
    intelligence_service
)
from src.control_center.pipeline_runner import run_controlled_pipeline
from src.database import ArchiveDatabase
from src.routing import RouteInput, explain_routing, choose_topic

@pytest.fixture(autouse=True)
def setup_teardown(tmp_path, monkeypatch):
    test_db = tmp_path / "test_control_center.sqlite3"
    db_service.DB_PATH = test_db
    db_service.init_db()
    yield
    try:
        if test_db.exists():
            os.remove(test_db)
    except PermissionError:
        pass


def test_health():
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_system():
    with TestClient(app) as client:
        response = client.get("/api/system")
        assert response.status_code == 200
        data = response.json()
        assert data["control_center"]["backend_running"] is True
        assert "executable" in data["python"]


def test_system_safe_mode():
    with TestClient(app) as client:
        r = client.get("/api/system/mode")
        assert r.status_code == 200
        assert r.json()["mode"] == "safe"

        r2 = client.post("/api/system/mode", json={"mode": "production"})
        assert r2.status_code == 200
        assert r2.json()["mode"] == "production"

        r3 = client.post("/api/system/mode", json={"mode": "safe"})
        assert r3.status_code == 200
        assert r3.json()["mode"] == "safe"


def test_safe_mode_blocks_live_jobs():
    with TestClient(app) as client:
        client.post("/api/system/mode", json={"mode": "safe"})

        # LIVE risk level blocked
        res = client.post("/api/jobs/start", json={"profile_id": "pipeline_live"})
        assert res.status_code == 403
        assert res.json()["detail"]["code"] == "SAFE_MODE_ACTIVE"

        # SAFE profile allowed
        res2 = client.post("/api/jobs/start", json={"profile_id": "queue_inspect"})
        assert res2.status_code in (200, 409)


def test_system_health_score_endpoint():
    with TestClient(app) as client:
        resp = client.get("/api/system/health_score")
        assert resp.status_code == 200
        data = resp.json()
        assert "score" in data
        assert 0 <= data["score"] <= 100
        assert data["status"] in ("HEALTHY", "DEGRADED", "CRITICAL")
        check_ids = [c["id"] for c in data["checks"]]
        assert "database" in check_ids
        assert "models" in check_ids
        assert "telegram" in check_ids
        assert "queue" in check_ids


def test_run_full_diagnostic_endpoint(tmp_path, monkeypatch):
    test_reports_dir = tmp_path / "diagnostic_reports"
    test_reports_dir.mkdir()
    monkeypatch.setattr(diagnostic_service, "REPORTS_DIR", test_reports_dir)

    with TestClient(app) as client:
        resp = client.post("/api/system/run_diagnostic")
        assert resp.status_code == 200
        data = resp.json()
        assert "report_id" in data
        assert "overall_status" in data
        assert len(data["tests"]) >= 5

        # Check list & download
        list_resp = client.get("/api/system/diagnostic_reports")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) >= 1

        dl_resp = client.get(f"/api/system/diagnostic_reports/{data['filename']}/download")
        assert dl_resp.status_code == 200


def test_config_diff_endpoint(tmp_path, monkeypatch):
    test_cfg_path = tmp_path / "config.yaml"
    initial_config = {
        "cleanup": {"enabled": False, "backup_safety_days": 7},
        "telegram": {"group_id": "123", "caption_max_length": 900}
    }
    with open(test_cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(initial_config, f)

    monkeypatch.setattr(config_service, "CONFIG_PATH", test_cfg_path)

    with TestClient(app) as client:
        # Diff with modified values
        new_config = {
            "cleanup": {"enabled": True, "backup_safety_days": 7},
            "telegram": {"group_id": "123", "caption_max_length": 850}
        }
        diff_res = client.post("/api/config/diff", json={"config": new_config})
        assert diff_res.status_code == 200
        diffs = diff_res.json()
        assert len(diffs) == 2
        paths = [d["path"] for d in diffs]
        assert "cleanup.enabled" in paths
        assert "telegram.caption_max_length" in paths

        cleanup_diff = next(d for d in diffs if d["path"] == "cleanup.enabled")
        assert cleanup_diff["old_value"] is False
        assert cleanup_diff["new_value"] is True
        assert cleanup_diff["change_type"] == "MODIFIED"


def test_intelligent_multi_clause_archive_search(tmp_path, monkeypatch):
    from src.config import load_config
    config = load_config()
    test_db_path = tmp_path / "archive_multi_search.sqlite3"

    db = ArchiveDatabase(test_db_path)
    db.apply_migrations(Path("sql"))

    with db.connect() as conn:
        cursor = conn.execute(
            "INSERT INTO people (person_slug, display_name, active, created_at, updated_at) VALUES ('alice_walker', 'Alice Walker', 1, '2026-08-01', '2026-08-01')"
        )
        person_id = cursor.lastrowid

        # Item 1: Screenshot with Alice taken in 2025
        cursor = conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, discovered_at, updated_at)
            VALUES ('sha_shot_alice', 'sha_shot', 'shot.png', 'receipt_screenshot.png', 'image', 1234, 0, 'BACKED_UP', '["screenshot", "receipt"]', '2025-06-15', '2026-08-01', '2026-08-01')
            """
        )
        media_id1 = cursor.lastrowid

        cursor = conn.execute(
            """
            INSERT INTO face_analysis_attempts (media_id, analysis_key, analysis_version, model_identity, reference_set_hash, started_at, finished_at, outcome, detected_face_count, accepted_match_count, unknown_face_count)
            VALUES (?, 'k1', 1, 'm1', 'h1', '2026-08-01', '2026-08-01', 'SUCCESS', 1, 1, 0)
            """,
            (media_id1,)
        )
        att_id1 = cursor.lastrowid
        conn.execute(
            """
            INSERT INTO media_faces (media_id, attempt_id, face_index, detector_confidence, best_person_id, best_score, decision, analyzed_at)
            VALUES (?, ?, 0, 0.95, ?, 0.88, 'KNOWN_MATCH', '2026-08-01')
            """,
            (media_id1, att_id1, person_id)
        )

        # Item 2: Nature photo without Alice from 2026
        conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, discovered_at, updated_at)
            VALUES ('sha_nature', 'sha_nat', 'nature.jpg', 'nature_mountains.jpg', 'image', 5678, 0, 'BACKED_UP', '["mountains", "nature"]', '2026-07-20', '2026-08-01', '2026-08-01')
            """
        )
        conn.commit()

    monkeypatch.setattr(config.app, "database_path", str(test_db_path))
    monkeypatch.setattr("src.control_center.api.archive.load_config", lambda: config)

    with TestClient(app) as client:
        # Multi-clause: "screenshots with Alice" -> should match item 1 ONLY
        res1 = client.get("/api/archive/search?q=screenshots with Alice")
        assert res1.status_code == 200
        items1 = res1.json()
        assert len(items1) == 1
        assert items1[0]["original_filename"] == "receipt_screenshot.png"

        # Date query: "receipts from 2025" -> should match item 1
        res2 = client.get("/api/archive/search?q=receipt from 2025")
        assert res2.status_code == 200
        assert len(res2.json()) == 1

        # Query "nature from 2025" -> should return 0 (nature was 2026)
        res3 = client.get("/api/archive/search?q=nature from 2025")
        assert res3.status_code == 200
        assert len(res3.json()) == 0

        # Query "mountains in 2026" -> should return 1 (nature photo)
        res4 = client.get("/api/archive/search?q=mountains in 2026")
        assert res4.status_code == 200
        assert len(res4.json()) == 1


def _create_test_image_bytes(color=(255, 0, 0), size=(100, 100)) -> bytes:
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_queue_ingest_and_import_history(tmp_path, monkeypatch):
    from src.config import load_config
    config = load_config()
    test_img_dir = tmp_path / "incoming_images"
    test_vid_dir = tmp_path / "incoming_videos"
    test_img_dir.mkdir()
    test_vid_dir.mkdir()
    
    monkeypatch.setattr(config.queue, "incoming_images", str(test_img_dir))
    monkeypatch.setattr(config.queue, "incoming_videos", str(test_vid_dir))
    monkeypatch.setattr("src.control_center.api.ingestion.load_config", lambda: config)

    img_bytes = _create_test_image_bytes()
    with TestClient(app) as client:
        response = client.post(
            "/api/queue/ingest",
            files=[("files", ("history_test.png", img_bytes, "image/png"))]
        )
        assert response.status_code == 200
        results = response.json()
        assert len(results) == 1
        assert results[0]["status"] == "IMPORT_COMPLETE"

        hist_resp = client.get("/api/queue/imports?limit=10")
        assert hist_resp.status_code == 200
        history = hist_resp.json()
        assert len(history) >= 1
        record = history[0]
        assert record["original_filename"] == "history_test.png"
        assert record["status"] == "COMPLETE"
        assert record["size_bytes"] == len(img_bytes)


def test_pipeline_timeline_endpoint(tmp_path, monkeypatch):
    from src.config import load_config
    config = load_config()
    test_db_path = tmp_path / "archive_timeline.sqlite3"

    db = ArchiveDatabase(test_db_path)
    db.apply_migrations(Path("sql"))

    with db.connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, face_state, scene_state, labels_json, discovered_at, updated_at)
            VALUES ('sha_time', 'sha_time', 'vacation.jpg', 'vacation.jpg', 'image', 4500, 0, 'BACKED_UP', 'COMPLETED', 'COMPLETED', '["beach", "ocean"]', '2026-08-01T10:00:00Z', '2026-08-01T10:05:00Z')
            """
        )
        media_id = cursor.lastrowid
        conn.execute(
            """
            INSERT INTO telegram_archive (media_id, group_id, topic_id, preview_message_id, original_message_id, telegram_file_id, upload_confirmed_at, retry_stage, route_key)
            VALUES (?, 123, 5, 201, 202, 'file_vac', '2026-08-01T10:05:00Z', 'DONE', 'travel_nature')
            """,
            (media_id,)
        )
        conn.commit()

    monkeypatch.setattr(config.app, "database_path", str(test_db_path))
    monkeypatch.setattr("src.control_center.api.archive.load_config", lambda: config)

    with TestClient(app) as client:
        resp = client.get(f"/api/archive/{media_id}/timeline")
        assert resp.status_code == 200
        data = resp.json()
        assert data["media_id"] == media_id
        assert data["original_filename"] == "vacation.jpg"
        assert len(data["events"]) >= 6


def test_models_api_verify_and_benchmark():
    with TestClient(app) as client:
        list_res = client.get("/api/models")
        assert list_res.status_code == 200
        models = list_res.json()
        assert len(models) >= 2
        assert any(m["id"] == "face_detector_yunet" for m in models)

        ver_res = client.post("/api/models/verify")
        assert ver_res.status_code == 200
        vers = ver_res.json()
        assert len(vers) >= 2
        yunet_ver = next(v for v in vers if v["id"] == "face_detector_yunet")
        assert yunet_ver["verified"] is True

        bm_res = client.post("/api/models/benchmark", json={"model_id": "face_detector_yunet"})
        assert bm_res.status_code == 200
        bm = bm_res.json()
        assert bm["id"] == "face_detector_yunet"
        assert bm["latency_ms"] > 0


# ==============================================================================
# PHASE 6.5D INTELLIGENCE TESTS
# ==============================================================================

def test_phase_6_5d_intelligence_suite(tmp_path, monkeypatch):
    from src.config import load_config
    config = load_config()
    test_db_path = tmp_path / "archive_intelligence.sqlite3"

    db = ArchiveDatabase(test_db_path)
    db.apply_migrations(Path("sql"))

    with db.connect() as conn:
        c = conn.execute(
            "INSERT INTO people (person_slug, display_name, active, created_at, updated_at) VALUES ('alice_w', 'Alice Walker', 1, '2026-08-01', '2026-08-01')"
        )
        p_alice = c.lastrowid

        # Item 1: Alice at Yosemite (Nature, 2026-07-15)
        c = conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, has_gps, location_label, discovered_at, updated_at)
            VALUES ('sha_yosemite_1', 'sha_y1', 'y1.jpg', 'yosemite_alice.jpg', 'image', 5000, 0, 'BACKED_UP', '["mountains", "nature", "forest"]', '2026-07-15T14:30:00Z', 1, 'Yosemite National Park', '2026-08-01', '2026-08-01')
            """
        )
        m_y1 = c.lastrowid

        # Item 2: Alice at Yosemite 20 mins later (Similar image)
        c = conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, has_gps, location_label, discovered_at, updated_at)
            VALUES ('sha_yosemite_2', 'sha_y2', 'y2.jpg', 'yosemite_alice_2.jpg', 'image', 5200, 0, 'BACKED_UP', '["mountains", "nature", "hiking"]', '2026-07-15T14:50:00Z', 1, 'Yosemite National Park', '2026-08-01', '2026-08-01')
            """
        )
        m_y2 = c.lastrowid

        # Item 3: Tax Receipt document from 2025
        c = conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, discovered_at, updated_at)
            VALUES ('sha_doc', 'sha_doc', 'tax.png', 'tax_receipt_2025.png', 'image', 1500, 0, 'BACKED_UP', '["receipt", "invoice", "document"]', '2025-04-10T10:00:00Z', '2026-08-01', '2026-08-01')
            """
        )
        m_doc = c.lastrowid

        # Item 4: Video clip from 2026
        conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, discovered_at, updated_at)
            VALUES ('sha_vid', 'sha_vid', 'clip.mp4', 'beach_clip.mp4', 'video', 25000000, 0, 'BACKED_UP', '["beach", "ocean"]', '2026-08-05T12:00:00Z', '2026-08-05', '2026-08-05')
            """
        )

        # Link Alice to m_y1 and m_y2
        for mid in (m_y1, m_y2):
            c_att = conn.execute(
                """
                INSERT INTO face_analysis_attempts (media_id, analysis_key, analysis_version, model_identity, reference_set_hash, started_at, finished_at, outcome, detected_face_count, accepted_match_count, unknown_face_count)
                VALUES (?, 'k', 1, 'm', 'h', '2026-08-01', '2026-08-01', 'SUCCESS', 1, 1, 0)
                """,
                (mid,)
            )
            att_id = c_att.lastrowid
            conn.execute(
                """
                INSERT INTO media_faces (media_id, attempt_id, face_index, detector_confidence, best_person_id, best_score, decision, analyzed_at)
                VALUES (?, ?, 0, 0.95, ?, 0.88, 'KNOWN_MATCH', '2026-08-01')
                """,
                (mid, att_id, p_alice)
            )

        conn.commit()

    monkeypatch.setattr(config.app, "database_path", str(test_db_path))
    monkeypatch.setattr("src.control_center.api.archive.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.services.intelligence_service.load_config", lambda: config)

    with TestClient(app) as client:
        # 1. Test Similar Media: Find items similar to m_y1 -> should return m_y2 as top match
        sim_res = client.get(f"/api/archive/{m_y1}/similar")
        assert sim_res.status_code == 200
        sim_data = sim_res.json()
        assert sim_data["target_media_id"] == m_y1
        assert len(sim_data["similar_items"]) >= 1
        top_match = sim_data["similar_items"][0]
        assert top_match["media_id"] == m_y2
        assert top_match["similarity_score"] >= 70
        assert any("Shared people" in r for r in top_match["reasons"])

        # 2. Test Natural Language Assistant ("Ask Archive")
        # Query: "Show photos of Alice in Yosemite"
        asst_res1 = client.post("/api/archive/assistant", json={"query": "Show photos of Alice"})
        assert asst_res1.status_code == 200
        data1 = asst_res1.json()
        assert data1["total_results"] == 2
        assert "Alice Walker" in data1["explanation"]

        # Query: "Find tax receipts and documents from 2025"
        asst_res2 = client.post("/api/archive/assistant", json={"query": "Find tax receipts from 2025"})
        assert asst_res2.status_code == 200
        data2 = asst_res2.json()
        assert data2["total_results"] == 1
        assert data2["results"][0]["original_filename"] == "tax_receipt_2025.png"

        # Query: "Show video memories"
        asst_res3 = client.post("/api/archive/assistant", json={"query": "Show all video clips"})
        assert asst_res3.status_code == 200
        data3 = asst_res3.json()
        assert data3["total_results"] == 1
        assert data3["results"][0]["media_type"] == "video"

        # 3. Test Smart Collections
        col_res = client.get("/api/archive/collections")
        assert col_res.status_code == 200
        cols = col_res.json()
        assert len(cols) >= 3
        cat_set = {c["category"] for c in cols}
        assert "people" in cat_set
        assert "documents" in cat_set
        assert "videos" in cat_set

        # Test getting collection items
        alice_col = next(c for c in cols if c["category"] == "people")
        col_items_res = client.get(f"/api/archive/collections/{alice_col['id']}")
        assert col_items_res.status_code == 200
        assert len(col_items_res.json()) == 2

        # 4. Test Archive Analytics
        ana_res = client.get("/api/archive/analytics")
        assert ana_res.status_code == 200
        ana = ana_res.json()
        assert ana["summary"]["total_media"] == 4
        assert ana["summary"]["images_count"] == 3
        assert ana["summary"]["videos_count"] == 1
        assert len(ana["top_people"]) == 1
        assert ana["top_people"][0]["name"] == "Alice Walker"
        assert len(ana["scene_distribution"]) >= 3


# ==============================================================================
# PHASE 6.5E MEMORY ENGINE TESTS
# ==============================================================================

def test_phase_6_5e_memory_engine_suite(tmp_path, monkeypatch):
    from src.config import load_config
    config = load_config()
    test_db_path = tmp_path / "archive_memory_engine.sqlite3"

    db = ArchiveDatabase(test_db_path)
    db.apply_migrations(Path("sql"))

    with db.connect() as conn:
        c1 = conn.execute("INSERT INTO people (person_slug, display_name, active, created_at, updated_at) VALUES ('alice', 'Alice Walker', 1, '2026-08-01', '2026-08-01')")
        p_alice = c1.lastrowid
        c2 = conn.execute("INSERT INTO people (person_slug, display_name, active, created_at, updated_at) VALUES ('bob', 'Bob Smith', 1, '2026-08-01', '2026-08-01')")
        p_bob = c2.lastrowid

        # Media 1: Yosemite Day 1 with Alice & Bob
        c = conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, has_gps, location_label, discovered_at, updated_at)
            VALUES ('sha_m1', 'sha_m1', 'yosemite_1.jpg', 'yosemite_1.jpg', 'image', 1200000, 0, 'BACKED_UP', '["mountains", "nature", "hiking"]', '2026-06-12T10:00:00Z', 1, 'Yosemite National Park', '2026-06-12', '2026-06-12')
            """
        )
        m1 = c.lastrowid

        # Media 2: Yosemite Day 2 with Alice & Bob
        c = conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, has_gps, location_label, discovered_at, updated_at)
            VALUES ('sha_m2', 'sha_m2', 'yosemite_2.jpg', 'yosemite_2.jpg', 'image', 1400000, 0, 'BACKED_UP', '["mountains", "waterfall"]', '2026-06-13T15:00:00Z', 1, 'Yosemite National Park', '2026-06-13', '2026-06-13')
            """
        )
        m2 = c.lastrowid

        # Media 3: Austin Downtown with Bob
        c = conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, has_gps, location_label, discovered_at, updated_at)
            VALUES ('sha_m3', 'sha_m3', 'austin.jpg', 'austin_party.jpg', 'image', 800000, 0, 'BACKED_UP', '["urban", "party", "food"]', '2026-07-20T20:00:00Z', 1, 'Austin Downtown', '2026-07-20', '2026-07-20')
            """
        )
        m3 = c.lastrowid

        # Link faces
        for mid in (m1, m2):
            c_att = conn.execute("INSERT INTO face_analysis_attempts (media_id, analysis_key, analysis_version, model_identity, reference_set_hash, started_at, finished_at, outcome, detected_face_count, accepted_match_count, unknown_face_count) VALUES (?, 'k', 1, 'm', 'h', '2026-06-12', '2026-06-12', 'SUCCESS', 2, 2, 0)", (mid,))
            att_id = c_att.lastrowid
            conn.execute("INSERT INTO media_faces (media_id, attempt_id, face_index, detector_confidence, best_person_id, best_score, decision, analyzed_at) VALUES (?, ?, 0, 0.95, ?, 0.88, 'KNOWN_MATCH', '2026-06-12')", (mid, att_id, p_alice))
            conn.execute("INSERT INTO media_faces (media_id, attempt_id, face_index, detector_confidence, best_person_id, best_score, decision, analyzed_at) VALUES (?, ?, 1, 0.94, ?, 0.86, 'KNOWN_MATCH', '2026-06-12')", (mid, att_id, p_bob))

        c_att3 = conn.execute("INSERT INTO face_analysis_attempts (media_id, analysis_key, analysis_version, model_identity, reference_set_hash, started_at, finished_at, outcome, detected_face_count, accepted_match_count, unknown_face_count) VALUES (?, 'k', 1, 'm', 'h', '2026-07-20', '2026-07-20', 'SUCCESS', 1, 1, 0)", (m3,))
        att_id3 = c_att3.lastrowid
        conn.execute("INSERT INTO media_faces (media_id, attempt_id, face_index, detector_confidence, best_person_id, best_score, decision, analyzed_at) VALUES (?, ?, 0, 0.93, ?, 0.85, 'KNOWN_MATCH', '2026-07-20')", (m3, att_id3, p_bob))

        conn.commit()

    monkeypatch.setattr(config.app, "database_path", str(test_db_path))
    monkeypatch.setattr("src.control_center.api.archive.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.services.memory_service.load_config", lambda: config)

    with TestClient(app) as client:
        # 1. Event Detection & Narrative Generation
        mems_res = client.get("/api/archive/memories")
        assert mems_res.status_code == 200
        events = mems_res.json()
        assert len(events) >= 2
        # Yosemite cluster should combine m1 and m2
        yosemite_ev = next(e for e in events if "Yosemite" in e["title"])
        assert yosemite_ev["media_count"] == 2
        assert "Alice Walker" in yosemite_ev["participants"]
        assert "Bob Smith" in yosemite_ev["participants"]
        assert len(yosemite_ev["narrative"]) > 20

        # 2. Curated Highlights
        hl_res = client.get("/api/archive/highlights?person=Alice")
        assert hl_res.status_code == 200
        highlights = hl_res.json()
        assert len(highlights) == 2
        assert highlights[0]["highlight_score"] >= 70

        # 3. Conversational Memory Chat
        # Query: "What did I do in 2026?"
        chat1 = client.post("/api/archive/chat", json={"prompt": "What did I do in 2026?"})
        assert chat1.status_code == 200
        c_data1 = chat1.json()
        assert "2026" in c_data1["answer"]
        assert len(c_data1["relevant_media"]) >= 1

        # Query: "When was the last time I saw Alice?"
        chat2 = client.post("/api/archive/chat", json={"prompt": "When was the last time I saw Alice?"})
        assert chat2.status_code == 200
        c_data2 = chat2.json()
        assert "Alice Walker" in c_data2["answer"]
        assert "2026-06-13" in c_data2["answer"]

        # 4. Archive Quality Metrics
        q_res = client.get("/api/archive/quality")
        assert q_res.status_code == 200
        q_data = q_res.json()
        assert q_data["overall_quality_score"] >= 90
        assert q_data["metadata_completeness_pct"] == 100.0
        assert q_data["scene_coverage_pct"] == 100.0

        # 5. People Relationships Co-occurrence Graph
        rel_res = client.get("/api/archive/relationships")
        assert rel_res.status_code == 200
        rel_data = rel_res.json()
        assert len(rel_data["nodes"]) == 2
        assert len(rel_data["links"]) == 1
        assert rel_data["links"][0]["weight"] == 2

