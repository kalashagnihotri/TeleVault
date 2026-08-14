from fastapi import APIRouter
from src.control_center.schemas.system import HealthResponse

router = APIRouter()

@router.get("/health", response_model=HealthResponse)
async def get_health():
    return HealthResponse(status="ok")
