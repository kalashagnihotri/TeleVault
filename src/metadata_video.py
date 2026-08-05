from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.logging_utils import RuntimeOptions, log_private
from src.models import MetadataResult

logger = logging.getLogger(__name__)

def extract_video_metadata(path: Path, opts: Optional[RuntimeOptions] = None) -> MetadataResult:
    result = MetadataResult()
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(path)
        ]
        
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(proc.stdout)
        
        all_tags = {}
        
        format_tags = data.get("format", {}).get("tags", {})
        all_tags.update(format_tags)
        
        for stream in data.get("streams", []):
            all_tags.update(stream.get("tags", {}))
            
        # Date extraction
        creation_time = all_tags.get("creation_time")
        if creation_time:
            try:
                dt = datetime.fromisoformat(creation_time.replace("Z", "+00:00"))
                result.date_taken = dt.isoformat()
            except ValueError:
                pass
                
        # GPS extraction
        location_tags = {
            key: value
            for key, value in all_tags.items()
            if any(
                term in key.lower()
                for term in ("location", "gps", "iso6709")
            )
        }
        
        if location_tags:
            # Find the first one that matches ISO 6709 pattern
            for key, location_val in location_tags.items():
                match = re.match(r"([+-]\d+\.?\d*)([+-]\d+\.?\d*)", str(location_val))
                if match:
                    lat_str, lon_str = match.groups()
                    result.latitude = float(lat_str)
                    result.longitude = float(lon_str)
                    result.has_gps = True
                    break

    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Failed to extract video metadata using ffprobe: error=%s", type(e).__name__)
        if opts:
            log_private(logger, opts.verbose_private, "Failed to extract video metadata path=%r", str(path), exc_info=True)
    except Exception as e:
        logger.warning("Unexpected error extracting video metadata: error=%s", type(e).__name__)
        if opts:
            log_private(logger, opts.verbose_private, "Unexpected error extracting video metadata path=%r", str(path), exc_info=True)

    return result
