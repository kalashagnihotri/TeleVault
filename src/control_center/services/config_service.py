"""
Config Service for Control Center (Phase 6.5C).
Provides safe, validated configuration reading, updating, and rollbacks.
Never exposes or overwrites secrets in .env.
"""
from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from src.config import load_config, ConfigError

logger = logging.getLogger(__name__)

CONFIG_PATH = Path("config/config.yaml")
BACKUP_DIR = Path("data/config_backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def get_active_config() -> Dict[str, Any]:
    """Read the active YAML configuration from disk as a dict."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Configuration file not found at {CONFIG_PATH}")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return data


def validate_config(config_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate an in-memory configuration dictionary against system requirements.
    Returns (is_valid, list_of_errors).
    """
    errors: List[str] = []

    if not isinstance(config_dict, dict):
        return False, ["Configuration payload must be a JSON/YAML object"]

    # 1. Telegram
    tg = config_dict.get("telegram", {})
    if not isinstance(tg, dict):
        errors.append("`telegram` section must be a dictionary")
    else:
        if not tg.get("group_id"):
            errors.append("`telegram.group_id` is required")
        topics = tg.get("topics", {})
        if not isinstance(topics, dict):
            errors.append("`telegram.topics` must be a dictionary")
        else:
            for required_topic in ("people", "family_groups", "travel_nature", "everyday", "screenshots_documents", "videos", "misc"):
                val = topics.get(required_topic)
                if val is None:
                    errors.append(f"`telegram.topics.{required_topic}` is required")
                elif not isinstance(val, (int, str)) or (isinstance(val, str) and not val.isdigit()):
                    errors.append(f"`telegram.topics.{required_topic}` must be an integer topic thread ID")

    # 2. Faces
    fc = config_dict.get("faces", {})
    if not isinstance(fc, dict):
        errors.append("`faces` section must be a dictionary")
    else:
        conf = fc.get("detector_confidence")
        if conf is not None and not (0.0 <= float(conf) <= 1.0):
            errors.append("`faces.detector_confidence` must be between 0.0 and 1.0")
        min_size = fc.get("minimum_face_size_px")
        if min_size is not None and int(min_size) < 16:
            errors.append("`faces.minimum_face_size_px` must be at least 16 pixels")

    # 3. Scenes
    sc = config_dict.get("scenes", {})
    if not isinstance(sc, dict):
        errors.append("`scenes` section must be a dictionary")
    else:
        conf = sc.get("minimum_confidence")
        if conf is not None and not (0.0 <= float(conf) <= 1.0):
            errors.append("`scenes.minimum_confidence` must be between 0.0 and 1.0")

    # 4. Cleanup
    cl = config_dict.get("cleanup", {})
    if not isinstance(cl, dict):
        errors.append("`cleanup` section must be a dictionary")
    else:
        mode = cl.get("mode")
        if mode and mode not in ("move", "delete"):
            errors.append("`cleanup.mode` must be 'move' or 'delete'")
        days = cl.get("backup_safety_days")
        if days is not None and int(days) < 0:
            errors.append("`cleanup.backup_safety_days` cannot be negative")

    # 5. Queue
    qu = config_dict.get("queue", {})
    if not isinstance(qu, dict):
        errors.append("`queue` section must be a dictionary")

    return len(errors) == 0, errors


def backup_config() -> Path:
    """Create a timestamped backup of the current config.yaml."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Cannot backup non-existent config file {CONFIG_PATH}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"config_backup_{ts}.yaml"
    shutil.copy2(CONFIG_PATH, backup_file)
    logger.info("Configuration backed up to %s", backup_file)
    return backup_file


def save_config(config_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate, backup, and atomically update config/config.yaml."""
    valid, errors = validate_config(config_dict)
    if not valid:
        return False, errors

    try:
        # Create backup first
        backup_path = backup_config()

        # Write to temporary file in same directory for atomic replace
        temp_path = CONFIG_PATH.parent / f".{CONFIG_PATH.name}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_dict, f, default_flow_style=False, sort_keys=False)

        os.replace(temp_path, CONFIG_PATH)
        logger.info("Configuration updated successfully. Backup saved at %s", backup_path)
        return True, []
    except Exception as e:
        logger.error("Failed to save configuration: %s", e)
        return False, [f"Save failed: {e}"]


def list_backups() -> List[Dict[str, Any]]:
    """List available configuration backups."""
    if not BACKUP_DIR.exists():
        return []

    backups: List[Dict[str, Any]] = []
    for f in sorted(BACKUP_DIR.glob("config_backup_*.yaml"), reverse=True):
        try:
            st = f.stat()
            backups.append({
                "filename": f.name,
                "path": str(f),
                "size_bytes": st.st_size,
                "created_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
            })
        except Exception:
            pass

    return backups


def restore_backup(filename: str) -> bool:
    """Restore configuration from a backup file."""
    backup_file = BACKUP_DIR / filename
    if not backup_file.exists() or not backup_file.is_file():
        raise FileNotFoundError(f"Backup file not found: {filename}")

    # Backup current before restoring
    backup_config()
    shutil.copy2(backup_file, CONFIG_PATH)
    logger.info("Configuration restored from %s", backup_file)
    return True


def compute_config_diff(new_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compute structured property-by-property differences between active and new config."""
    old_config = get_active_config()
    diffs: List[Dict[str, Any]] = []

    def _compare(old: Any, new: Any, path: str):
        if isinstance(old, dict) and isinstance(new, dict):
            all_keys = sorted(set(old.keys()) | set(new.keys()))
            for k in all_keys:
                sub_path = f"{path}.{k}" if path else k
                if k not in old:
                    diffs.append({
                        "path": sub_path,
                        "key": k,
                        "old_value": None,
                        "new_value": new[k],
                        "change_type": "ADDED"
                    })
                elif k not in new:
                    diffs.append({
                        "path": sub_path,
                        "key": k,
                        "old_value": old[k],
                        "new_value": None,
                        "change_type": "REMOVED"
                    })
                else:
                    _compare(old[k], new[k], sub_path)
        else:
            if old != new:
                diffs.append({
                    "path": path,
                    "key": path.split(".")[-1] if "." in path else path,
                    "old_value": old,
                    "new_value": new,
                    "change_type": "MODIFIED"
                })

    _compare(old_config, new_config, "")
    return diffs

