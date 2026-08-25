"""
Diagnostic Service for Control Center.
Executes 1-Click Full System Diagnostics and outputs timestamped JSON reports.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import load_config
from src.control_center.services import model_service, health_service, db_service

logger = logging.getLogger(__name__)

REPORTS_DIR = Path("data/diagnostic_reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def run_full_diagnostic() -> Dict[str, Any]:
    """Execute complete diagnostic suite and save JSON report."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"diagnostic_report_{ts}.json"
    report_path = REPORTS_DIR / report_filename

    results: Dict[str, Any] = {
        "report_id": f"diag-{ts}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "diagnostic_version": "2.0.0",
        "system": {
            "platform": platform.platform(),
            "python_version": sys.version,
            "python_executable": sys.executable,
            "working_directory": str(Path.cwd()),
        },
        "tests": []
    }

    # 1. Python & Dependencies Test
    deps_ok = True
    deps_details = []
    for pkg in ("fastapi", "uvicorn", "pydantic", "yaml", "PIL", "cv2", "onnxruntime", "httpx"):
        try:
            __import__(pkg)
            deps_details.append(f"{pkg}: installed")
        except ImportError as e:
            deps_ok = False
            deps_details.append(f"{pkg}: MISSING ({e})")
    
    results["tests"].append({
        "name": "Python Environment & Core Dependencies",
        "status": "PASSED" if deps_ok else "FAILED",
        "details": deps_details
    })

    # 2. Database Integrity Test
    try:
        config = load_config()
        db_path = Path(config.app.database_path)
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            pragma_res = conn.execute("PRAGMA integrity_check").fetchone()[0]
            media_cnt = conn.execute("SELECT COUNT(*) FROM media").fetchone()[0] if bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='media'").fetchone()) else 0
            conn.close()
            results["tests"].append({
                "name": "SQLite Archive Database Integrity",
                "status": "PASSED" if pragma_res == "ok" else "FAILED",
                "details": [f"Path: {db_path}", f"PRAGMA: {pragma_res}", f"Media Rows: {media_cnt}"]
            })
        else:
            results["tests"].append({
                "name": "SQLite Archive Database Integrity",
                "status": "WARNING",
                "details": [f"Database file not yet created at {db_path}"]
            })
    except Exception as e:
        results["tests"].append({
            "name": "SQLite Archive Database Integrity",
            "status": "FAILED",
            "details": [f"Error checking database: {e}"]
        })

    # 3. Model Signatures Test
    try:
        model_results = model_service.verify_models()
        all_models_valid = all(m.get("verified") for m in model_results)
        results["tests"].append({
            "name": "AI Model Signatures & Weights Verification",
            "status": "PASSED" if all_models_valid else "FAILED",
            "details": [f"{m['name']}: {m.get('status')} (SHA: {m.get('sha256_prefix', 'N/A')}...)" for m in model_results]
        })
    except Exception as e:
        results["tests"].append({
            "name": "AI Model Signatures & Weights Verification",
            "status": "FAILED",
            "details": [f"Model verification failed: {e}"]
        })

    # 4. Config Validation Test
    try:
        cfg = load_config()
        results["tests"].append({
            "name": "Configuration Validation",
            "status": "PASSED",
            "details": [
                f"Telegram Group: {cfg.telegram.group_id}",
                f"Topics configured: {list(cfg.telegram.topics.__dict__.keys()) if hasattr(cfg.telegram.topics, '__dict__') else 'Yes'}",
                f"Face Analysis: {'Enabled' if cfg.faces.enabled else 'Disabled'}",
                f"Scene Analysis: {'Enabled' if cfg.scenes.enabled else 'Disabled'}",
            ]
        })
    except Exception as e:
        results["tests"].append({
            "name": "Configuration Validation",
            "status": "FAILED",
            "details": [f"Config validation error: {e}"]
        })

    # 5. Queue Folders Write Test
    try:
        cfg = load_config()
        queue_checks = []
        queue_all_ok = True
        for name, folder_path in [
            ("incoming_images", cfg.queue.incoming_images),
            ("incoming_videos", cfg.queue.incoming_videos),
            ("completed", cfg.queue.completed),
            ("failed", cfg.queue.failed),
        ]:
            p = Path(folder_path)
            if p.exists():
                test_file = p / f".diag_write_test_{ts}.tmp"
                try:
                    test_file.write_text("test", encoding="utf-8")
                    test_file.unlink(missing_ok=True)
                    queue_checks.append(f"{name} ({p}): Accessible & Writable")
                except Exception as ex:
                    queue_all_ok = False
                    queue_checks.append(f"{name} ({p}): Write Permission Denied ({ex})")
            else:
                queue_all_ok = False
                queue_checks.append(f"{name} ({p}): Folder Missing")

        results["tests"].append({
            "name": "Queue Folders & File System Permissions",
            "status": "PASSED" if queue_all_ok else "WARNING",
            "details": queue_checks
        })
    except Exception as e:
        results["tests"].append({
            "name": "Queue Folders & File System Permissions",
            "status": "FAILED",
            "details": [f"Queue check failed: {e}"]
        })

    # 6. Disk Space Test
    try:
        total, used, free = shutil.disk_usage(Path.cwd())
        free_gb = free / (1024 ** 3)
        total_gb = total / (1024 ** 3)
        results["tests"].append({
            "name": "Disk Storage Space",
            "status": "PASSED" if free_gb > 5.0 else ("WARNING" if free_gb > 1.0 else "FAILED"),
            "details": [f"Total: {total_gb:.1f} GB", f"Free: {free_gb:.1f} GB"]
        })
    except Exception as e:
        results["tests"].append({
            "name": "Disk Storage Space",
            "status": "WARNING",
            "details": [f"Could not read disk space: {e}"]
        })

    # Overall summary
    has_failed = any(t["status"] == "FAILED" for t in results["tests"])
    has_warning = any(t["status"] == "WARNING" for t in results["tests"])
    results["overall_status"] = "FAILED" if has_failed else ("WARNING" if has_warning else "PASSED")

    # Save to disk
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    db_service.add_notification(
        level="SUCCESS" if not has_failed else "WARNING",
        title="Full Diagnostic Completed",
        message=f"System diagnostic check finished with status {results['overall_status']} ({len(results['tests'])} tests executed)."
    )

    results["filename"] = report_filename
    results["path"] = str(report_path)
    return results


def list_diagnostic_reports() -> List[Dict[str, Any]]:
    """List historical diagnostic reports."""
    if not REPORTS_DIR.exists():
        return []

    reports = []
    for f in sorted(REPORTS_DIR.glob("diagnostic_report_*.json"), reverse=True):
        try:
            with open(f, "r", encoding="utf-8") as rf:
                data = json.load(rf)
                reports.append({
                    "filename": f.name,
                    "report_id": data.get("report_id"),
                    "timestamp": data.get("timestamp"),
                    "overall_status": data.get("overall_status", "UNKNOWN"),
                    "test_count": len(data.get("tests", [])),
                    "size_bytes": f.stat().st_size
                })
        except Exception:
            pass

    return reports


def get_report_file_path(filename: str) -> Optional[Path]:
    p = REPORTS_DIR / Path(filename).name
    if p.exists() and p.is_file():
        return p
    return None
