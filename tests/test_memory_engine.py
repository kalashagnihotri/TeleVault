import pytest
from fastapi.testclient import TestClient
from src.control_center.app import app
import os
import sqlite3
from pathlib import Path
from src.database import ArchiveDatabase
from src.control_center.services import memory_service, db_service


@pytest.fixture(autouse=True)
def setup_teardown(tmp_path):
    test_db = tmp_path / "test_control_center.sqlite3"
    db_service.DB_PATH = test_db
    db_service.init_db()
    yield
    try:
        if test_db.exists():
            os.remove(test_db)
    except PermissionError:
        pass


def test_same_location_different_dates_separation(tmp_path, monkeypatch):
    """Same location (Austin) across distant dates (Jan vs July) must create two distinct memories."""
    from src.config import load_config
    config = load_config()
    test_db_path = tmp_path / "archive_sep.sqlite3"

    db = ArchiveDatabase(test_db_path)
    db.apply_migrations(Path("sql"))

    with db.connect() as conn:
        # Event A: Austin in January 2026
        conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, has_gps, location_label, discovered_at, updated_at)
            VALUES ('sha_jan_1', 'sha_j1', 'jan1.jpg', 'austin_jan1.jpg', 'image', 500000, 0, 'BACKED_UP', '["office", "work"]', '2026-01-15T10:00:00Z', 1, 'Austin', '2026-01-15', '2026-01-15'),
                   ('sha_jan_2', 'sha_j2', 'jan2.jpg', 'austin_jan2.jpg', 'image', 520000, 0, 'BACKED_UP', '["office", "work"]', '2026-01-16T11:00:00Z', 1, 'Austin', '2026-01-16', '2026-01-16')
            """
        )
        # Event B: Austin in July 2026 (6 months later)
        conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, has_gps, location_label, discovered_at, updated_at)
            VALUES ('sha_jul_1', 'sha_jl1', 'jul1.jpg', 'austin_jul1.jpg', 'image', 600000, 0, 'BACKED_UP', '["bbq", "food", "party"]', '2026-07-20T18:00:00Z', 1, 'Austin', '2026-07-20', '2026-07-20')
            """
        )
        conn.commit()

    monkeypatch.setattr(config.app, "database_path", str(test_db_path))
    monkeypatch.setattr("src.control_center.services.memory_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.api.archive.load_config", lambda: config)

    with TestClient(app) as client:
        res = client.get("/api/archive/memories")
        assert res.status_code == 200
        events = res.json()
        # Must produce at least 2 distinct events despite same location
        assert len(events) == 2
        dates = [e["start_date"][:7] for e in events]
        assert "2026-01" in dates
        assert "2026-07" in dates


def test_trip_detection_and_smart_naming(tmp_path, monkeypatch):
    """Outdoor trip with Alice at Yosemite should produce smart title 'Alice's Yosemite Trip'."""
    from src.config import load_config
    config = load_config()
    test_db_path = tmp_path / "archive_trip.sqlite3"

    db = ArchiveDatabase(test_db_path)
    db.apply_migrations(Path("sql"))

    with db.connect() as conn:
        c = conn.execute("INSERT INTO people (person_slug, display_name, active, created_at, updated_at) VALUES ('alice', 'Alice Walker', 1, '2026-08-01', '2026-08-01')")
        p_alice = c.lastrowid

        c1 = conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, has_gps, location_label, discovered_at, updated_at)
            VALUES ('sha_yos_1', 'sha_y1', 'y1.jpg', 'yosemite_hike.jpg', 'image', 1200000, 0, 'BACKED_UP', '["mountains", "hiking", "nature"]', '2026-06-12T09:00:00Z', 1, 'Yosemite', '2026-06-12', '2026-06-12')
            """
        )
        m1 = c1.lastrowid

        c2 = conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, has_gps, location_label, discovered_at, updated_at)
            VALUES ('sha_yos_2', 'sha_y2', 'y2.jpg', 'yosemite_falls.jpg', 'image', 1400000, 0, 'BACKED_UP', '["waterfall", "nature"]', '2026-06-13T14:00:00Z', 1, 'Yosemite', '2026-06-13', '2026-06-13')
            """
        )
        m2 = c2.lastrowid

        for mid in (m1, m2):
            c_att = conn.execute("INSERT INTO face_analysis_attempts (media_id, analysis_key, analysis_version, model_identity, reference_set_hash, started_at, finished_at, outcome, detected_face_count, accepted_match_count, unknown_face_count) VALUES (?, 'k', 1, 'm', 'h', '2026-06-12', '2026-06-12', 'SUCCESS', 1, 1, 0)", (mid,))
            att_id = c_att.lastrowid
            conn.execute("INSERT INTO media_faces (media_id, attempt_id, face_index, detector_confidence, best_person_id, best_score, decision, analyzed_at) VALUES (?, ?, 0, 0.95, ?, 0.88, 'KNOWN_MATCH', '2026-06-12')", (mid, att_id, p_alice))

        conn.commit()

    monkeypatch.setattr(config.app, "database_path", str(test_db_path))
    monkeypatch.setattr("src.control_center.services.memory_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.api.archive.load_config", lambda: config)

    with TestClient(app) as client:
        res = client.get("/api/archive/memories")
        assert res.status_code == 200
        events = res.json()
        assert len(events) == 1
        ev = events[0]
        assert ev["category"] == "trip"
        assert "Alice Walker" in ev["title"]
        assert "Yosemite" in ev["title"]
        assert ev["event_confidence"] >= 80
        assert len(ev["confidence_reasons"]) >= 2


def test_document_and_screenshot_session_detection(tmp_path, monkeypatch):
    """Screenshots and documents should be detected under work_session and documents categories."""
    from src.config import load_config
    config = load_config()
    test_db_path = tmp_path / "archive_sessions.sqlite3"

    db = ArchiveDatabase(test_db_path)
    db.apply_migrations(Path("sql"))

    with db.connect() as conn:
        # Technical screenshots
        conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, has_gps, location_label, discovered_at, updated_at)
            VALUES ('sha_shot_1', 'sha_s1', 'shot1.png', 'debug_error.png', 'image', 300000, 0, 'BACKED_UP', '["screenshot", "ui", "code"]', '2026-08-10T14:00:00Z', 0, 'Misc', '2026-08-10', '2026-08-10'),
                   ('sha_shot_2', 'sha_s2', 'shot2.png', 'trace_stack.png', 'image', 320000, 0, 'BACKED_UP', '["screenshot", "window"]', '2026-08-10T15:00:00Z', 0, 'Misc', '2026-08-10', '2026-08-10')
            """
        )
        # Invoices and receipts
        conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, has_gps, location_label, discovered_at, updated_at)
            VALUES ('sha_doc_1', 'sha_d1', 'tax.pdf', 'tax_receipt.png', 'image', 450000, 0, 'BACKED_UP', '["receipt", "invoice", "document"]', '2026-04-15T10:00:00Z', 0, 'Misc', '2026-04-15', '2026-04-15')
            """
        )
        conn.commit()

    monkeypatch.setattr(config.app, "database_path", str(test_db_path))
    monkeypatch.setattr("src.control_center.services.memory_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.api.archive.load_config", lambda: config)

    with TestClient(app) as client:
        res = client.get("/api/archive/memories")
        assert res.status_code == 200
        events = res.json()
        assert len(events) == 2
        categories = {e["category"] for e in events}
        assert "work_session" in categories
        assert "documents" in categories


def test_smart_highlight_similarity_suppression(tmp_path, monkeypatch):
    """10 similar photos from same event should be diversity-suppressed in highlights."""
    from src.config import load_config
    config = load_config()
    test_db_path = tmp_path / "archive_hl_suppress.sqlite3"

    db = ArchiveDatabase(test_db_path)
    db.apply_migrations(Path("sql"))

    with db.connect() as conn:
        # 5 burst shots from same day at same location
        for i in range(5):
            conn.execute(
                """
                INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, has_gps, location_label, discovered_at, updated_at)
                VALUES (?, ?, ?, ?, 'image', ?, 0, 'BACKED_UP', '["beach", "nature"]', '2026-07-04T12:00:00Z', 1, 'Miami Beach', '2026-07-04', '2026-07-04')
                """,
                (f"sha_miami_{i}", f"sha_m{i}", f"m_{i}.jpg", f"miami_beach_burst_{i}.jpg", 800000 + i * 1000)
            )

        # 1 photo from mountain trip
        conn.execute(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, has_gps, location_label, discovered_at, updated_at)
            VALUES ('sha_mtn', 'sha_mtn', 'mtn.jpg', 'aspen_mountains.jpg', 'image', 1500000, 0, 'BACKED_UP', '["mountains", "forest"]', '2026-08-15T10:00:00Z', 1, 'Aspen', '2026-08-15', '2026-08-15')
            """
        )
        conn.commit()

    monkeypatch.setattr(config.app, "database_path", str(test_db_path))
    monkeypatch.setattr("src.control_center.services.memory_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.api.archive.load_config", lambda: config)

    with TestClient(app) as client:
        res = client.get("/api/archive/highlights?limit=4")
        assert res.status_code == 200
        highlights = res.json()
        assert len(highlights) >= 2
        # Aspen photo should be included despite 5 Miami burst photos
        filenames = [h["original_filename"] for h in highlights]
        assert "aspen_mountains.jpg" in filenames
        # Miami photos should not monopolize
        miami_count = sum(1 for f in filenames if "miami" in f)
        assert miami_count <= 2
        assert highlights[0]["highlight_score"] > 0
        assert len(highlights[0]["reasons"]) > 0


def test_archive_assistant_intents_and_comparisons(tmp_path, monkeypatch):
    """Test comparison queries, relationship queries, and temporal interpretation."""
    from src.config import load_config
    config = load_config()
    test_db_path = tmp_path / "archive_asst.sqlite3"

    db = ArchiveDatabase(test_db_path)
    db.apply_migrations(Path("sql"))

    with db.connect() as conn:
        c1 = conn.execute("INSERT INTO people (person_slug, display_name, active, created_at, updated_at) VALUES ('alice', 'Alice Walker', 1, '2026-08-01', '2026-08-01')")
        p1 = c1.lastrowid
        c2 = conn.execute("INSERT INTO people (person_slug, display_name, active, created_at, updated_at) VALUES ('bob', 'Bob Smith', 1, '2026-08-01', '2026-08-01')")
        p2 = c2.lastrowid

        # 2025 item
        conn.execute("INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, discovered_at, updated_at) VALUES ('s25', 's25', 'f25.jpg', 'doc2025.jpg', 'image', 1000, 0, 'BACKED_UP', '[]', '2025-05-01', '2025-05-01', '2025-05-01')")
        # 2026 items with Alice and Bob
        c_m26 = conn.execute("INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, has_gps, location_label, discovered_at, updated_at) VALUES ('s26', 's26', 'f26.jpg', 'party2026.jpg', 'image', 1000, 0, 'BACKED_UP', '[\"party\"]', '2026-07-04', 1, 'Austin', '2026-07-04', '2026-07-04')")
        m26 = c_m26.lastrowid

        c_att = conn.execute("INSERT INTO face_analysis_attempts (media_id, analysis_key, analysis_version, model_identity, reference_set_hash, started_at, finished_at, outcome, detected_face_count, accepted_match_count, unknown_face_count) VALUES (?, 'k', 1, 'm', 'h', '2026-07-04', '2026-07-04', 'SUCCESS', 2, 2, 0)", (m26,))
        att_id = c_att.lastrowid
        conn.execute("INSERT INTO media_faces (media_id, attempt_id, face_index, detector_confidence, best_person_id, best_score, decision, analyzed_at) VALUES (?, ?, 0, 0.95, ?, 0.88, 'KNOWN_MATCH', '2026-07-04')", (m26, att_id, p1))
        conn.execute("INSERT INTO media_faces (media_id, attempt_id, face_index, detector_confidence, best_person_id, best_score, decision, analyzed_at) VALUES (?, ?, 1, 0.94, ?, 0.85, 'KNOWN_MATCH', '2026-07-04')", (m26, att_id, p2))
        conn.commit()

    monkeypatch.setattr(config.app, "database_path", str(test_db_path))
    monkeypatch.setattr("src.control_center.services.memory_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.api.archive.load_config", lambda: config)

    with TestClient(app) as client:
        # Comparison query
        res1 = client.post("/api/archive/chat", json={"prompt": "Compare 2025 and 2026"})
        assert res1.status_code == 200
        d1 = res1.json()
        assert "2025" in d1["answer"] and "2026" in d1["answer"]
        assert d1["interpreted_intent"]["detected_category"] == "year_comparison"

        # People comparison query
        res2 = client.post("/api/archive/chat", json={"prompt": "Compare Alice and Bob"})
        assert res2.status_code == 200
        d2 = res2.json()
        assert "Alice Walker" in d2["answer"] and "Bob Smith" in d2["answer"]
        assert "shared photo" in d2["answer"]

        # Relationship query: who appears most with Bob
        res3 = client.post("/api/archive/chat", json={"prompt": "Who appears most with Bob?"})
        assert res3.status_code == 200
        d3 = res3.json()
        assert "Alice Walker" in d3["answer"]


def test_archive_health_100_point_score_and_profiles(tmp_path, monkeypatch):
    """Test 100-point AI-readiness score calculation and people profiles endpoint."""
    from src.config import load_config
    config = load_config()
    test_db_path = tmp_path / "archive_hl_prof.sqlite3"

    db = ArchiveDatabase(test_db_path)
    db.apply_migrations(Path("sql"))

    with db.connect() as conn:
        c = conn.execute("INSERT INTO people (person_slug, display_name, active, created_at, updated_at) VALUES ('charlie', 'Charlie Brown', 1, '2026-08-01', '2026-08-01')")
        p_c = c.lastrowid
        conn.execute("INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, has_gps, location_label, discovered_at, updated_at) VALUES ('s1', 's1', 'c.jpg', 'charlie.jpg', 'image', 500000, 0, 'BACKED_UP', '[\"portrait\"]', '2026-08-01T10:00:00Z', 1, 'Seattle', '2026-08-01', '2026-08-01')")
        conn.commit()

    monkeypatch.setattr(config.app, "database_path", str(test_db_path))
    monkeypatch.setattr("src.control_center.services.memory_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.api.archive.load_config", lambda: config)

    with TestClient(app) as client:
        # Quality score
        q_res = client.get("/api/archive/quality")
        assert q_res.status_code == 200
        q_data = q_res.json()
        assert 0 <= q_data["overall_quality_score"] <= 100
        assert "score_breakdown" in q_data
        assert "metadata" in q_data["score_breakdown"]
        assert len(q_data["recommendations"]) >= 1

        # People profiles
        prof_res = client.get("/api/archive/people_profiles")
        assert prof_res.status_code == 200
