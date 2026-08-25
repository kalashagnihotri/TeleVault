"""
AI Models API Endpoints for Control Center.
"""
from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.control_center.services import model_service

router = APIRouter()


class BenchmarkRequest(BaseModel):
    model_id: str


@router.get("/models")
def list_models():
    """Return all registered AI models and their disk/readiness status."""
    return model_service.get_models_status()


@router.post("/models/verify")
def verify_model_signatures():
    """Verify SHA-256 signatures of all registered models."""
    return model_service.verify_models()


@router.post("/models/benchmark")
def benchmark_model_endpoint(req: BenchmarkRequest):
    """Run synthetic inference benchmark on specified model."""
    try:
        return model_service.benchmark_model(req.model_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference benchmark failed: {e}")
