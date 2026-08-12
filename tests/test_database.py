import threading
import sqlite3
import pytest
from pathlib import Path
from src.database import ArchiveDatabase

def test_duplicate_race(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    db = ArchiveDatabase(db_path)
    
    db.apply_migrations(Path("sql"))
    hash_val = "1234567890abcdef"
    results = []
    
    def worker():
        try:
            res = db.reserve_media(
                sha256=hash_val,
                short_hash="12345678",
                original_path="/dummy/path.jpg",
                original_filename="path.jpg",
                media_type="image",
                size_bytes=100,
                modified_ns=1000,
                state="RESERVED",
                timestamp="2026-01-01T00:00:00"
            )
            results.append(res)
        except Exception as e:
            results.append(e)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Only one thread should have received a non-None media_id (the successful insert)
    # The others should have received None (due to DO NOTHING on conflict)
    # Filter out exceptions if any
    valid_results = [r for r in results if not isinstance(r, Exception)]
    successful_inserts = [r for r in valid_results if r is not None]
    
    assert len(successful_inserts) == 1, "Only one worker should successfully reserve the hash"
    assert len(valid_results) == 10, "All workers should complete without DB lock errors"

def test_face_attempt_counts(tmp_path: Path):
    db_path = tmp_path / "test.sqlite3"
    db = ArchiveDatabase(db_path)
    db.apply_migrations(Path("sql"))
    
    media_id = db.reserve_media(
        sha256="1234567890abcdef",
        short_hash="12345678",
        original_path="dummy.jpg",
        original_filename="dummy.jpg",
        media_type="image",
        size_bytes=100,
        modified_ns=1000,
        state="RESERVED",
        timestamp="2026-01-01T00:00:00"
    )
    
    # 1. One IGNORED_TINY result
    att_1 = db.start_face_analysis_attempt(media_id, "TEST", 3, "model", "ref", None)
    db.record_face_analysis_success(media_id, att_1, [{"face_index": 0, "decision": "IGNORED_TINY"}])
    
    with db.transaction() as conn:
        row = conn.execute("SELECT detected_face_count, accepted_match_count, unknown_face_count FROM face_analysis_attempts WHERE attempt_id = ?", (att_1,)).fetchone()
        assert row["detected_face_count"] == 1
        assert row["accepted_match_count"] == 0
        assert row["unknown_face_count"] == 0
        
    # 2. One UNKNOWN_LOW_SCORE result
    att_2 = db.start_face_analysis_attempt(media_id, "TEST", 4, "model", "ref", None)
    db.record_face_analysis_success(media_id, att_2, [{"face_index": 0, "decision": "UNKNOWN_LOW_SCORE"}])
    
    with db.transaction() as conn:
        row = conn.execute("SELECT detected_face_count, accepted_match_count, unknown_face_count FROM face_analysis_attempts WHERE attempt_id = ?", (att_2,)).fetchone()
        assert row["detected_face_count"] == 1
        assert row["accepted_match_count"] == 0
        assert row["unknown_face_count"] == 1
        
    # 3. Mixed known, unknown and tiny detections

    with db.transaction() as conn:
        conn.execute("INSERT INTO people (person_id, person_slug, display_name, active, created_at, updated_at) VALUES (1, 'person_1', 'Person 1', 1, 'now', 'now')")
        conn.execute("INSERT INTO people (person_id, person_slug, display_name, active, created_at, updated_at) VALUES (2, 'person_2', 'Person 2', 1, 'now', 'now')")
        
    att_3 = db.start_face_analysis_attempt(media_id, "TEST", 5, "model", "ref", None)

    db.record_face_analysis_success(media_id, att_3, [
        {"face_index": 0, "decision": "KNOWN_MATCH", "best_person_id": 1},
        {"face_index": 1, "decision": "KNOWN_MATCH", "best_person_id": 2},
        {"face_index": 2, "decision": "UNKNOWN_AMBIGUOUS"},
        {"face_index": 3, "decision": "UNKNOWN_LOW_SCORE"},
        {"face_index": 4, "decision": "UNKNOWN_UNCALIBRATED"},
        {"face_index": 5, "decision": "IGNORED_TINY"},
        {"face_index": 6, "decision": "IGNORED_TINY"}
    ])
    
    with db.transaction() as conn:
        row = conn.execute("SELECT detected_face_count, accepted_match_count, unknown_face_count FROM face_analysis_attempts WHERE attempt_id = ?", (att_3,)).fetchone()
        assert row["detected_face_count"] == 7
        assert row["accepted_match_count"] == 2
        assert row["unknown_face_count"] == 3
def test_get_media_people_names(tmp_path: Path):
    db_path = tmp_path / "test.sqlite3"
    db = ArchiveDatabase(db_path)
    db.apply_migrations(Path("sql"))
    
    media_id = db.reserve_media(
        sha256="1234567890abcdef", short_hash="1234", original_path="d.jpg", original_filename="d.jpg",
        media_type="image", size_bytes=100, modified_ns=1000, state="RESERVED", timestamp="2026-01-01T00:00:00"
    )

    with db.transaction() as conn:
        conn.execute("INSERT INTO people (person_id, person_slug, display_name, active, created_at, updated_at) VALUES (1, 'p_1', 'Person A', 1, 'now', 'now')")
        conn.execute("INSERT INTO people (person_id, person_slug, display_name, active, created_at, updated_at) VALUES (2, 'p_2', 'Person B', 1, 'now', 'now')")
        conn.execute("INSERT INTO people (person_id, person_slug, display_name, active, created_at, updated_at) VALUES (3, 'p_3', 'Person C', 1, 'now', 'now')")
        
    # v4 attempt (historical)
    att_v4 = db.start_face_analysis_attempt(media_id, "TEST", 4, "model", "ref", None)
    db.record_face_analysis_success(media_id, att_v4, [
        {"face_index": 0, "decision": "KNOWN_MATCH", "best_person_id": 1, "quality_json": None},
        {"face_index": 1, "decision": "KNOWN_MATCH", "best_person_id": 2, "quality_json": None},
    ])

    # Should return historical names since it's the only one
    assert db.get_media_people_names(media_id) == ["Person A", "Person B"]

    # v5 attempt (current)
    att_v5 = db.start_face_analysis_attempt(media_id, "TEST", 5, "model", "ref", None)
    db.record_face_analysis_success(media_id, att_v5, [
        {"face_index": 0, "decision": "KNOWN_MATCH", "best_person_id": 2, "quality_json": None},
        {"face_index": 1, "decision": "UNKNOWN_LOW_RES", "best_person_id": 3, "quality_json": None},
        {"face_index": 2, "decision": "KNOWN_MATCH", "best_person_id": 2, "quality_json": None} # multiple faces to same person
    ])

    # Should return ONLY Person B (from v5). 
    # Person A is from v4 (historical). 
    # Person C is UNKNOWN (should not be returned).
    # Person B appears twice in v5 but should only be returned once.
    names = db.get_media_people_names(media_id)
    assert names == ["Person B"]
    
    # Empty attempt
    att_v6 = db.start_face_analysis_attempt(media_id, "TEST", 6, "model", "ref", None)
    db.record_face_analysis_success(media_id, att_v6, [])
    assert db.get_media_people_names(media_id) == []

def test_get_pending_face_analysis_cleanup(tmp_path: Path):
    db_path = tmp_path / "test.sqlite3"
    db = ArchiveDatabase(db_path)
    db.apply_migrations(Path("sql"))
    
    # Insert multiple media to test get_pending_face_analysis
    with db.transaction() as conn:
        def insert_media(mid, media_type, face_state, state, cleanup_state):
            conn.execute(
                "INSERT INTO media (id, sha256, short_hash, original_path, original_filename, size_bytes, media_type, state, cleanup_state, face_state, modified_ns, discovered_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 100, ?, ?, ?, ?, 0, '2026-01-01', '2026-01-01')",
                (mid, f"h{mid}", f"s{mid}", f"f{mid}", f"f{mid}", media_type, state, cleanup_state, face_state)
            )
        
        insert_media(1, 'image', 'PENDING', 'ACTIVE', 'PENDING')
        insert_media(2, 'image', 'FAILED', 'ACTIVE', 'PENDING')
        insert_media(3, 'image', 'ANALYZING', 'ACTIVE', 'PENDING') # Stale (old date)
        insert_media(4, 'image', 'PENDING', 'ACTIVE', 'CLEANED') # Excluded: CLEANED
        insert_media(5, 'image', 'PENDING', 'ACTIVE', 'COMPLETED') # Excluded: COMPLETED
        insert_media(6, 'video', 'PENDING', 'ACTIVE', 'PENDING') # Excluded: video
        insert_media(7, 'image', 'SUCCESS', 'ACTIVE', 'PENDING') # Excluded: face_state SUCCESS
        
    candidates = db.get_pending_face_analysis(limit=100, stale_minutes=0)
    ids = [c["id"] for c in candidates]
    
    # 1, 2, 3 should be returned.
    assert 1 in ids
    assert 2 in ids
    assert 3 in ids
    
    # 4, 5, 6, 7 should not be returned.
    assert 4 not in ids
    assert 5 not in ids
    assert 6 not in ids
    assert 7 not in ids
def test_update_route_before_upload(tmp_path: Path):
    db_path = tmp_path / "test.sqlite3"
    db = ArchiveDatabase(db_path)
    db.apply_migrations(Path("sql"))

    def reserve(mid: int, state="READY_TO_UPLOAD"):
        return db.reserve_media(
            sha256=f"hash{mid}", short_hash=f"hash{mid}", original_path=f"path{mid}", original_filename=f"path{mid}",
            media_type="image", size_bytes=100, modified_ns=1000, state=state, timestamp="2026-01-01"
        )
        
    # 1. READY_TO_UPLOAD with zero upload evidence -> success
    mid1 = reserve(1)
    db.update_metadata(mid1, None, 1, "Location", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01")
    assert db.update_route_before_upload(mid1, "people") is True
    
    # 2. BACKED_UP -> rejected
    mid2 = reserve(2, "BACKED_UP")
    db.update_metadata(mid2, None, 1, "Location", "[]", "[]", "everyday", "BACKED_UP", "2026-01-01")
    assert db.update_route_before_upload(mid2, "people") is False
    
    # 3. PREVIEW_CONFIRMED -> rejected
    mid3 = reserve(3, "PREVIEW_CONFIRMED")
    db.update_metadata(mid3, None, 1, "Location", "[]", "[]", "everyday", "PREVIEW_CONFIRMED", "2026-01-01")
    assert db.update_route_before_upload(mid3, "people") is False

    # 4. Upload attempt exists -> rejected
    mid4 = reserve(4)
    db.update_metadata(mid4, None, 1, "Location", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01")
    db.start_upload_attempt(mid4, "preview", "PREVIEW_UPLOADING", "f", 100, "1", "1", "2026-01-01")
    with db.connect() as c: c.execute("UPDATE media SET state='READY_TO_UPLOAD' WHERE id=?", (mid4,))
    assert db.update_route_before_upload(mid4, "people") is False

    # 5. preview_message_id exists -> rejected
    mid5 = reserve(5)
    db.update_metadata(mid5, None, 1, "Location", "[]", "[]", "everyday", "READY_TO_UPLOAD", "2026-01-01")
    with db.connect() as c: c.execute("UPDATE telegram_archive SET preview_message_id='m1' WHERE media_id=?", (mid5,))
    assert db.update_route_before_upload(mid5, "people") is False

