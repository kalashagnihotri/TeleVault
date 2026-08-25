"""API Router for Phase 6.5H: Final Production Intelligence Layer."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.control_center.services.embedding_search_service import (
    search_by_semantic_query,
    find_similar_images
)
from src.control_center.services.person_management_service import (
    get_all_people_summaries,
    get_person_timeline,
    rename_person,
    split_person_identity,
    delete_person
)
from src.control_center.services.memory_override_service import (
    save_memory_override,
    get_memory_overrides,
    remove_memory_override
)
from src.control_center.services.smart_notification_service import get_smart_notifications_feed
from src.control_center.services.ai_recommendations_service import (
    get_maintenance_recommendations,
    execute_recommendation
)
from src.control_center.services.video_intelligence_service import (
    extract_and_store_video_intelligence,
    get_video_intelligence
)
from src.control_center.services.voice_query_service import process_voice_query
from src.control_center.services.timeline_stream_service import get_timeline_stream
from src.control_center.services.fleet_management_service import (
    register_worker_heartbeat,
    get_fleet_status
)
from src.control_center.services.encryption_service import (
    encrypt_file,
    decrypt_file
)
from src.control_center.services.simulator_service import generate_synthetic_archive_dataset
from src.control_center.services.plugin_service import (
    get_all_plugins,
    toggle_plugin
)
from src.control_center.services.ocr_intelligence_service import (
    extract_and_store_document_ocr,
    search_documents
)
from src.control_center.services.security_scorecard_service import evaluate_security_threat_model

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Production Intelligence"])


# 1. Semantic Embedding Search
class SemanticSearchRequest(BaseModel):
    query: str
    limit: int = 20

@router.post("/api/archive/semantic_search")
def api_semantic_search(payload: SemanticSearchRequest):
    return search_by_semantic_query(payload.query, payload.limit)

@router.get("/api/media/{media_id}/similar")
def api_similar_images(media_id: int, limit: int = 10):
    return find_similar_images(media_id, limit)


# 2. People Manager & Identity Timeline
@router.get("/api/people/summaries")
def api_people_summaries():
    return get_all_people_summaries()

@router.get("/api/people/{person_id}/timeline")
def api_person_timeline(person_id: int):
    return get_person_timeline(person_id)

class RenamePersonRequest(BaseModel):
    new_display_name: str

@router.post("/api/people/{person_id}/rename")
def api_rename_person(person_id: int, payload: RenamePersonRequest):
    return rename_person(person_id, payload.new_display_name)

class SplitPersonRequest(BaseModel):
    target_media_face_ids: List[int]
    new_person_name: str

@router.post("/api/people/{person_id}/split")
def api_split_person(person_id: int, payload: SplitPersonRequest):
    return split_person_identity(person_id, payload.target_media_face_ids, payload.new_person_name)

@router.delete("/api/people/{person_id}")
def api_delete_person(person_id: int):
    return delete_person(person_id)


# 3. Memory Overrides
@router.get("/api/memories/overrides")
def api_get_memory_overrides():
    return get_memory_overrides()

class MemoryOverrideRequest(BaseModel):
    original_ai_title: str
    user_title: Optional[str] = None
    user_description: Optional[str] = None
    cover_media_id: Optional[int] = None
    is_pinned: bool = False

@router.post("/api/memories/{memory_id}/override")
def api_save_memory_override(memory_id: str, payload: MemoryOverrideRequest):
    return save_memory_override(
        memory_id=memory_id,
        original_ai_title=payload.original_ai_title,
        user_title=payload.user_title,
        user_description=payload.user_description,
        cover_media_id=payload.cover_media_id,
        is_pinned=payload.is_pinned
    )

@router.delete("/api/memories/{memory_id}/override")
def api_remove_memory_override(memory_id: str):
    return remove_memory_override(memory_id)


# 4. Smart Notifications Feed
@router.get("/api/notifications/smart_feed")
def api_smart_notifications():
    return get_smart_notifications_feed()


# 5. Proactive Maintenance Recommendations
@router.get("/api/maintenance/recommendations")
def api_maintenance_recommendations():
    return get_maintenance_recommendations()

class RecommendationExecRequest(BaseModel):
    action_key: str

@router.post("/api/maintenance/recommendations/execute")
def api_execute_recommendation(payload: RecommendationExecRequest):
    return execute_recommendation(payload.action_key)


# 6. Video Intelligence
@router.get("/api/media/{media_id}/video_intelligence")
def api_video_intelligence(media_id: int):
    data = get_video_intelligence(media_id)
    if not data:
        data = extract_and_store_video_intelligence(media_id, f"media_{media_id}.mp4")
    return data


# 7. Voice Query
class VoiceQueryRequest(BaseModel):
    transcript: str

@router.post("/api/archive/voice_query")
def api_voice_query(payload: VoiceQueryRequest):
    return process_voice_query(payload.transcript)


# 8. Timeline Stream (Google Photos Style)
@router.get("/api/archive/timeline_stream")
def api_timeline_stream(page: int = 1, page_size: int = 50):
    return get_timeline_stream(page, page_size)


# 9. Distributed Worker Fleet
class WorkerHeartbeatRequest(BaseModel):
    worker_id: str
    node_name: str
    ip_address: Optional[str] = "127.0.0.1"
    capabilities: Optional[List[str]] = None
    status: str = "ONLINE"
    current_job_id: Optional[str] = None
    tasks_processed_delta: int = 0

@router.post("/api/fleet/heartbeat")
def api_worker_heartbeat(payload: WorkerHeartbeatRequest):
    return register_worker_heartbeat(
        worker_id=payload.worker_id,
        node_name=payload.node_name,
        ip_address=payload.ip_address,
        capabilities=payload.capabilities,
        status=payload.status,
        current_job_id=payload.current_job_id,
        tasks_processed_delta=payload.tasks_processed_delta
    )

@router.get("/api/fleet/status")
def api_fleet_status():
    return get_fleet_status()


# 10. At-Rest Encryption
class EncryptExportRequest(BaseModel):
    source_file_path: str
    output_file_path: str
    passphrase: str

@router.post("/api/security/encrypt_export")
def api_encrypt_export(payload: EncryptExportRequest):
    return encrypt_file(payload.source_file_path, payload.output_file_path, payload.passphrase)

class DecryptExportRequest(BaseModel):
    encrypted_file_path: str
    output_file_path: str
    passphrase: str

@router.post("/api/security/decrypt_export")
def api_decrypt_export(payload: DecryptExportRequest):
    return decrypt_file(payload.encrypted_file_path, payload.output_file_path, payload.passphrase)


# 11. Archive Dataset Simulator
class SimulatorRequest(BaseModel):
    photo_count: int = 50
    people_count: int = 5
    locations_count: int = 3

@router.post("/api/simulator/generate")
def api_simulator_generate(payload: SimulatorRequest):
    return generate_synthetic_archive_dataset(
        photo_count=payload.photo_count,
        people_count=payload.people_count,
        locations_count=payload.locations_count
    )


# 12. Plugins Registry
@router.get("/api/plugins/list")
def api_plugins_list():
    return get_all_plugins()

class PluginToggleRequest(BaseModel):
    plugin_name: str
    enabled: bool

@router.post("/api/plugins/toggle")
def api_plugins_toggle(payload: PluginToggleRequest):
    return toggle_plugin(payload.plugin_name, payload.enabled)


# 13. Document OCR & Search
class DocumentSearchRequest(BaseModel):
    query: str
    limit: int = 20

@router.post("/api/documents/search")
def api_documents_search(payload: DocumentSearchRequest):
    return search_documents(payload.query, payload.limit)

class DocumentOcrRequest(BaseModel):
    media_id: int
    raw_text_hint: Optional[str] = None

@router.post("/api/documents/extract")
def api_documents_extract(payload: DocumentOcrRequest):
    return extract_and_store_document_ocr(payload.media_id, f"doc_{payload.media_id}.jpg", payload.raw_text_hint)


# 14. Security Threat Model Scorecard
@router.get("/api/security/scorecard")
def api_security_scorecard():
    return evaluate_security_threat_model()
