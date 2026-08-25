from fastapi import APIRouter, HTTPException
from src.control_center.services import integrity_service

router = APIRouter()


@router.post("/integrity/scan")
def run_integrity_scan():
    """Trigger a comprehensive filesystem and database integrity audit."""
    try:
        return integrity_service.run_deep_integrity_scan()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/integrity/report")
def get_integrity_report():
    """Retrieve the latest archive integrity scan report."""
    try:
        return integrity_service.get_last_integrity_report()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
