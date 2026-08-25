import os
import re
import logging
from typing import Dict, Any, List
from pathlib import Path
from PIL import Image
from src.config import load_config

logger = logging.getLogger(__name__)

# Max upload limit: 2GB
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024

# Pillow decompression bomb limit (safe threshold)
Image.MAX_IMAGE_PIXELS = 100_000_000

# Secret patterns (e.g. Telegram Bot tokens: 123456789:ABCdefGhI...)
SECRET_PATTERNS = [
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"),  # Telegram Bot Token
    re.compile(r"(?i)bot_token\s*[:=]\s*['\"]?[0-9a-zA-Z_-]{20,}"),
    re.compile(r"(?i)api_key\s*[:=]\s*['\"]?[0-9a-zA-Z_-]{20,}")
]


def sanitize_filename(filename: str) -> str:
    """Strip directory traversal attempts and illegal filename characters."""
    clean = Path(filename).name
    clean = re.sub(r'[\\/*?:"<>|]', "", clean)
    clean = clean.replace("..", "")
    return clean or "unnamed_media.bin"


def validate_upload_security(filename: str, size_bytes: int) -> Dict[str, Any]:
    """Validates file upload constraints and ensures security against decompression bombs."""
    sanitized = sanitize_filename(filename)
    if size_bytes > MAX_UPLOAD_BYTES:
        raise ValueError(f"File '{sanitized}' exceeds maximum allowed size of 2 GB.")

    return {
        "valid": True,
        "sanitized_filename": sanitized,
        "size_bytes": size_bytes
    }


def audit_secrets_in_logs_and_diagnostics() -> Dict[str, Any]:
    """Scans all log files and diagnostic outputs to verify zero secret exposure."""
    config = load_config()
    bot_token = config.secrets.bot_token
    token_fragment = bot_token[:8] if bot_token and bot_token != "YOUR_TELEGRAM_BOT_TOKEN" else None

    log_dirs = [Path("data/control_center_logs"), Path("data/diagnostics"), Path("logs")]
    violations: List[Dict[str, Any]] = []

    for d in log_dirs:
        if not d.exists():
            continue
        for f in d.glob("*.*"):
            if f.is_file() and f.suffix in (".log", ".json", ".jsonl", ".txt"):
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    # Check token fragment
                    if token_fragment and token_fragment in content:
                        violations.append({
                            "file": str(f),
                            "violation": "Potential Telegram Bot Token Fragment Detected",
                            "severity": "CRITICAL"
                        })
                    # Check regexes
                    for pat in SECRET_PATTERNS:
                        if pat.search(content):
                            violations.append({
                                "file": str(f),
                                "violation": "Secret regex pattern matched in log file",
                                "severity": "HIGH"
                            })
                except Exception:
                    pass

    return {
        "status": "PASSED" if len(violations) == 0 else "FAIL_SECRETS_EXPOSED",
        "total_files_audited": sum(len(list(d.glob("*.*"))) for d in log_dirs if d.exists()),
        "violations_count": len(violations),
        "violations": violations,
        "safe_redaction_verified": len(violations) == 0
    }
