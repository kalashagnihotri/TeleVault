"""API Router for Phase 6.5J: Personal AI Experience.

Endpoints:
- Conversational AI Archive Chat (/api/ai/chat)
- Memory Autobiography Generator (/api/ai/autobiography/{year})
- Emotion & Mood Understanding (/api/ai/mood/{media_id}, /api/ai/mood/collections)
- Calendar Integration (/api/calendar/events, /api/calendar/events/{id}/photos)
- Location Intelligence Hierarchy (/api/locations/hierarchy)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.config import load_config
from src.control_center.services.ai_chat_service import AIChatService
from src.control_center.services.autobiography_service import AutobiographyService
from src.control_center.services.emotion_service import EmotionService
from src.control_center.services.calendar_integration_service import CalendarIntegrationService
from src.control_center.services.location_intelligence_service import LocationIntelligenceService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Personal AI Experience"])

def _get_services():
    config = load_config()
    db_p = Path(config.app.database_path)
    return {
        "chat": AIChatService(db_p),
        "autobiography": AutobiographyService(db_p),
        "emotion": EmotionService(db_p),
        "calendar": CalendarIntegrationService(db_p),
        "location": LocationIntelligenceService(db_p),
    }

class ChatRequest(BaseModel):
    prompt: str

class CalendarEventRequest(BaseModel):
    title: str
    start_date: str
    end_date: str
    location: Optional[str] = None
    description: Optional[str] = None

# --- AI Chat ---
@router.post("/api/ai/chat")
async def chat_with_archive(req: ChatRequest):
    svc = _get_services()["chat"]
    return svc.chat_query(req.prompt)

# --- Autobiography Generator ---
@router.get("/api/ai/autobiography/{year}")
async def get_autobiography(year: str):
    svc = _get_services()["autobiography"]
    return svc.generate_annual_autobiography(year)

# --- Emotion & Mood ---
@router.get("/api/ai/mood/{media_id}")
async def get_media_mood(media_id: int):
    svc = _get_services()["emotion"]
    try:
        return svc.analyze_media_mood(media_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/api/ai/mood/collections")
async def get_mood_collections():
    svc = _get_services()["emotion"]
    return svc.list_mood_collections()

# --- Calendar Integration ---
@router.post("/api/calendar/events")
async def add_calendar_event(req: CalendarEventRequest):
    svc = _get_services()["calendar"]
    return svc.add_calendar_event(req.title, req.start_date, req.end_date, req.location, req.description)

@router.get("/api/calendar/events")
async def list_calendar_events():
    svc = _get_services()["calendar"]
    return svc.list_calendar_events()

@router.get("/api/calendar/events/{event_id}/photos")
async def get_calendar_event_photos(event_id: str):
    svc = _get_services()["calendar"]
    try:
        return svc.get_event_matched_media(event_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

# --- Location Intelligence ---
@router.get("/api/locations/hierarchy")
async def get_locations_hierarchy():
    svc = _get_services()["location"]
    return svc.get_places_visited_hierarchy()
