from typing import Dict, Optional, List
import sys
from src.control_center.schemas.jobs import CommandProfile

_PROFILES: Dict[str, dict] = {
    "pytest_full": {
        "id": "pytest_full",
        "display_name": "Full Pytest Suite",
        "description": "Run the entire existing repository test suite safely.",
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
        "args": ["-m", "pytest", "tests/test_face_analysis_live.py", "tests/test_face_analysis_dry_run.py", "tests/test_face_routing.py", "tests/test_face_routing_regression.py", "tests/test_face_results.py", "-q"]
    },
    "pytest_scene": {
        "id": "pytest_scene",
        "display_name": "Scene Tests",
        "description": "Run tests for scene and image heuristics.",
        "risk_level": "SAFE",
        "category": "TEST",
        "executable": sys.executable,
        "args": ["-m", "pytest", "tests/test_scene_analysis.py", "tests/test_image_heuristics.py", "-q"]
    },
    "pytest_routing": {
        "id": "pytest_routing",
        "display_name": "Routing Tests",
        "description": "Run tests for routing and orchestration.",
        "risk_level": "SAFE",
        "category": "TEST",
        "executable": sys.executable,
        "args": ["-m", "pytest", "tests/test_routing.py", "tests/test_orchestration_routing.py", "-q"]
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
    "db_integrity": {
        "id": "db_integrity",
        "display_name": "DB Integrity Check",
        "description": "Run PRAGMA integrity_check safely.",
        "risk_level": "SAFE",
        "category": "READ-ONLY",
        "executable": sys.executable,
        "args": ["-c", "import sqlite3; from src.config import load_config; c = load_config(); db = sqlite3.connect(c.app.database_path); print(f'Integrity result: {db.execute(\"PRAGMA integrity_check\").fetchone()[0]}')"]
    },
    "queue_inspect": {
        "id": "queue_inspect",
        "display_name": "Inspect Queue",
        "description": "List files currently in Incoming paths.",
        "risk_level": "SAFE",
        "category": "READ-ONLY",
        "executable": sys.executable,
        "args": ["-c", "import os; from pathlib import Path; from src.config import load_config; c = load_config(); print(f'Images: {len(list(Path(c.queue.incoming_images).glob(\"*\")))}'); print(f'Videos: {len(list(Path(c.queue.incoming_videos).glob(\"*\")))}')"]
    },
    "system_diagnostics": {
        "id": "system_diagnostics",
        "display_name": "System Diagnostics",
        "description": "Check system health safely.",
        "risk_level": "SAFE",
        "category": "DIAGNOSTICS",
        "executable": sys.executable,
        "args": ["-c", "import sys; print(f'Python: {sys.version}'); from src.config import load_config; c=load_config(); print(f'Config loaded'); print(f'DB Path: {c.app.database_path}')"]
    }
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
