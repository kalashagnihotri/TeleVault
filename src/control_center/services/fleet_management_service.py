"""Distributed Worker Fleet Management Service (Phase 6.5H Pillar 9)

Tracks multi-machine worker nodes, capabilities (GPU Face/Scene vs Uploaders),
heartbeats, and task assignment statuses.
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


def register_worker_heartbeat(
    worker_id: str,
    node_name: str,
    ip_address: Optional[str] = None,
    capabilities: Optional[List[str]] = None,
    status: str = "ONLINE",
    current_job_id: Optional[str] = None,
    tasks_processed_delta: int = 0
) -> Dict[str, Any]:
    """Register or update a worker node's heartbeat in the fleet registry."""
    conn = _get_db_conn()
    now_iso = datetime.now(timezone.utc).isoformat()
    caps_json = json.dumps(capabilities or ["face", "scene", "upload"])

    try:
        with conn:
            conn.execute(
                """
                INSERT INTO worker_nodes 
                (worker_id, node_name, ip_address, capabilities_json, status, last_heartbeat_at, current_job_id, processed_tasks_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(worker_id) DO UPDATE SET
                    node_name = excluded.node_name,
                    ip_address = COALESCE(excluded.ip_address, worker_nodes.ip_address),
                    capabilities_json = excluded.capabilities_json,
                    status = excluded.status,
                    last_heartbeat_at = excluded.last_heartbeat_at,
                    current_job_id = excluded.current_job_id,
                    processed_tasks_count = worker_nodes.processed_tasks_count + ?
                """,
                (
                    worker_id,
                    node_name,
                    ip_address or "127.0.0.1",
                    caps_json,
                    status,
                    now_iso,
                    current_job_id,
                    tasks_processed_delta,
                    tasks_processed_delta
                )
            )

        return {
            "success": True,
            "worker_id": worker_id,
            "node_name": node_name,
            "status": status,
            "last_heartbeat_at": now_iso
        }
    finally:
        conn.close()


def get_fleet_status() -> Dict[str, Any]:
    """Return all active worker nodes in the fleet."""
    conn = _get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM worker_nodes ORDER BY last_heartbeat_at DESC")
        rows = cur.fetchall()

        nodes: List[Dict[str, Any]] = []
        for r in rows:
            nodes.append({
                "worker_id": r["worker_id"],
                "node_name": r["node_name"],
                "ip_address": r["ip_address"],
                "capabilities": json.loads(r["capabilities_json"] or "[]"),
                "status": r["status"],
                "last_heartbeat_at": r["last_heartbeat_at"],
                "current_job_id": r["current_job_id"],
                "processed_tasks_count": r["processed_tasks_count"]
            })

        return {
            "total_nodes": len(nodes),
            "online_nodes_count": sum(1 for n in nodes if n["status"] == "ONLINE"),
            "nodes": nodes
        }
    finally:
        conn.close()
