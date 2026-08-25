from fastapi import APIRouter, HTTPException
from src.control_center.services import metrics_service

router = APIRouter()


@router.get("/metrics/pipeline")
def get_pipeline_metrics():
    """Return pipeline throughput, stage latencies, and success percentages."""
    try:
        return metrics_service.get_pipeline_metrics()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/failures")
def get_failure_analytics():
    """Return categorized failure counters and root-cause breakdown."""
    try:
        return metrics_service.get_failure_analytics()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/retries")
def get_retry_queue():
    """Return active retry queue and retry schedules."""
    try:
        return metrics_service.get_retry_queue()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
