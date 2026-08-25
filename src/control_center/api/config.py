"""
Config API Endpoints for Control Center (Phase 6.5C).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.control_center.services import config_service

router = APIRouter()


class ConfigPayload(BaseModel):
    config: Dict[str, Any]


class ConfigValidationResponse(BaseModel):
    valid: bool
    errors: List[str]


class ConfigSaveResponse(BaseModel):
    success: bool
    message: str
    errors: List[str] = []


class ConfigDiffItem(BaseModel):
    path: str
    key: str
    old_value: Any
    new_value: Any
    change_type: str  # "MODIFIED", "ADDED", "REMOVED"


class RestoreRequest(BaseModel):
    filename: str


@router.get("/config")
def get_config():
    """Return the active configuration dict."""
    try:
        return config_service.get_active_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/validate", response_model=ConfigValidationResponse)
def validate_config_endpoint(payload: ConfigPayload):
    """Validate submitted configuration in memory."""
    valid, errors = config_service.validate_config(payload.config)
    return ConfigValidationResponse(valid=valid, errors=errors)


@router.post("/config/diff", response_model=List[ConfigDiffItem])
def compute_config_diff_endpoint(payload: ConfigPayload):
    """Compute structured differences between active on-disk config and proposed payload."""
    try:
        return config_service.compute_config_diff(payload.config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute config diff: {e}")


@router.post("/config/save", response_model=ConfigSaveResponse)
def save_config_endpoint(payload: ConfigPayload):
    """Validate, create backup, and apply new configuration to config.yaml."""
    success, errors = config_service.save_config(payload.config)
    if not success:
        return ConfigSaveResponse(success=False, message="Configuration validation failed", errors=errors)
    return ConfigSaveResponse(success=True, message="Configuration saved and applied successfully.", errors=[])


@router.get("/config/backups")
def get_config_backups():
    """List historical config backups."""
    return config_service.list_backups()


@router.post("/config/restore")
def restore_config_endpoint(req: RestoreRequest):
    """Restore configuration from a selected backup file."""
    try:
        config_service.restore_backup(req.filename)
        return {"success": True, "message": f"Successfully restored configuration from {req.filename}"}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
