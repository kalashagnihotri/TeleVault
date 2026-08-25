"""Calendar Integration Service for Phase 6.5J.

Correlates external calendar entries (Google Calendar / ICS formats) with archive photos by date range and location.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class CalendarIntegrationService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def add_calendar_event(
        self,
        title: str,
        start_date: str,
        end_date: str,
        location: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert a new calendar event and match with photos."""
        evt_id = f"cal_{uuid.uuid4().hex[:8]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            # Match photos within date range
            cnt = conn.execute(
                "SELECT COUNT(*) FROM media WHERE date_taken >= ? AND date_taken <= ?",
                (start_date, end_date),
            ).fetchone()[0]

            conn.execute(
                """
                INSERT INTO calendar_events 
                (id, title, start_date, end_date, location, description, matched_media_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (evt_id, title, start_date, end_date, location or "", description or "", cnt, now_iso),
            )

        logger.info("Added calendar event %s ('%s', %d matched photos)", evt_id, title, cnt)
        return {
            "id": evt_id,
            "title": title,
            "start_date": start_date,
            "end_date": end_date,
            "location": location,
            "matched_media_count": cnt,
        }

    def list_calendar_events(self) -> List[Dict[str, Any]]:
        """Return all calendar events with matched photo counts."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, title, start_date, end_date, location, description, matched_media_count, created_at FROM calendar_events ORDER BY start_date DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_event_matched_media(self, event_id: str) -> Dict[str, Any]:
        """Fetch all photos matching a specific calendar event."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            evt = conn.execute("SELECT * FROM calendar_events WHERE id = ?", (event_id,)).fetchone()
            if not evt:
                raise ValueError(f"Calendar event {event_id} not found.")

            photos = conn.execute(
                """
                SELECT id, original_filename, date_taken, location_label, labels_json, people_json
                FROM media
                WHERE date_taken >= ? AND date_taken <= ?
                ORDER BY date_taken ASC
                """,
                (evt["start_date"], evt["end_date"]),
            ).fetchall()

        return {
            "event": dict(evt),
            "matched_photos": [dict(p) for p in photos],
        }
