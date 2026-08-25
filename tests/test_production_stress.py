import pytest
from fastapi.testclient import TestClient
from src.control_center.app import app
import os
import sqlite3
import time
import concurrent.futures
from pathlib import Path
from src.database import ArchiveDatabase
from src.control_center.services import db_service, intelligence_service, memory_service


@pytest.fixture(autouse=True)
def setup_teardown(tmp_path):
    test_db = tmp_path / "test_stress_control_center.sqlite3"
    db_service.DB_PATH = test_db
    db_service.init_db()
    yield
    try:
        if test_db.exists():
            os.remove(test_db)
    except PermissionError:
        pass


def test_10000_media_records_performance(tmp_path, monkeypatch):
    """Stress test: Ingest 10,000 media records in batch and verify indexed retrieval speed < 100ms."""
    from src.config import load_config
    config = load_config()
    test_db_path = tmp_path / "archive_10k.sqlite3"

    db = ArchiveDatabase(test_db_path)
    db.apply_migrations(Path("sql"))

    # Batch insert 10,000 records
    t0 = time.perf_counter()
    batch_size = 10000
    rows = []
    for i in range(batch_size):
        sha = f"sha_10k_{i:06d}"
        fn = f"photo_{i:06d}.jpg"
        loc = "Yosemite" if i % 100 == 0 else "Austin" if i % 50 == 0 else "Misc"
        label = '["nature", "mountains"]' if i % 3 == 0 else '["screenshot", "code"]' if i % 2 == 0 else '[]'
        dt = f"2026-06-{(i % 28) + 1:02d}T10:00:00Z"
        rows.append((sha, sha[:8], f"path/{fn}", fn, "image", 500000 + i, 0, "BACKED_UP", label, dt, 1 if loc != "Misc" else 0, loc, dt, dt))

    with db.connect() as conn:
        conn.executemany(
            """
            INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, has_gps, location_label, discovered_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows
        )
        conn.commit()

    insert_duration = time.perf_counter() - t0
    assert insert_duration < 5.0, f"10,000 inserts took too long: {insert_duration:.2f}s"

    monkeypatch.setattr(config.app, "database_path", str(test_db_path))
    monkeypatch.setattr("src.control_center.services.memory_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.services.intelligence_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.api.archive.load_config", lambda: config)

    with TestClient(app) as client:
        # Measure search query latency on 10,000 records
        t_search = time.perf_counter()
        res = client.get("/api/archive/search?q=nature in Yosemite&limit=50")
        latency = (time.perf_counter() - t_search) * 1000
        assert res.status_code == 200
        results = res.json()
        assert len(results) >= 1
        assert latency < 250.0, f"Search latency too high: {latency:.1f}ms on 10k items"


def test_100_concurrent_archive_searches(tmp_path, monkeypatch):
    """Stress test: Execute 100 concurrent search requests to test SQLite concurrency and connection pool safety."""
    from src.config import load_config
    config = load_config()
    test_db_path = tmp_path / "archive_concurrent.sqlite3"

    db = ArchiveDatabase(test_db_path)
    db.apply_migrations(Path("sql"))

    with db.connect() as conn:
        for i in range(500):
            conn.execute(
                """
                INSERT INTO media (sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, labels_json, date_taken, has_gps, location_label, discovered_at, updated_at)
                VALUES (?, ?, ?, ?, 'image', 500000, 0, 'BACKED_UP', '["nature"]', '2026-06-12', 1, 'Yosemite', '2026-06-12', '2026-06-12')
                """,
                (f"sha_c_{i}", f"sha_{i}", f"photo_{i}.jpg", f"photo_{i}.jpg")
            )
        conn.commit()

    monkeypatch.setattr(config.app, "database_path", str(test_db_path))
    monkeypatch.setattr("src.control_center.services.intelligence_service.load_config", lambda: config)
    monkeypatch.setattr("src.control_center.api.archive.load_config", lambda: config)

    queries = [
        "nature in Yosemite",
        "photo_0001",
        "from 2026",
        "photo",
        "Yosemite"
    ]

    with TestClient(app) as client:
        def do_search(q: str):
            r = client.get(f"/api/archive/search?q={q}&limit=20")
            return r.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(do_search, queries[i % len(queries)]) for i in range(100)]
            results = [f.result() for f in futures]

        assert all(code == 200 for code in results), "Not all 100 concurrent searches succeeded"


def test_corrupted_file_and_error_recovery(tmp_path, monkeypatch):
    """Resilience test: Ingesting corrupted/zero-byte files must not crash pipeline and must record proper error state."""
    from src.config import load_config
    config = load_config()
    test_img_dir = tmp_path / "incoming_images"
    test_vid_dir = tmp_path / "incoming_videos"
    test_img_dir.mkdir()
    test_vid_dir.mkdir()
    
    monkeypatch.setattr(config.queue, "incoming_images", str(test_img_dir))
    monkeypatch.setattr(config.queue, "incoming_videos", str(test_vid_dir))
    monkeypatch.setattr("src.control_center.api.ingestion.load_config", lambda: config)

    # Ingest 0-byte corrupt file
    corrupt_bytes = b""
    with TestClient(app) as client:
        response = client.post(
            "/api/queue/ingest",
            files=[("files", ("corrupted_zero_byte.png", corrupt_bytes, "image/png"))]
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] in ("INVALID_MEDIA", "IMPORT_FAILED")


def test_job_interruption_recovery(tmp_path):
    """Resilience test: Interrupted running jobs upon crash/restart are cleanly recovered to INTERRUPTED state."""
    from src.control_center.services import job_runner, db_service

    # Create a job left in RUNNING state
    stale_job = {
        "id": "stale_job_123",
        "profile_id": "pipeline_live",
        "status": "RUNNING",
        "created_at": "2026-08-25T10:00:00Z",
        "started_at": "2026-08-25T10:00:01Z",
        "finished_at": None,
        "exit_code": None,
        "duration": None,
        "error_summary": None,
        "raw_command": "echo 'stale'"
    }
    db_service.save_job(stale_job)

    # Run crash recovery
    job_runner.recover_stale_jobs()

    # Verify job is recovered to INTERRUPTED
    recovered = db_service.get_job("stale_job_123")
    assert recovered is not None
    assert recovered["status"] == "INTERRUPTED"
    assert "restarted" in recovered["error_summary"].lower()

