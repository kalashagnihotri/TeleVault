from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from src.control_center.services import face_management_service, scene_management_service

router = APIRouter()


class CreatePersonFromClusterRequest(BaseModel):
    cluster_id: str
    display_name: str


class MergeIdentitiesRequest(BaseModel):
    source_person_id: int
    target_person_id: int


class ReprocessScenesRequest(BaseModel):
    mode: str = "failed"
    media_ids: Optional[List[int]] = None


# Face Management Endpoints
@router.get("/faces/unknown_clusters")
def get_unknown_face_clusters():
    """Return clustered unknown faces requiring review."""
    try:
        return face_management_service.get_unknown_face_clusters()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/faces/clusters/create_person")
def create_person_from_cluster(req: CreatePersonFromClusterRequest):
    """Enroll a new identity from an unknown cluster."""
    try:
        return face_management_service.create_person_from_cluster(req.cluster_id, req.display_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/faces/merge_identities")
def merge_identities(req: MergeIdentitiesRequest):
    """Merge duplicate identity into canonical person."""
    try:
        return face_management_service.merge_identities(req.source_person_id, req.target_person_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/faces/confidence_stats")
def get_face_confidence_stats():
    """Return distribution of face match confidence."""
    try:
        return face_management_service.get_face_confidence_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Scene Management Endpoints
@router.get("/scenes/{media_id}/confidence")
def get_scene_confidence(media_id: int):
    """Return itemized scene tags and confidence scores for a media asset."""
    try:
        return scene_management_service.get_scene_confidence_data(media_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenes/reprocess_queue")
def get_scene_reprocess_queue():
    """Return count of images eligible for scene reprocessing."""
    try:
        return scene_management_service.get_scene_reprocess_queue()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scenes/reprocess")
def reprocess_scenes(req: ReprocessScenesRequest):
    """Re-trigger scene analysis for targeted or failed assets."""
    try:
        return scene_management_service.reprocess_scenes(req.mode, req.media_ids)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
