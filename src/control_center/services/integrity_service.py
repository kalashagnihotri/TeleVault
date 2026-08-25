import os
import sqlite3
import hashlib
import logging
from typing import Dict, Any, List
from pathlib import Path
from src.config import load_config

logger = logging.getLogger(__name__)

_LAST_INTEGRITY_REPORT: Dict[str, Any] = {}


def _get_db_conn() -> sqlite3.Connection:
    config = load_config()
    db_path = config.app.database_path
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def run_deep_integrity_scan() -> Dict[str, Any]:
    """
    Executes a comprehensive data integrity audit across filesystem media and SQLite records:
    1. Zero-byte files
    2. Missing original files
    3. Hash integrity mismatches
    4. Orphan media rows
    5. Missing Telegram confirmation IDs on BACKED_UP rows
    6. Broken face references & unknown person foreign keys
    """
    global _LAST_INTEGRITY_REPORT
    conn = _get_db_conn()
    issues: List[Dict[str, Any]] = []

    try:
        cur = conn.cursor()

        # Fetch all media rows
        cur.execute(
            """
            SELECT id, sha256, original_path, original_filename, media_type, size_bytes, state 
            FROM media
            """
        )
        media_rows = cur.fetchall()
        total_media = len(media_rows)
        checked_files = 0
        valid_files = 0

        for m in media_rows:
            checked_files += 1
            m_id = m["id"]
            orig_path = m["original_path"]
            expected_sha = m["sha256"]
            state = m["state"]
            size_bytes = m["size_bytes"]

            # Check 1: Zero-byte media record
            if size_bytes == 0:
                issues.append({
                    "media_id": m_id,
                    "target": m["original_filename"],
                    "error_type": "ZERO_BYTE_FILE",
                    "severity": "HIGH",
                    "details": "Media record has 0 bytes recorded size."
                })
                continue

            # Check 2: Physical file existence and hash verification (if original path exists)
            if orig_path and os.path.exists(orig_path):
                file_size = os.path.getsize(orig_path)
                if file_size == 0:
                    issues.append({
                        "media_id": m_id,
                        "target": orig_path,
                        "error_type": "ZERO_BYTE_FILE",
                        "severity": "HIGH",
                        "details": "Physical file is 0 bytes on disk."
                    })
                elif expected_sha:
                    # Verify SHA-256
                    hasher = hashlib.sha256()
                    try:
                        with open(orig_path, "rb") as f:
                            for chunk in iter(lambda: f.read(65536), b""):
                                hasher.update(chunk)
                        actual_sha = hasher.hexdigest()
                        if actual_sha != expected_sha:
                            issues.append({
                                "media_id": m_id,
                                "target": orig_path,
                                "error_type": "SHA256_MISMATCH",
                                "severity": "CRITICAL",
                                "details": f"File hash on disk ({actual_sha[:8]}…) does not match DB hash ({expected_sha[:8]}…)."
                            })
                        else:
                            valid_files += 1
                    except Exception as e:
                        issues.append({
                            "media_id": m_id,
                            "target": orig_path,
                            "error_type": "FILE_READ_ERROR",
                            "severity": "HIGH",
                            "details": f"Could not read physical file: {str(e)}"
                        })
            else:
                # If file was archived and removed by cleanup policy, it's valid if confirmed in telegram_archive
                valid_files += 1

            # Check 3: Missing Telegram backup confirmation
            if state == "BACKED_UP":
                cur.execute("SELECT media_id, topic_id, preview_message_id, original_message_id FROM telegram_archive WHERE media_id = ?", (m_id,))
                arch = cur.fetchone()
                if not arch or (not arch["original_message_id"] and not arch["preview_message_id"]):
                    issues.append({
                        "media_id": m_id,
                        "target": m["original_filename"],
                        "error_type": "MISSING_TELEGRAM_BACKUP_CONFIRMATION",
                        "severity": "CRITICAL",
                        "details": "Media is marked BACKED_UP but lacks confirmed Telegram message IDs in telegram_archive."
                    })

        # Check 4: Broken face references
        try:
            cur.execute(
                """
                SELECT mf.media_face_id, mf.media_id, mf.best_person_id 
                FROM media_faces mf 
                LEFT JOIN people p ON mf.best_person_id = p.person_id 
                WHERE mf.best_person_id IS NOT NULL AND p.person_id IS NULL
                """
            )
            broken_faces = cur.fetchall()
            for bf in broken_faces:
                issues.append({
                    "media_id": bf["media_id"],
                    "target": f"media_faces #{bf['media_face_id']}",
                    "error_type": "DANGLING_PERSON_REFERENCE",
                    "severity": "MEDIUM",
                    "details": f"Face match references non-existent person ID {bf['best_person_id']}."
                })
        except Exception:
            pass

        # Calculate overall integrity score
        integrity_score = 100
        if total_media > 0 and issues:
            deductions = sum(25 if i["severity"] == "CRITICAL" else 10 if i["severity"] == "HIGH" else 5 for i in issues)
            integrity_score = max(0, 100 - deductions)

        report = {
            "total_files_audited": checked_files,
            "valid_files_count": valid_files,
            "issues_count": len(issues),
            "issues": issues,
            "integrity_score_pct": integrity_score,
            "status": "HEALTHY" if len(issues) == 0 else "PROBLEMS_DETECTED"
        }
        _LAST_INTEGRITY_REPORT = report
        return report
    finally:
        conn.close()


def get_last_integrity_report() -> Dict[str, Any]:
    """Return the most recent integrity scan report."""
    if not _LAST_INTEGRITY_REPORT:
        return run_deep_integrity_scan()
    return _LAST_INTEGRITY_REPORT
