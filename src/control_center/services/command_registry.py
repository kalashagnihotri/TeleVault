from typing import Dict, Optional, List
import sys
from src.control_center.schemas.jobs import CommandProfile

_PROFILES: Dict[str, dict] = {
    # ── Tests ──────────────────────────────────────────────────────────────
    "pytest_full": {
        "id": "pytest_full",
        "display_name": "Full Pytest Suite",
        "description": "Run the entire repository test suite safely.",
        "risk_level": "SAFE",
        "category": "TEST",
        "executable": sys.executable,
        "args": ["-m", "pytest", "-q"]
    },
    "pytest_face": {
        "id": "pytest_face",
        "display_name": "Face Tests",
        "description": "Run tests specifically for face analysis.",
        "risk_level": "SAFE",
        "category": "TEST",
        "executable": sys.executable,
        "args": ["-m", "pytest",
                 "tests/test_face_analysis_live.py",
                 "tests/test_face_analysis_dry_run.py",
                 "tests/test_face_routing.py",
                 "tests/test_face_routing_regression.py",
                 "tests/test_face_results.py",
                 "-q"]
    },
    "pytest_scene": {
        "id": "pytest_scene",
        "display_name": "Scene Tests",
        "description": "Run tests for scene and image heuristics.",
        "risk_level": "SAFE",
        "category": "TEST",
        "executable": sys.executable,
        "args": ["-m", "pytest",
                 "tests/test_scene_analysis.py",
                 "tests/test_image_heuristics.py",
                 "-q"]
    },
    "pytest_routing": {
        "id": "pytest_routing",
        "display_name": "Routing Tests",
        "description": "Run tests for routing and orchestration.",
        "risk_level": "SAFE",
        "category": "TEST",
        "executable": sys.executable,
        "args": ["-m", "pytest",
                 "tests/test_routing.py",
                 "tests/test_orchestration_routing.py",
                 "-q"]
    },
    "pytest_control_center": {
        "id": "pytest_control_center",
        "display_name": "Control Center Tests",
        "description": "Run backend unit tests for Control Center.",
        "risk_level": "SAFE",
        "category": "TEST",
        "executable": sys.executable,
        "args": ["-m", "pytest", "tests/test_control_center.py", "-q"]
    },

    # ── Pipeline ────────────────────────────────────────────────────────────
    "pipeline_dry_run": {
        "id": "pipeline_dry_run",
        "display_name": "Dry Run Pipeline",
        "description": "Run the archive pipeline in DRY RUN mode. Scans queue, executes face/scene detection, checks routing, with zero DB writes and zero Telegram uploads.",
        "risk_level": "CONTROLLED",
        "category": "PIPELINE",
        "executable": sys.executable,
        "args": ["-m", "src.control_center.pipeline_runner", "--mode", "dry_run"]
    },
    "pipeline_live": {
        "id": "pipeline_live",
        "display_name": "Live Pipeline Run",
        "description": "Execute the live archive pipeline against Incoming queue. Media is hashed, analyzed, uploaded to Telegram, and recorded as BACKED_UP. (Cleanup is forced OFF).",
        "risk_level": "LIVE",
        "category": "PIPELINE",
        "executable": sys.executable,
        "args": ["-m", "src.control_center.pipeline_runner", "--mode", "live"]
    },

    # ── Live / Telegram ─────────────────────────────────────────────────────
    "telegram_smoke_test": {
        "id": "telegram_smoke_test",
        "display_name": "Telegram Smoke Test",
        "description": "Send a verified test message to the configured Telegram group to validate bot token and permissions.",
        "risk_level": "CONTROLLED",
        "category": "LIVE",
        "executable": sys.executable,
        "args": ["-c",
            "import asyncio, httpx, sys\n"
            "from src.config import load_config\n"
            "async def run():\n"
            "    c = load_config()\n"
            "    token = c.secrets.bot_token\n"
            "    gid = c.telegram.group_id\n"
            "    if not token:\n"
            "        print('Smoke test FAILED: No bot token configured.')\n"
            "        return 1\n"
            "    url = f'https://api.telegram.org/bot{token}/sendMessage'\n"
            "    try:\n"
            "        async with httpx.AsyncClient(timeout=10.0) as client:\n"
            "            r = await client.post(url, json={'chat_id': gid, 'text': '[Control Center Smoke Test] Verification message OK'})\n"
            "            d = r.json()\n"
            "            if d.get('ok'):\n"
            "                msg_id = d['result']['message_id']\n"
            "                print(f'Telegram Smoke Test PASSED: message_id={msg_id}, group_id={gid}')\n"
            "                return 0\n"
            "            else:\n"
            "                desc = d.get('description', 'Unknown error')\n"
            "                print(f'Telegram Smoke Test FAILED: {desc}')\n"
            "                return 1\n"
            "    except Exception as e:\n"
            "        print(f'Telegram Smoke Test FAILED: {type(e).__name__}: {e}')\n"
            "        return 1\n"
            "sys.exit(asyncio.run(run()))"
        ]
    },

    # ── Maintenance & DB ─────────────────────────────────────────────────────
    "cleanup_preview": {
        "id": "cleanup_preview",
        "display_name": "Cleanup Preview",
        "description": "Read-only inspection of eligible cleanup candidates according to safety delay and verification rules. No files are moved or deleted.",
        "risk_level": "CONTROLLED",
        "category": "MAINTENANCE",
        "executable": sys.executable,
        "args": ["-m", "src.control_center.pipeline_runner", "--mode", "cleanup_preview"]
    },
    "db_backup": {
        "id": "db_backup",
        "display_name": "Backup Database",
        "description": "Create an atomic, verified SQLite backup using sqlite3.Connection.backup() into data/db_backups/.",
        "risk_level": "SAFE",
        "category": "MAINTENANCE",
        "executable": sys.executable,
        "args": ["-c",
            "import sqlite3, sys\n"
            "from pathlib import Path\n"
            "from datetime import datetime, timezone\n"
            "from src.config import load_config\n"
            "c = load_config()\n"
            "src_path = Path(c.app.database_path)\n"
            "if not src_path.exists():\n"
            "    print(f'Backup FAILED: Source database {src_path} does not exist.')\n"
            "    sys.exit(1)\n"
            "backup_dir = Path('data/db_backups')\n"
            "backup_dir.mkdir(parents=True, exist_ok=True)\n"
            "ts = datetime.now().strftime('%Y%m%d_%H%M%S')\n"
            "dest_path = backup_dir / f'archive_backup_{ts}.sqlite3'\n"
            "src_conn = sqlite3.connect(str(src_path))\n"
            "dest_conn = sqlite3.connect(str(dest_path))\n"
            "try:\n"
            "    src_conn.backup(dest_conn)\n"
            "    dest_conn.close()\n"
            "    src_conn.close()\n"
            "    chk_conn = sqlite3.connect(str(dest_path))\n"
            "    integrity = chk_conn.execute('PRAGMA integrity_check').fetchone()[0]\n"
            "    has_media = bool(chk_conn.execute(\"SELECT 1 FROM sqlite_master WHERE type='table' AND name='media'\").fetchone())\n"
            "    media_count = chk_conn.execute('SELECT COUNT(*) FROM media').fetchone()[0] if has_media else 0\n"
            "    chk_conn.close()\n"
            "    size = dest_path.stat().st_size\n"
            "    print('=== Database Backup Summary ===')\n"
            "    print(f'Filename:     {dest_path.name}')\n"
            "    print(f'Location:     {dest_path}')\n"
            "    print(f'File Size:    {size} bytes')\n"
            "    print(f'Integrity:    {integrity}')\n"
            "    print(f'Media Rows:   {media_count}')\n"
            "    print(f'Timestamp:    {datetime.now(timezone.utc).isoformat()}')\n"
            "    if integrity != 'ok':\n"
            "        print('Backup FAILED integrity check!')\n"
            "        sys.exit(1)\n"
            "    print('Backup completed successfully.')\n"
            "except Exception as e:\n"
            "    print(f'Backup FAILED: {type(e).__name__}: {e}')\n"
            "    sys.exit(1)"
        ]
    },
    "db_integrity": {
        "id": "db_integrity",
        "display_name": "DB Integrity Check",
        "description": "Run PRAGMA integrity_check on the archive database.",
        "risk_level": "SAFE",
        "category": "READ-ONLY",
        "executable": sys.executable,
        "args": ["-c",
            "import sqlite3; from src.config import load_config; "
            "c = load_config(); db = sqlite3.connect(c.app.database_path); "
            "print(f'Integrity result: {db.execute(\"PRAGMA integrity_check\").fetchone()[0]}'); "
            "r = db.execute('SELECT state, COUNT(*) FROM media GROUP BY state').fetchall() if db.execute(\"SELECT 1 FROM sqlite_master WHERE type='table' AND name='media'\").fetchone() else []; "
            "[print(f'  {s}: {n}') for s,n in r]"
        ]
    },
    "db_stats": {
        "id": "db_stats",
        "display_name": "Archive Stats",
        "description": "Print a summary of the archive database — counts by status, recent activity.",
        "risk_level": "SAFE",
        "category": "READ-ONLY",
        "executable": sys.executable,
        "args": ["-c",
            "import sqlite3; from src.config import load_config; "
            "c = load_config(); db = sqlite3.connect(c.app.database_path); "
            "has_media = bool(db.execute(\"SELECT 1 FROM sqlite_master WHERE type='table' AND name='media'\").fetchone()); "
            "rows = db.execute('SELECT state, COUNT(*) as n FROM media GROUP BY state ORDER BY n DESC').fetchall() if has_media else []; "
            "print('=== Archive Status Counts ==='); "
            "[print(f'  {s}: {n}') for s, n in rows]; "
            "total = db.execute('SELECT COUNT(*) FROM media').fetchone()[0] if has_media else 0; "
            "print(f'  TOTAL: {total}'); "
            "recent = db.execute('SELECT short_hash, original_filename, state, updated_at FROM media ORDER BY updated_at DESC LIMIT 5').fetchall() if has_media else []; "
            "print(); print('=== Recent Media ==='); "
            "[print(f'  [{r[0][:8] if r[0] else \"\"}] {r[1]} ({r[2]}) at {r[3]}') for r in recent]"
        ]
    },
    "queue_inspect": {
        "id": "queue_inspect",
        "display_name": "Inspect Queue",
        "description": "List files currently in Incoming paths.",
        "risk_level": "SAFE",
        "category": "READ-ONLY",
        "executable": sys.executable,
        "args": ["-c",
            "from pathlib import Path; from src.config import load_config; "
            "c = load_config(); "
            "imgs = [f for f in Path(c.queue.incoming_images).glob('*') if f.is_file() and not f.name.startswith('.')]; "
            "vids = [f for f in Path(c.queue.incoming_videos).glob('*') if f.is_file() and not f.name.startswith('.')]; "
            "print(f'Images: {len(imgs)}'); "
            "[print(f'  {f.name} ({f.stat().st_size} bytes)') for f in imgs[:10]]; "
            "print(f'Videos: {len(vids)}'); "
            "[print(f'  {f.name} ({f.stat().st_size} bytes)') for f in vids[:10]]"
        ]
    },
    "system_diagnostics": {
        "id": "system_diagnostics",
        "display_name": "System Diagnostics",
        "description": "Check system health — Python version, config, DB path, face/scene model presence.",
        "risk_level": "SAFE",
        "category": "DIAGNOSTICS",
        "executable": sys.executable,
        "args": ["-c",
            "import sys, os; from pathlib import Path; "
            "print(f'Python: {sys.version}'); "
            "from src.config import load_config; c = load_config(); "
            "print(f'DB Path: {c.app.database_path}'); "
            "print(f'DB exists: {Path(c.app.database_path).exists()}'); "
            "print(f'Telegram configured: {bool(c.secrets.bot_token)}'); "
            "print(f'Faces enabled: {c.faces.enabled}'); "
            "face_det = Path(c.faces.model_root) / c.faces.detector_model; "
            "face_rec = Path(c.faces.model_root) / c.faces.recognizer_model; "
            "print(f'Face detector model: {face_det.exists()}'); "
            "print(f'Face recognizer model: {face_rec.exists()}'); "
            "scene_model = Path(c.scenes.model_path); "
            "print(f'Scene model: {scene_model.exists()}'); "
            "imgs = [f for f in Path(c.queue.incoming_images).glob('*') if f.is_file() and not f.name.startswith('.')]; "
            "vids = [f for f in Path(c.queue.incoming_videos).glob('*') if f.is_file() and not f.name.startswith('.')]; "
            "print(f'Queue images: {len(imgs)}, videos: {len(vids)}')"
        ]
    },
}


def get_profile(profile_id: str) -> Optional[dict]:
    return _PROFILES.get(profile_id)


def get_all_profiles() -> List[CommandProfile]:
    return [
        CommandProfile(
            id=v["id"],
            display_name=v["display_name"],
            description=v["description"],
            risk_level=v["risk_level"],
            category=v["category"]
        ) for v in _PROFILES.values()
    ]
