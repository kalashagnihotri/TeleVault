"""Memory Human Customization & Override Service (Phase 6.5H Pillar 3)

Allows humans to edit, customize, pin, and retitle AI-generated memories.
Human edits always take precedence over machine generation while preserving original context.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import load_config
from src.control_center.services.audit_service import record_audit_event

logger = logging.getLogger(__name__)


def _get_db_conn() -> sqlite3.Connection:
    config = load_config()
    db_path = Path(config.app.database_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def save_memory_override(
    memory_id: str,
    original_ai_title: str,
    user_title: Optional[str] = None,
    user_description: Optional[str] = None,
    cover_media_id: Optional[int] = None,
    is_pinned: bool = False
) -> Dict[str, Any]:
    """Save or update human customization overrides for a memory."""
    conn = _get_db_conn()
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_overrides 
                (memory_id, original_ai_title, user_title, user_description, cover_media_id, is_pinned, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    original_ai_title,
                    user_title or original_ai_title,
                    user_description or "",
                    cover_media_id,
                    1 if is_pinned else 0,
                    now_iso
                )
            )

        record_audit_event(
            actor="USER",
            action="SAVE_MEMORY_OVERRIDE",
            object_type="memory",
            object_id=memory_id,
            before_state={"original_ai_title": original_ai_title},
            after_state={"user_title": user_title, "user_description": user_description, "is_pinned": is_pinned}
        )

        return {
            "success": True,
            "memory_id": memory_id,
            "active_title": user_title or original_ai_title,
            "user_description": user_description,
            "is_pinned": is_pinned
        }
    finally:
        conn.close()


def get_memory_overrides() -> Dict[str, Dict[str, Any]]:
    """Return all active memory overrides mapped by memory_id."""
    conn = _get_db_conn()
    overrides: Dict[str, Dict[str, Any]] = {}
    try:
        cur = conn.cursor()
        cur.execute("SELECT memory_id, original_ai_title, user_title, user_description, cover_media_id, is_pinned, updated_at FROM memory_overrides")
        for r in cur.fetchall():
            overrides[r["memory_id"]] = {
                "memory_id": r["memory_id"],
                "original_ai_title": r["original_ai_title"],
                "user_title": r["user_title"],
                "user_description": r["user_description"],
                "cover_media_id": r["cover_media_id"],
                "is_pinned": bool(r["is_pinned"]),
                "updated_at": r["updated_at"]
            }
        return overrides
    finally:
        conn.close()


def remove_memory_override(memory_id: str) -> Dict[str, Any]:
    """Revert a memory back to AI default generation."""
    conn = _get_db_conn()
    try:
        with conn:
            conn.execute("DELETE FROM memory_overrides WHERE memory_id = ?", (memory_id,))
        record_audit_event(
            actor="USER",
            action="REVERT_MEMORY_OVERRIDE",
            object_type="memory",
            object_id=memory_id,
            before_state={"overridden": True},
            after_state={"overridden": False}
        )
        return {"success": True, "memory_id": memory_id, "message": "Reverted memory to AI defaults."}
    finally:
        conn.close()
