import sqlite3
from pathlib import Path
import json

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
        conn.commit()

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

def get_job(job_id: str) -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row:
            return dict(row)
        return None

def get_all_jobs() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
