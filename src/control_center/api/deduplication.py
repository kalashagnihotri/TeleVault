"""Near-Deduplication API Router (Phase 6.5G Pillar 9)"""

from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter
from pydantic import BaseModel

from src.control_center.services.deduplication_service import scan_for_near_duplicates

router = APIRouter(prefix="/api/deduplication", tags=["Near-Deduplication"])


class DeduplicationScanRequest(BaseModel):
    distance_threshold: int = 5


@router.post("/scan")
def post_scan_near_duplicates(req: DeduplicationScanRequest = DeduplicationScanRequest()) -> Dict[str, Any]:
    return scan_for_near_duplicates(distance_threshold=req.distance_threshold)
