from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.control_center.schemas.system import SystemHealthResponse
from src.control_center.services import system_service, db_service

router = APIRouter()

class SystemModeRequest(BaseModel):
    mode: str  # "safe" or "production"

class SystemModeResponse(BaseModel):
    mode: str
    updated_at: str

@router.get("/system", response_model=SystemHealthResponse)
async def get_system_health():
    return system_service.get_system_health()

@router.get("/system/diagnostic_report")
async def get_diagnostic_report():
    return system_service.get_diagnostic_report()

@router.get("/system/mode")
async def get_system_mode():
    mode = db_service.get_system_mode()
    return {"mode": mode}

@router.post("/system/mode")
async def update_system_mode(req: SystemModeRequest):
    if req.mode.lower() not in ("safe", "production"):
        raise HTTPException(status_code=400, detail="Invalid system mode. Must be 'safe' or 'production'.")
    saved_mode = db_service.set_system_mode(req.mode.lower())
    return {"mode": saved_mode, "status": "updated"}
