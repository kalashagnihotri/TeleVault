"""Human Correction Learning & Feedback Service (Phase 6.5G Pillar 1)

Closes the active learning loop when humans confirm, reject, merge,
or correct face recognition and scene classification predictions.
"""

from __future__ import annotations

import json
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
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def record_face_feedback(
    media_id: int,
    action: str,
    new_identity: Optional[str] = None,
    face_id: Optional[int] = None,
    person_id: Optional[int] = None,
    notes: Optional[str] = None,
    actor: str = "USER"
) -> Dict[str, Any]:
    """
    Record human feedback on face recognition and update model confidence / person mappings.
    Actions:
    - CONFIRM: Confirm detected match, increment person reference strength
    - REJECT: Invalidate match, mark as UNKNOWN or IGNORED
    - MERGE: Reassign face to specified person
    - IGNORE: Suppress future detection for this face artifact
    """
    conn = _get_db_conn()
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        cur = conn.cursor()
        
        # 1. Fetch current face prediction if face_id given
        old_pred = None
        if face_id:
            cur.execute(
                """
                SELECT mf.media_face_id, mf.best_person_id, mf.decision, p.display_name
                FROM media_faces mf
                LEFT JOIN people p ON mf.best_person_id = p.person_id
                WHERE mf.media_face_id = ?
                """,
                (face_id,)
            )
            row = cur.fetchone()
            if row:
                old_pred = row["display_name"] or row["decision"]

        # 2. Determine target person_id if new_identity string is provided
        target_person_id = person_id
        if not target_person_id and new_identity:
            slug = new_identity.lower().strip().replace(" ", "_")
            cur.execute("SELECT person_id FROM people WHERE person_slug = ?", (slug,))
            p_row = cur.fetchone()
            if p_row:
                target_person_id = p_row["person_id"]
            else:
                cur.execute(
                    "INSERT INTO people (person_slug, display_name, active, created_at, updated_at) VALUES (?, ?, 1, ?, ?)",
                    (slug, new_identity.strip(), now_iso, now_iso)
                )
                target_person_id = cur.lastrowid

        # 3. Apply state update
        before_state = {"action": action, "old_prediction": old_pred}
        after_state = {"target_person_id": target_person_id, "new_identity": new_identity}

        if action == "CONFIRM" and face_id and target_person_id:
            cur.execute(
                "UPDATE media_faces SET best_person_id = ?, decision = 'KNOWN_MATCH', best_score = 0.98 WHERE media_face_id = ?",
                (target_person_id, face_id)
            )
        elif action == "REJECT" and face_id:
            cur.execute(
                "UPDATE media_faces SET best_person_id = NULL, decision = 'UNKNOWN' WHERE media_face_id = ?",
                (face_id,)
            )
        elif action == "MERGE" and face_id and target_person_id:
            cur.execute(
                "UPDATE media_faces SET best_person_id = ?, decision = 'KNOWN_MATCH', best_score = 0.95 WHERE media_face_id = ?",
                (target_person_id, face_id)
            )
        elif action == "IGNORE" and face_id:
            cur.execute(
                "UPDATE media_faces SET decision = 'IGNORED' WHERE media_face_id = ?",
                (face_id,)
            )

        # 4. Insert feedback record
        cur.execute(
            """
            INSERT INTO face_feedback (media_id, face_id, action, old_prediction, new_identity, person_id, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (media_id, face_id, action, old_pred, new_identity, target_person_id, notes, now_iso)
        )
        feedback_id = cur.lastrowid
        conn.commit()

        # 5. Log audit event
        record_audit_event(
            actor=actor,
            action=f"FACE_FEEDBACK_{action}",
            object_type="media_faces",
            object_id=str(face_id or media_id),
            before_state=json.dumps(before_state),
            after_state=json.dumps(after_state)
        )

        logger.info("Recorded face feedback #%s (action=%s, media=%s)", feedback_id, action, media_id)
        return {
            "success": True,
            "feedback_id": feedback_id,
            "action": action,
            "target_person_id": target_person_id,
            "message": f"Successfully applied face feedback '{action}'."
        }
    finally:
        conn.close()


def record_scene_feedback(
    media_id: int,
    new_label: str,
    confidence: float = 1.0,
    notes: Optional[str] = None,
    actor: str = "USER"
) -> Dict[str, Any]:
    """Record human correction for scene classification and update media tags."""
    conn = _get_db_conn()
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        cur = conn.cursor()
        
        # 1. Fetch current scene state
        cur.execute("SELECT labels_json FROM media WHERE id = ?", (media_id,))
        m_row = cur.fetchone()
        old_pred = None
        current_labels = []
        if m_row and m_row["labels_json"]:
            try:
                current_labels = json.loads(m_row["labels_json"])
                old_pred = current_labels[0] if current_labels else None
            except Exception:
                pass

        # 2. Update media labels with user override
        cleaned_label = new_label.strip()
        updated_labels = [cleaned_label] + [l for l in current_labels if l.lower() != cleaned_label.lower()]
        
        cur.execute(
            "UPDATE media SET labels_json = ?, scene_state = 'ANALYZED', updated_at = ? WHERE id = ?",
            (json.dumps(updated_labels), now_iso, media_id)
        )

        # 3. Insert feedback record
        cur.execute(
            """
            INSERT INTO scene_feedback (media_id, old_prediction, new_label, confidence, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (media_id, old_pred, cleaned_label, confidence, notes, now_iso)
        )
        feedback_id = cur.lastrowid
        conn.commit()

        # 4. Record audit event
        record_audit_event(
            actor=actor,
            action="SCENE_FEEDBACK_CORRECTION",
            object_type="media",
            object_id=str(media_id),
            before_state=json.dumps({"old_prediction": old_pred, "labels": current_labels}),
            after_state=json.dumps({"new_label": cleaned_label, "labels": updated_labels})
        )

        logger.info("Recorded scene feedback #%s (media=%s, label=%s)", feedback_id, media_id, cleaned_label)
        return {
            "success": True,
            "feedback_id": feedback_id,
            "media_id": media_id,
            "new_label": cleaned_label,
            "labels": updated_labels,
            "message": f"Updated scene label to '{cleaned_label}'."
        }
    finally:
        conn.close()
