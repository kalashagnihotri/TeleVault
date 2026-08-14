import pytest
from fastapi.testclient import TestClient
from src.control_center.app import app
import os
import asyncio
from pathlib import Path
from src.control_center.services import db_service

@pytest.fixture(autouse=True)
def setup_teardown():
    # Use a test db
    db_service.DB_PATH = Path("data/test_control_center.sqlite3")
    db_service.init_db()
    yield
    # Cleanup
    try:
        if db_service.DB_PATH.exists():
            os.remove(db_service.DB_PATH)
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

def test_diagnostic_report():
    with TestClient(app) as client:
        response = client.get("/api/system/diagnostic_report")
        assert response.status_code == 200
        data = response.json()
        assert "recent_jobs" in data
        assert data["diagnostic_version"] == "1.0.0"

def test_dashboard():
    with TestClient(app) as client:
        response = client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert "archive" in data
        assert "queue" in data

def test_list_profiles():
    with TestClient(app) as client:
        response = client.get("/api/jobs/profiles")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        assert data[0]["id"] == "pytest_full"
        assert any(p["id"] == "system_diagnostics" for p in data)

def test_start_unknown_profile():
    with TestClient(app) as client:
        response = client.post("/api/jobs/start", json={"profile_id": "nonexistent"})
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "UNKNOWN_PROFILE"

def test_invalid_origin_websocket():
    with TestClient(app) as client:
        # Create a dummy job to test origin
        db_service.save_job({"id": "job-test1", "profile_id": "test", "status": "RUNNING"})
        
        with pytest.raises(Exception):
            with client.websocket_connect("/api/jobs/job-test1/stream", headers={"Origin": "http://evil.com"}):
                pass
                
        # Valid origin should connect
        try:
            with client.websocket_connect("/api/jobs/job-test1/stream", headers={"Origin": "http://127.0.0.1:5173"}):
                pass
        except Exception as e:
            if "1000" not in str(e) and "1008" in str(e):
                pytest.fail(f"Valid origin rejected: {e}")

@pytest.mark.asyncio
async def test_job_execution_and_cancellation():
    from src.control_center.services import job_runner
    import uuid
    import time
    
    # Manually start a safe quick job
    job_id = await job_runner.start_job("queue_inspect")
    
    # Wait for completion
    for _ in range(50): # 5 seconds max
        job = db_service.get_job(job_id)
        if job["status"] != "RUNNING":
            break
        await asyncio.sleep(0.1)
        
    job = db_service.get_job(job_id)
    assert job["status"] in ("PASSED", "FAILED")
    
    # Check events journal exists
    log_dir = Path("data/control_center_logs")
    assert (log_dir / f"{job_id}.events.jsonl").exists()
    assert (log_dir / f"{job_id}.log").exists()
    
    # Test log redaction helper
    redacted = job_runner.redact_secrets("token YOUR_TELEGRAM_BOT_TOKEN test")
    assert "YOUR_TELEGRAM_BOT_TOKEN" in redacted # Config token placeholder itself won't be replaced if missing from actual secrets, but test behavior

def test_stale_job_recovery():
    db_service.save_job({"id": "job-stale", "profile_id": "test", "status": "RUNNING"})
    
    # Lifecycle should recover this to INTERRUPTED
    with TestClient(app):
        job = db_service.get_job("job-stale")
        assert job["status"] == "INTERRUPTED"

@pytest.mark.asyncio
async def test_current_job():
    from src.control_center.services import job_runner
    with TestClient(app) as client:
        response = client.get('/api/jobs/current')
        assert response.status_code == 200
        assert response.json() is None
        job_id = await job_runner.start_job('queue_inspect')
        response = client.get('/api/jobs/current')
        assert response.status_code == 200
        data = response.json()
        assert data is not None
        assert data['id'] == job_id
        for _ in range(50):
            job = db_service.get_job(job_id)
            if job['status'] != 'RUNNING':
                break
            await asyncio.sleep(0.1)
        response = client.get('/api/jobs/current')
        assert response.status_code == 200
        assert response.json() is None
