"""Comprehensive Unit Test Suite for Phase 6.5I, 6.5J, and Phase 7.

Tests:
- Pipeline Replay Engine
- Model Registry Lineage
- Config Versioning & Diffing
- Priority Worker Queue
- Failure Recovery Center
- Storage Intelligence
- Automated Backup Sandbox Restore
- Conversational AI Archive Chat
- Autobiography Life Story Generation
- Emotion Atmosphere Tagger
- Calendar Integration Linkage
- Location Visited Hierarchy
- Public REST API v1
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
import pytest

from src.control_center.services.pipeline_replay_service import PipelineReplayService
from src.control_center.services.model_registry_service import ModelRegistryService
from src.control_center.services.config_history_service import ConfigHistoryService
from src.control_center.services.priority_queue_service import PriorityQueueService
from src.control_center.services.failure_recovery_service import FailureRecoveryService
from src.control_center.services.storage_intelligence_service import StorageIntelligenceService
from src.control_center.services.automated_backup_verifier import AutomatedBackupVerifier
from src.control_center.services.ai_chat_service import AIChatService
from src.control_center.services.autobiography_service import AutobiographyService
from src.control_center.services.emotion_service import EmotionService
from src.control_center.services.calendar_integration_service import CalendarIntegrationService
from src.control_center.services.location_intelligence_service import LocationIntelligenceService
from src.control_center.services.public_api_service import PublicAPIService

@pytest.fixture
def test_env():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        tmp_p = Path(tmp_dir)
        db_p = tmp_p / "test_archive.sqlite3"
        cfg_p = tmp_p / "config.yaml"
        cfg_p.write_text("app:\n  face_threshold: 0.85\n  log_level: INFO\n", encoding="utf-8")

        # Create schema from migration scripts
        conn = sqlite3.connect(db_p)
        for sql_file in sorted(Path("sql").glob("*.sql")):
            conn.executescript(sql_file.read_text(encoding="utf-8"))

        # Seed sample media and people
        with conn:
            conn.execute(
                """
                INSERT INTO people (person_id, person_slug, display_name, active, created_at, updated_at)
                VALUES (1, 'alice', 'Alice Smith', 1, '2025-01-01', '2026-08-25')
                """
            )
            conn.execute(
                """
                INSERT INTO media 
                (id, sha256, short_hash, original_path, original_filename, media_type, size_bytes, modified_ns, state, face_state, scene_state, labels_json, people_json, date_taken, location_label, discovered_at, updated_at)
                VALUES 
                (1, 'sha_lake', 'sh1', '/lake.jpg', 'lake.jpg', 'image', 50000, 0, 'BACKED_UP', 'ANALYZED', 'ANALYZED', '["Lake", "Nature", "Water"]', '["Alice Smith"]', '2026-08-15', 'Lake Tahoe, CA', '2026-08-25', '2026-08-25'),
                (2, 'sha_rec', 'sh2', '/receipt.jpg', 'receipt.jpg', 'image', 12000, 0, 'BACKED_UP', 'ANALYZED', 'ANALYZED', '["Document", "Receipt"]', '[]', '2026-08-20', 'Austin, TX', '2026-08-25', '2026-08-25'),
                (3, 'sha_vid', 'sh3', '/trip.mp4', 'trip.mp4', 'video', 5000000, 0, 'BACKED_UP', 'ANALYZED', 'ANALYZED', '["Travel", "Trip"]', '["Alice Smith"]', '2026-07-10', 'Yosemite, CA', '2026-08-25', '2026-08-25'),
                (4, 'sha_fail', 'sh4', '/bad.jpg', 'bad.jpg', 'image', 1000, 0, 'FAILED', 'FAILED', 'PENDING', '[]', '[]', '2026-08-01', '', '2026-08-25', '2026-08-25')
                """
            )
            conn.execute(
                """
                INSERT INTO memories (memory_id, title, category, start_date, end_date, total_photos, cover_media_id, is_curated, created_at, updated_at)
                VALUES ('mem_tahoe', 'Lake Tahoe Trip', 'TRIP', '2026-08-15', '2026-08-16', 1, 1, 1, '2026-08-25', '2026-08-25')
                """
            )
        conn.close()

        yield {
            "db_path": db_p,
            "cfg_path": cfg_p,
            "dir": tmp_p,
        }

def test_pipeline_replay_and_model_registry(test_env):
    db_p = test_env["db_path"]
    replay_svc = PipelineReplayService(db_p)
    model_svc = ModelRegistryService(db_p)

    # 1. Test Model Registry
    models = model_svc.list_registered_models()
    assert len(models) >= 5
    model_svc.register_model("Custom Face Model", "v2.0", "FACE_DETECTOR", description="Test detector")
    models_updated = model_svc.list_registered_models()
    assert any(m["model_name"] == "Custom Face Model" for m in models_updated)

    # 2. Test Pipeline Execution Recording & Replay
    h_id = replay_svc.record_stage_execution(1, "FACE_DETECTION", "yunet_2023mar", "cfg_hash_1", {"faces": 1})
    assert h_id > 0

    history = replay_svc.get_media_pipeline_history(1)
    assert len(history) >= 1
    assert history[0]["stage"] == "FACE_DETECTION"

    replay_res = replay_svc.replay_pipeline_for_media(1)
    assert replay_res["stages_replayed"] == 4
    assert "METADATA" in replay_res["results"]
    assert "FACE_DETECTION" in replay_res["results"]

def test_config_history_and_priority_queue(test_env):
    db_p = test_env["db_path"]
    cfg_p = test_env["cfg_path"]
    cfg_svc = ConfigHistoryService(db_p, cfg_p)
    queue_svc = PriorityQueueService(db_p)

    # 1. Test Config Snapshots and Rollback
    v1_list = cfg_svc.list_versions()
    assert len(v1_list) >= 1

    # Record v2 with change
    v2_id = cfg_svc.record_snapshot("app:\n  face_threshold: 0.90\n  log_level: DEBUG\n", changed_by="admin", reason="Tightened threshold")
    diff = cfg_svc.compare_versions(v1_list[0]["id"], v2_id)
    assert diff["lines_changed"] > 0

    # Rollback to v1
    rollback = cfg_svc.rollback_to_version(v1_list[0]["id"])
    assert rollback["success"] is True
    assert "face_threshold: 0.85" in cfg_p.read_text(encoding="utf-8")

    # 2. Test Priority Worker Queue
    j_low = queue_svc.enqueue_job(1, "REPROCESS_SCENE", priority=3)
    j_high = queue_svc.enqueue_job(4, "RETRY_FAILED", priority=1)
    j_mid = queue_svc.enqueue_job(2, "NEW_UPLOAD", priority=2)

    # Fetch next job (must be priority 1)
    next_j = queue_svc.fetch_next_job()
    assert next_j is not None
    assert next_j["job_id"] == j_high
    assert next_j["priority"] == 1

    queue_svc.complete_job(j_high, success=True)
    stats = queue_svc.get_queue_stats()
    assert stats["summary"]["completed"] == 1

def test_failure_recovery_storage_and_backup(test_env):
    db_p = test_env["db_path"]
    rec_svc = FailureRecoveryService(db_p)
    storage_svc = StorageIntelligenceService(db_p)
    backup_svc = AutomatedBackupVerifier(db_p)

    # 1. Test Failure Recovery
    ov = rec_svc.get_failure_overview()
    assert ov["total_failed_items"] == 1
    retry_res = rec_svc.retry_all_failed()
    assert retry_res["reset_count"] == 1

    # 2. Test Storage Intelligence
    stor = storage_svc.get_storage_breakdown()
    assert stor["total_media_count"] == 4
    assert stor["category_distribution"]["videos"]["file_count"] == 1
    assert stor["category_distribution"]["photos"]["file_count"] == 3
    assert len(stor["largest_files"]) == 4

    # 3. Test Automated Backup Sandbox Restore Verification
    b_res = backup_svc.run_automated_restore_verification()
    assert b_res["status"] == "PASSED"
    assert b_res["backup_confidence_score"] == 100.0

def test_personal_ai_and_public_api(test_env):
    db_p = test_env["db_path"]
    chat_svc = AIChatService(db_p)
    autobio_svc = AutobiographyService(db_p)
    mood_svc = EmotionService(db_p)
    cal_svc = CalendarIntegrationService(db_p)
    loc_svc = LocationIntelligenceService(db_p)
    api_svc = PublicAPIService(db_p)

    # 1. AI Chat Query
    chat_res = chat_svc.chat_query("Find pictures from the trip where we went hiking with Alice near the lake")
    assert chat_res["understood_intent"]["is_trip"] is True
    assert chat_res["understood_intent"]["person_name"] == "Alice"
    assert len(chat_res["relevant_assets"]) > 0

    # 2. Autobiography
    book = autobio_svc.generate_annual_autobiography("2026")
    assert book["year"] == "2026"
    assert len(book["chapters"]) > 0

    # 3. Emotion Mood Tags
    mood_res = mood_svc.analyze_media_mood(1)
    assert len(mood_res["suggested_moods"]) > 0

    # 4. Calendar Linkage
    cal_evt = cal_svc.add_calendar_event("Tahoe Summer Vacation", "2026-08-14", "2026-08-16", location="Lake Tahoe")
    assert cal_evt["matched_media_count"] == 1

    # 5. Location Hierarchy
    loc_hier = loc_svc.get_places_visited_hierarchy()
    assert loc_hier["total_places_visited"] >= 2

    # 6. Public REST API v1
    token_obj = api_svc.create_api_token("Test App Token")
    assert api_svc.validate_token(token_obj["raw_token"]) is True
    photos = api_svc.get_public_photos()
    assert len(photos) >= 1
    ppl = api_svc.get_public_people()
    assert len(ppl) == 1
