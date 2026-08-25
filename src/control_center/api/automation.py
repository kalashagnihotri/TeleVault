"""Automation, Scheduler, Lifecycle, Preferences & Workers API Router (Phase 6.5G)"""

from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.control_center.services.lifecycle_service import get_media_lifecycle_summary
from src.control_center.services.preference_service import get_user_preferences_profile, record_interaction
from src.control_center.services.retry_engine_service import process_retry_queue
from src.control_center.services.scheduler_service import (
    execute_maintenance_cycle,
    get_scheduler_status,
    toggle_scheduler_task
)
from src.workers.worker_manager import get_worker_fleet_status

router = APIRouter(prefix="/api/automation", tags=["Automation & Fleet"])


class ToggleTaskRequest(BaseModel):
    task_name: str
    enabled: bool


class PreferenceInteractionRequest(BaseModel):
    category: str
    increment: float = 1.0


@router.get("/scheduler/status")
def get_scheduler_status_endpoint() -> Dict[str, Any]:
    return get_scheduler_status()


@router.post("/scheduler/toggle")
def post_toggle_task(req: ToggleTaskRequest) -> Dict[str, Any]:
    return toggle_scheduler_task(req.task_name, req.enabled)


@router.post("/maintenance/run")
def post_run_maintenance() -> Dict[str, Any]:
    return execute_maintenance_cycle(actor="USER_MANUAL_TRIGGER")


@router.post("/retries/process")
def post_process_retries() -> Dict[str, Any]:
    return process_retry_queue()


@router.get("/lifecycle")
def get_lifecycle_endpoint() -> Dict[str, Any]:
    return get_media_lifecycle_summary()


@router.get("/preferences")
def get_preferences_endpoint() -> Dict[str, Any]:
    return get_user_preferences_profile()


@router.post("/preferences/interact")
def post_preference_interaction(req: PreferenceInteractionRequest) -> Dict[str, Any]:
    record_interaction(req.category, req.increment)
    return {"success": True, "category": req.category}


@router.get("/workers")
def get_workers_endpoint() -> Dict[str, Any]:
    return get_worker_fleet_status()
