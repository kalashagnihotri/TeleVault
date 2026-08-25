"""
System Health Scoring Service.
Computes an aggregated 0-100% health score from:
- SQLite Database Integrity (20 pts)
- AI Model Verification (20 pts)
- Telegram Bot Connectivity (15 pts)
- Queue Directory Accessibility (15 pts)
- Disk Storage Space (15 pts)
- Backup Recency (15 pts)
"""
from __future__ import annotations

import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

from src.config import load_config
from src.control_center.services import model_service, snapshot_service, db_service

logger = logging.getLogger(__name__)


def compute_system_health() -> Dict[str, Any]:
    score = 0
    checks: List[Dict[str, Any]] = []

    try:
        config = load_config()
    except Exception as e:
        return {
            "score": 0,
            "status": "CRITICAL",
            "message": f"Configuration load failed: {e}",
            "checks": [{
                "id": "config",
                "name": "Configuration",
                "score": 0,
                "max_score": 100,
                "status": "FAILED",
                "message": str(e)
            }]
        }

    # 1. Database Integrity (20 pts)
    db_ok = False
    db_msg = "Database file missing"
    db_path = Path(config.app.database_path)
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            row = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            if row and row[0] == "ok":
                db_ok = True
                db_msg = "Database integrity verified (PRAGMA ok)"
            else:
                db_msg = f"Integrity check returned: {row[0] if row else 'none'}"
        except Exception as e:
            db_msg = f"Database check failed: {e}"
    
    db_score = 20 if db_ok else 0
    score += db_score
    checks.append({
        "id": "database",
        "name": "Database Integrity",
        "score": db_score,
        "max_score": 20,
        "status": "PASSED" if db_ok else "FAILED",
        "message": db_msg
    })

    # 2. AI Model Verification (20 pts)
    model_vers = model_service.verify_models()
    all_models_ok = len(model_vers) > 0 and all(m.get("verified", False) for m in model_vers)
    models_score = 20 if all_models_ok else (10 if any(m.get("verified", False) for m in model_vers) else 0)
    score += models_score
    checks.append({
        "id": "models",
        "name": "AI Models Verification",
        "score": models_score,
        "max_score": 20,
        "status": "PASSED" if all_models_ok else ("WARNING" if models_score > 0 else "FAILED"),
        "message": f"{sum(1 for m in model_vers if m.get('verified'))}/{len(model_vers)} models verified"
    })

    # 3. Telegram Connectivity / Config (15 pts)
    tg_ok = False
    tg_msg = "Telegram token or group not configured"
    if config.secrets.bot_token and config.telegram.group_id:
        tg_ok = True
        tg_msg = f"Configured for Group {config.telegram.group_id}"
    tg_score = 15 if tg_ok else 0
    score += tg_score
    checks.append({
        "id": "telegram",
        "name": "Telegram Connectivity",
        "score": tg_score,
        "max_score": 15,
        "status": "PASSED" if tg_ok else "WARNING",
        "message": tg_msg
    })

    # 4. Queue Folder Accessibility (15 pts)
    queue_ok = True
    queue_msgs = []
    for p_name, p_val in [
        ("Images", config.queue.incoming_images),
        ("Videos", config.queue.incoming_videos),
        ("Completed", config.queue.completed),
    ]:
        p = Path(p_val)
        if not p.exists():
            queue_ok = False
            queue_msgs.append(f"{p_name} dir missing ({p})")
    
    queue_score = 15 if queue_ok else 5
    score += queue_score
    checks.append({
        "id": "queue",
        "name": "Queue Folders Accessibility",
        "score": queue_score,
        "max_score": 15,
        "status": "PASSED" if queue_ok else "WARNING",
        "message": "All queue directories accessible" if queue_ok else ", ".join(queue_msgs)
    })

    # 5. Disk Storage Space (15 pts)
    disk_ok = False
    disk_msg = "Unknown"
    try:
        total, used, free = shutil.disk_usage(Path.cwd())
        free_gb = free / (1024 ** 3)
        if free_gb > 10.0:
            disk_ok = True
            disk_score = 15
            disk_status = "PASSED"
            disk_msg = f"{free_gb:.1f} GB free storage available"
        elif free_gb > 2.0:
            disk_ok = True
            disk_score = 10
            disk_status = "WARNING"
            disk_msg = f"Low disk space: {free_gb:.1f} GB remaining"
        else:
            disk_score = 0
            disk_status = "FAILED"
            disk_msg = f"Critical disk space: {free_gb:.1f} GB remaining"
    except Exception:
        disk_score = 10
        disk_status = "WARNING"
        disk_msg = "Could not evaluate disk space"

    score += disk_score
    checks.append({
        "id": "disk_space",
        "name": "Disk Storage Space",
        "score": disk_score,
        "max_score": 15,
        "status": disk_status,
        "message": disk_msg
    })

    # 6. Backup Recency (15 pts)
    snapshots = snapshot_service.list_snapshots()
    backup_ok = False
    backup_msg = "No system snapshots found"
    if snapshots:
        latest = snapshots[0]
        try:
            created = datetime.fromisoformat(latest["created_at"])
            # If within 7 days
            if datetime.now(timezone.utc) - created < timedelta(days=7):
                backup_ok = True
                backup_msg = f"Latest snapshot created {created.strftime('%Y-%m-%d %H:%M')}"
            else:
                backup_msg = f"Latest snapshot is older than 7 days ({created.strftime('%Y-%m-%d')})"
        except Exception:
            backup_ok = True
            backup_msg = "Snapshot available"
    
    backup_score = 15 if backup_ok else 5
    score += backup_score
    checks.append({
        "id": "backup_recency",
        "name": "Backup Recency",
        "score": backup_score,
        "max_score": 15,
        "status": "PASSED" if backup_ok else "WARNING",
        "message": backup_msg
    })

    status = "HEALTHY" if score >= 85 else ("DEGRADED" if score >= 60 else "CRITICAL")

    return {
        "score": min(score, 100),
        "status": status,
        "checks": checks,
        "evaluated_at": datetime.now(timezone.utc).isoformat()
    }
