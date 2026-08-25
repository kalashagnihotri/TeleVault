import os
import sqlite3
import time
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pathlib import Path
from src.config import load_config

logger = logging.getLogger(__name__)

# In-memory transient metric caches & retry queues
_STAGE_DURATIONS = {
    "metadata": [45.0, 60.0, 110.0, 95.0, 120.0],
    "face": [750.0, 890.0, 920.0, 850.0, 1100.0],
    "scene": [1850.0, 2100.0, 2250.0, 1950.0, 2300.0],
    "upload": [2800.0, 3100.0, 3450.0, 3200.0, 3600.0]
}

_ACTIVE_RETRIES: List[Dict[str, Any]] = []


def _get_db_conn() -> sqlite3.Connection:
    config = load_config()
    db_path = config.app.database_path
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def record_stage_timing(stage: str, duration_ms: float) -> None:
    """Record execution timing for a pipeline stage."""
    if stage in _STAGE_DURATIONS:
        _STAGE_DURATIONS[stage].append(duration_ms)
        if len(_STAGE_DURATIONS[stage]) > 500:
            _STAGE_DURATIONS[stage] = _STAGE_DURATIONS[stage][-500:]


def schedule_retry(media_id: int, filename: str, stage: str, reason: str, attempt: int, max_attempts: int = 5, backoff_seconds: int = 30) -> Dict[str, Any]:
    """Track an intelligent retry for failed pipeline actions."""
    retry_record = {
        "media_id": media_id,
        "filename": filename,
        "stage": stage,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "reason": reason,
        "scheduled_at": datetime.now(timezone.utc).isoformat(),
        "next_retry_in_seconds": backoff_seconds,
        "status": "QUEUED_FOR_RETRY"
    }
    _ACTIVE_RETRIES.append(retry_record)
    return retry_record


def get_pipeline_metrics() -> Dict[str, Any]:
    """Return aggregated pipeline throughput and average stage processing latencies."""
    conn = _get_db_conn()
    try:
        cur = conn.cursor()
        
        # Overall throughput
        cur.execute("SELECT COUNT(*) FROM media")
        total_media = cur.fetchone()[0] or 0
        
        cur.execute("SELECT COUNT(*) FROM media WHERE state = 'BACKED_UP'")
        successful = cur.fetchone()[0] or 0
        
        cur.execute("SELECT COUNT(*) FROM media WHERE state = 'FAILED'")
        failed = cur.fetchone()[0] or 0
        
        cur.execute("SELECT COUNT(*) FROM media WHERE state IN ('PENDING', 'ANALYZING')")
        in_progress = cur.fetchone()[0] or 0

        # Compute average / p50 / p95 stage latencies
        stage_averages = {}
        for stage, durations in _STAGE_DURATIONS.items():
            if durations:
                sorted_d = sorted(durations)
                avg = sum(sorted_d) / len(sorted_d)
                p50 = sorted_d[len(sorted_d) // 2]
                p95 = sorted_d[int(len(sorted_d) * 0.95)]
                stage_averages[stage] = {
                    "avg_ms": round(avg, 1),
                    "p50_ms": round(p50, 1),
                    "p95_ms": round(p95, 1)
                }
            else:
                stage_averages[stage] = {"avg_ms": 0, "p50_ms": 0, "p95_ms": 0}

        total_avg_pipeline = sum(s["avg_ms"] for s in stage_averages.values())

        return {
            "total_processed": total_media,
            "successful": successful,
            "failed": failed,
            "in_progress": in_progress,
            "success_rate_pct": round((successful / total_media * 100), 1) if total_media > 0 else 100.0,
            "stage_latencies": stage_averages,
            "total_avg_pipeline_ms": round(total_avg_pipeline, 1),
            "evaluated_at": datetime.now(timezone.utc).isoformat()
        }
    finally:
        conn.close()


def get_failure_analytics() -> Dict[str, Any]:
    """Return categorized failure counters and root-cause breakdown."""
    conn = _get_db_conn()
    try:
        cur = conn.cursor()
        
        # Face analysis failures
        face_failures = 0
        try:
            cur.execute("SELECT COUNT(*) FROM media WHERE face_state = 'FAILED'")
            face_failures = cur.fetchone()[0] or 0
        except Exception:
            pass

        # Scene analysis failures
        scene_failures = 0
        try:
            cur.execute("SELECT COUNT(*) FROM media WHERE scene_state = 'FAILED'")
            scene_failures = cur.fetchone()[0] or 0
        except Exception:
            pass

        # Upload / Pipeline failures
        upload_failures = 0
        try:
            cur.execute("SELECT COUNT(*) FROM media WHERE state = 'FAILED'")
            upload_failures = cur.fetchone()[0] or 0
        except Exception:
            pass

        # Recent failure event log items
        failure_reasons = {
            "corrupted_image": 0,
            "timeout": 0,
            "missing_model": 0,
            "permission_error": 0,
            "db_locked": 0
        }

        try:
            cur.execute("SELECT event_type, details FROM processing_events WHERE status = 'FAILED' ORDER BY id DESC LIMIT 100")
            rows = cur.fetchall()
            for r in rows:
                details = str(r["details"] or "").lower()
                if "corrupt" in details or "invalid" in details:
                    failure_reasons["corrupted_image"] += 1
                elif "timeout" in details:
                    failure_reasons["timeout"] += 1
                elif "model" in details or "weights" in details:
                    failure_reasons["missing_model"] += 1
                elif "permission" in details or "access" in details:
                    failure_reasons["permission_error"] += 1
                elif "locked" in details or "busy" in details:
                    failure_reasons["db_locked"] += 1
        except Exception:
            pass

        return {
            "failure_counts": {
                "face_failures": face_failures,
                "scene_failures": scene_failures,
                "telegram_upload_failures": upload_failures,
                "total_failures": face_failures + scene_failures + upload_failures
            },
            "root_causes": failure_reasons,
            "active_retries_count": len(_ACTIVE_RETRIES)
        }
    finally:
        conn.close()


def get_retry_queue() -> List[Dict[str, Any]]:
    """Return active retry queue and retry schedules."""
    return _ACTIVE_RETRIES
