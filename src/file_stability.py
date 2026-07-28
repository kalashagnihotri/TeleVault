from __future__ import annotations

import time
from pathlib import Path

TEMP_SUFFIXES = {".tmp", ".part", ".crdownload"}

def is_supported_candidate(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() not in TEMP_SUFFIXES


