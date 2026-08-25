"""API Router for Phase 6.5I: Production Reliability.

Endpoints:
- Pipeline Replay Engine (/api/pipeline/history, /api/pipeline/replay)
- Model Version Registry (/api/models/list, /api/models/register)
- Config Versioning (/api/config/history, /api/config/compare, /api/config/rollback)
- Priority Worker Queue (/api/queue/enqueue, /api/queue/next, /api/queue/stats)
- Failure Recovery Center (/api/recovery/overview, /api/recovery/retry_all, /api/recovery/ignore)
- Storage Intelligence (/api/storage/breakdown)
- Automated Backup Verification (/api/backup/automated_verification)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.config import load_config
from src.control_center.services.pipeline_replay_service import PipelineReplayService
from src.control_center.services.model_registry_service import ModelRegistryService
from src.control_center.services.config_history_service import ConfigHistoryService
from src.control_center.services.priority_queue_service import PriorityQueueService
from src.control_center.services.failure_recovery_service import FailureRecoveryService
from src.control_center.services.storage_intelligence_service import StorageIntelligenceService
from src.control_center.services.automated_backup_verifier import AutomatedBackupVerifier

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Production Reliability"])

def _get_services():
    config = load_config()
    db_p = Path(config.app.database_path)
    cfg_p = Path("config.yaml")
    return {
        "replay": PipelineReplayService(db_p),
        "models": ModelRegistryService(db_p),
        "config_hist": ConfigHistoryService(db_p, cfg_p),
        "queue": PriorityQueueService(db_p),
        "recovery": FailureRecoveryService(db_p),
        "storage": StorageIntelligenceService(db_p),
        "backup_verifier": AutomatedBackupVerifier(db_p),
    }

class ReplayRequest(BaseModel):
    media_id: int
    stage_filter: Optional[str] = None

class ModelRegisterRequest(BaseModel):
    model_name: str
    version: str
    category: str
    sha256: Optional[str] = None
    description: Optional[str] = None

class ConfigRollbackRequest(BaseModel):
    version_id: int
    changed_by: str = "user"

class JobEnqueueRequest(BaseModel):
    media_id: int
    task_type: str
    priority: int = 2
    payload: Optional[Dict[str, Any]] = None

# --- Pipeline Replay Endpoints ---
@router.get("/api/pipeline/history/{media_id}")
async def get_pipeline_history(media_id: int):
    svc = _get_services()["replay"]
    return svc.get_media_pipeline_history(media_id)

@router.post("/api/pipeline/replay")
async def replay_pipeline(req: ReplayRequest):
    svc = _get_services()["replay"]
    try:
        return svc.replay_pipeline_for_media(req.media_id, req.stage_filter)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- Model Registry Endpoints ---
@router.get("/api/models/list")
async def list_models():
    svc = _get_services()["models"]
    return svc.list_registered_models()

@router.post("/api/models/register")
async def register_model(req: ModelRegisterRequest):
    svc = _get_services()["models"]
    return svc.register_model(
        req.model_name, req.version, req.category, req.sha256, req.description
    )

# --- Config History Endpoints ---
@router.get("/api/config/history")
async def list_config_history(limit: int = 50):
    svc = _get_services()["config_hist"]
    return svc.list_versions(limit)

@router.get("/api/config/compare")
async def compare_config_versions(v_old: int, v_new: int):
    svc = _get_services()["config_hist"]
    try:
        return svc.compare_versions(v_old, v_new)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/config/rollback")
async def rollback_config_version(req: ConfigRollbackRequest):
    svc = _get_services()["config_hist"]
    try:
        return svc.rollback_to_version(req.version_id, req.changed_by)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- Priority Queue Endpoints ---
@router.post("/api/queue/enqueue")
async def enqueue_priority_job(req: JobEnqueueRequest):
    svc = _get_services()["queue"]
    job_id = svc.enqueue_job(req.media_id, req.task_type, req.priority, req.payload)
    return {"success": True, "job_id": job_id}

@router.get("/api/queue/stats")
async def get_queue_stats():
    svc = _get_services()["queue"]
    return svc.get_queue_stats()

# --- Failure Recovery Endpoints ---
@router.get("/api/recovery/overview")
async def get_failure_overview():
    svc = _get_services()["recovery"]
    return svc.get_failure_overview()

@router.post("/api/recovery/retry_all")
async def retry_all_failed():
    svc = _get_services()["recovery"]
    return svc.retry_all_failed()

@router.post("/api/recovery/ignore/{media_id}")
async def ignore_failure(media_id: int):
    svc = _get_services()["recovery"]
    return svc.ignore_failure(media_id)

# --- Storage Intelligence & Backup Verification ---
@router.get("/api/storage/breakdown")
async def get_storage_breakdown():
    svc = _get_services()["storage"]
    return svc.get_storage_breakdown()

@router.post("/api/backup/automated_verification")
async def run_backup_verification():
    svc = _get_services()["backup_verifier"]
    return svc.run_automated_restore_verification()
