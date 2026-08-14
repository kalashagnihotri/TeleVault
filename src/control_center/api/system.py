from fastapi import APIRouter
from src.control_center.schemas.system import SystemHealthResponse
from src.control_center.services import system_service

router = APIRouter()

@router.get("/system", response_model=SystemHealthResponse)
async def get_system_health():
    return system_service.get_system_health()

@router.get("/system/diagnostic_report")
async def get_diagnostic_report():
    return system_service.get_diagnostic_report()
