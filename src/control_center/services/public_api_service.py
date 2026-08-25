"""Public REST API v1 Service for Phase 7.

Exposes external 3rd-party integration endpoints (/api/v1/photos, /api/v1/people, /api/v1/memories)
protected by scoped API keys and token lifecycle management.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class PublicAPIService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._ensure_default_api_key()

    def _ensure_default_api_key(self) -> None:
        """Create a default local developer API key if none exists."""
        with sqlite3.connect(self.db_path) as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM api_tokens").fetchone()[0]
            if cnt == 0:
                self.create_api_token(name="Default Developer Token", raw_token="televault_live_dev_token_2026")

    def create_api_token(self, name: str, raw_token: Optional[str] = None) -> Dict[str, Any]:
        """Create a new API key."""
        token_str = raw_token or f"tv_key_{uuid.uuid4().hex}"
        tok_hash = hashlib.sha256(token_str.encode("utf-8")).hexdigest()
        tok_id = f"tok_{uuid.uuid4().hex[:8]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO api_tokens (token_id, token_hash, name, scopes_json, created_at, active)
                VALUES (?, ?, ?, '["read", "photos", "memories", "people"]', ?, 1)
                """,
                (tok_id, tok_hash, name, now_iso),
            )

        logger.info("Created public API token %s ('%s')", tok_id, name)
        return {
            "token_id": tok_id,
            "name": name,
            "raw_token": token_str,
            "created_at": now_iso,
        }

    def list_api_tokens(self) -> List[Dict[str, Any]]:
        """Return all API tokens without revealing hashes."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT token_id, name, scopes_json, created_at, last_used_at, active FROM api_tokens ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def validate_token(self, raw_token: str) -> bool:
        """Validate API token authenticity."""
        tok_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        now_iso = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT token_id FROM api_tokens WHERE token_hash = ? AND active = 1",
                (tok_hash,),
            ).fetchone()
            if row:
                conn.execute("UPDATE api_tokens SET last_used_at = ? WHERE token_id = ?", (now_iso, row[0]))
                return True
        return False

    def get_public_photos(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """Public endpoint: GET /api/v1/photos"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, original_filename, media_type, size_bytes, date_taken, location_label, state
                FROM media
                WHERE state = 'BACKED_UP'
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_public_people(self) -> List[Dict[str, Any]]:
        """Public endpoint: GET /api/v1/people"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT person_id, person_slug, display_name, active, created_at
                FROM people
                WHERE active = 1
                ORDER BY display_name ASC
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def get_public_memories(self) -> List[Dict[str, Any]]:
        """Public endpoint: GET /api/v1/memories"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT memory_id, title, category, start_date, end_date, total_photos, cover_media_id, is_curated
                FROM memories
                ORDER BY start_date DESC
                """
            ).fetchall()
        return [dict(r) for r in rows]
