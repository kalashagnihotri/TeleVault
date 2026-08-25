import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from uuid import uuid4

DB_PATH = Path("data/control_center.sqlite3")

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    if not DB_PATH.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS control_center_schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                profile_id TEXT,
                status TEXT,
                created_at TEXT,
                started_at TEXT,
                finished_at TEXT,
                exit_code INTEGER,
                log_path TEXT,
                duration REAL,
                error_summary TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS imports (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                sha256 TEXT,
                size_bytes INTEGER,
                media_type TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                destination TEXT,
                error_code TEXT,
                error_message TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY,
                level TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                read INTEGER NOT NULL DEFAULT 0
            )
        """)

        # Default system mode to "safe" if not set
        row = conn.execute("SELECT value FROM settings WHERE key = 'system_mode'").fetchone()
        if not row:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("INSERT INTO settings (key, value, updated_at) VALUES ('system_mode', 'safe', ?)", (now,))

        conn.commit()


# ── Jobs ───────────────────────────────────────────────────────────────────

def save_job(job_dict: dict):
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO jobs (
                id, profile_id, status, created_at, started_at, finished_at, exit_code, log_path, duration, error_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_dict["id"],
            job_dict["profile_id"],
            job_dict["status"],
            job_dict.get("created_at"),
            job_dict.get("started_at"),
            job_dict.get("finished_at"),
            job_dict.get("exit_code"),
            job_dict.get("log_path"),
            job_dict.get("duration"),
            job_dict.get("error_summary")
        ))
        conn.commit()

def get_job(job_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row:
            return dict(row)
        return None

def get_all_jobs() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


# ── Imports ────────────────────────────────────────────────────────────────

def save_import(import_dict: dict):
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO imports (
                id, filename, original_filename, sha256, size_bytes, media_type,
                status, created_at, completed_at, destination, error_code, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            import_dict["id"],
            import_dict["filename"],
            import_dict["original_filename"],
            import_dict.get("sha256"),
            import_dict.get("size_bytes"),
            import_dict.get("media_type"),
            import_dict["status"],
            import_dict["created_at"],
            import_dict.get("completed_at"),
            import_dict.get("destination"),
            import_dict.get("error_code"),
            import_dict.get("error_message")
        ))
        conn.commit()

def get_all_imports(limit: int = 50, offset: int = 0) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM imports ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
        return [dict(r) for r in rows]

def get_import(import_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM imports WHERE id = ?", (import_id,)).fetchone()
        if row:
            return dict(row)
        return None


# ── System Settings / Safe Mode ────────────────────────────────────────────

def get_system_mode() -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'system_mode'").fetchone()
        return row["value"] if row else "safe"

def set_system_mode(mode: str) -> str:
    valid_mode = "production" if mode.lower() == "production" else "safe"
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('system_mode', ?, ?)",
            (valid_mode, now)
        )
        conn.commit()
    return valid_mode


# ── Notifications ──────────────────────────────────────────────────────────

def add_notification(level: str, title: str, message: str) -> dict:
    nid = f"notif-{uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO notifications (id, level, title, message, created_at, read) VALUES (?, ?, ?, ?, ?, 0)",
            (nid, level, title, message, now)
        )
        conn.commit()
    return {
        "id": nid,
        "level": level,
        "title": title,
        "message": message,
        "created_at": now,
        "read": 0
    }

def get_notifications(limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

def mark_notification_read(notification_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute("UPDATE notifications SET read = 1 WHERE id = ?", (notification_id,))
        conn.commit()
        return cursor.rowcount > 0

def mark_all_notifications_read() -> int:
    with get_connection() as conn:
        cursor = conn.execute("UPDATE notifications SET read = 1 WHERE read = 0")
        conn.commit()
        return cursor.rowcount
