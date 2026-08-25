"""API Router for Phase 7: Architecture Evolution.

Endpoints:
- Mobile Companion & PWA Manifest (/manifest.json, /api/mobile/sync_status)
- Private Cloud Sync Protocol (/api/cloud/status, /api/cloud/sync_dry_run)
- Plugin Marketplace (/api/marketplace/list, /api/marketplace/install)
- Public REST API v1 (/api/v1/tokens, /api/v1/photos, /api/v1/people, /api/v1/memories)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from src.config import load_config
from src.control_center.services.mobile_companion_service import MobileCompanionService
from src.control_center.services.cloud_sync_service import CloudSyncService
from src.control_center.services.marketplace_service import PluginMarketplaceService
from src.control_center.services.public_api_service import PublicAPIService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Architecture Evolution"])

def _get_services():
    config = load_config()
    db_p = Path(config.app.database_path)
    return {
        "mobile": MobileCompanionService(),
        "cloud": CloudSyncService(db_p),
        "marketplace": PluginMarketplaceService(db_p),
        "public_api": PublicAPIService(db_p),
    }

class CreateTokenRequest(BaseModel):
    name: str

class InstallPluginRequest(BaseModel):
    plugin_id: str

# --- Mobile Companion & PWA ---
@router.get("/manifest.json")
async def get_pwa_manifest():
    svc = _get_services()["mobile"]
    return svc.get_pwa_manifest()

@router.get("/api/mobile/sync_status")
async def get_mobile_sync_status():
    svc = _get_services()["mobile"]
    return svc.get_mobile_sync_status()

# --- Private Cloud Sync ---
@router.get("/api/cloud/status")
async def get_cloud_status():
    svc = _get_services()["cloud"]
    return svc.get_cloud_sync_status()

@router.post("/api/cloud/sync_dry_run")
async def trigger_cloud_sync():
    svc = _get_services()["cloud"]
    return svc.trigger_cloud_sync_dry_run()

# --- Plugin Marketplace ---
@router.get("/api/marketplace/list")
async def list_marketplace():
    svc = _get_services()["marketplace"]
    return svc.list_marketplace_plugins()

@router.post("/api/marketplace/install")
async def install_marketplace_plugin(req: InstallPluginRequest):
    svc = _get_services()["marketplace"]
    try:
        return svc.install_plugin(req.plugin_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- Public REST API v1 Token Management ---
@router.post("/api/v1/tokens")
async def create_api_token(req: CreateTokenRequest):
    svc = _get_services()["public_api"]
    return svc.create_api_token(req.name)

@router.get("/api/v1/tokens")
async def list_api_tokens():
    svc = _get_services()["public_api"]
    return svc.list_api_tokens()

# --- Public REST API v1 Endpoints ---
@router.get("/api/v1/photos")
async def get_public_photos(limit: int = 20, offset: int = 0, authorization: Optional[str] = Header(None)):
    svc = _get_services()["public_api"]
    # Allow loopback/internal test queries or validate token if auth header provided
    if authorization:
        tok = authorization.replace("Bearer ", "").strip()
        if not svc.validate_token(tok):
            raise HTTPException(status_code=401, detail="Invalid API token.")
    return svc.get_public_photos(limit, offset)

@router.get("/api/v1/people")
async def get_public_people(authorization: Optional[str] = Header(None)):
    svc = _get_services()["public_api"]
    if authorization:
        tok = authorization.replace("Bearer ", "").strip()
        if not svc.validate_token(tok):
            raise HTTPException(status_code=401, detail="Invalid API token.")
    return svc.get_public_people()

@router.get("/api/v1/memories")
async def get_public_memories(authorization: Optional[str] = Header(None)):
    svc = _get_services()["public_api"]
    if authorization:
        tok = authorization.replace("Bearer ", "").strip()
        if not svc.validate_token(tok):
            raise HTTPException(status_code=401, detail="Invalid API token.")
    return svc.get_public_memories()
