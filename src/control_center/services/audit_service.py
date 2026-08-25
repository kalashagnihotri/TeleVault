"""Audit Trail Service (Phase 6.5G Pillar 2)

Maintains an immutable historical ledger of all configuration changes,
identity merges, restore events, automated maintenance, and human feedback.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import load_config

logger = logging.getLogger(__name__)


def _get_db_conn() -> sqlite3.Connection:
    config = load_config()
    db_path = Path(config.app.database_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def record_audit_event(
    actor: str,
    action: str,
    object_type: str,
    object_id: Optional[str] = None,
    before_state: Optional[str] = None,
    after_state: Optional[str] = None
) -> int:
    """Insert an immutable audit event into the ledger."""
    conn = _get_db_conn()
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO audit_events (actor, action, object_type, object_id, before_state, after_state, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (actor, action, object_type, object_id, before_state, after_state, now_iso)
        )
        conn.commit()
        event_id = cur.lastrowid
        return event_id
    except Exception as e:
        logger.warning("Failed to record audit event: %s", e)
        return -1
    finally:
        conn.close()


def get_audit_timeline(
    limit: int = 50,
    offset: int = 0,
    action_filter: Optional[str] = None,
    actor_filter: Optional[str] = None
) -> Dict[str, Any]:
    """Retrieve chronological audit timeline with optional filters."""
    conn = _get_db_conn()
    try:
        cur = conn.cursor()
        query = "SELECT id, actor, action, object_type, object_id, before_state, after_state, timestamp FROM audit_events WHERE 1=1"
        params: List[Any] = []

        if action_filter:
            query += " AND action LIKE ?"
            params.append(f"%{action_filter}%")
        if actor_filter:
            query += " AND actor = ?"
            params.append(actor_filter)

        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cur.execute(query, tuple(params))
        rows = [dict(r) for r in cur.fetchall()]

        # Parse JSON states if applicable
        for r in rows:
            if r.get("before_state"):
                try:
                    r["before_state_parsed"] = json.loads(r["before_state"])
                except Exception:
                    r["before_state_parsed"] = r["before_state"]
            if r.get("after_state"):
                try:
                    r["after_state_parsed"] = json.loads(r["after_state"])
                except Exception:
                    r["after_state_parsed"] = r["after_state"]

        cur.execute("SELECT COUNT(*) FROM audit_events")
        total_count = cur.fetchone()[0]

        return {
            "total_events": total_count,
            "returned_count": len(rows),
            "events": rows
        }
    finally:
        conn.close()
