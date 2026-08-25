"""Feedback & Audit Trail API Endpoints (Phase 6.5G)"""

from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.control_center.services.audit_service import get_audit_timeline
from src.control_center.services.feedback_learning_service import (
    record_face_feedback,
    record_scene_feedback
)

router = APIRouter(prefix="/api", tags=["Feedback & Audit"])


class FaceFeedbackRequest(BaseModel):
    media_id: int
    action: str  # CONFIRM, REJECT, MERGE, IGNORE
    new_identity: Optional[str] = None
    face_id: Optional[int] = None
    person_id: Optional[int] = None
    notes: Optional[str] = None


class SceneFeedbackRequest(BaseModel):
    media_id: int
    new_label: str
    confidence: float = 1.0
    notes: Optional[str] = None


@router.post("/feedback/face")
def post_face_feedback(req: FaceFeedbackRequest) -> Dict[str, Any]:
    try:
        return record_face_feedback(
            media_id=req.media_id,
            action=req.action,
            new_identity=req.new_identity,
            face_id=req.face_id,
            person_id=req.person_id,
            notes=req.notes
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback/scene")
def post_scene_feedback(req: SceneFeedbackRequest) -> Dict[str, Any]:
    try:
        return record_scene_feedback(
            media_id=req.media_id,
            new_label=req.new_label,
            confidence=req.confidence,
            notes=req.notes
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit/timeline")
def get_audit_timeline_endpoint(
    limit: int = 50,
    offset: int = 0,
    action: Optional[str] = None,
    actor: Optional[str] = None
) -> Dict[str, Any]:
    return get_audit_timeline(limit=limit, offset=offset, action_filter=action, actor_filter=actor)
