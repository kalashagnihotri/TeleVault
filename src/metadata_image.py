from __future__ import annotations

import logging
from src.logging_utils import RuntimeOptions, log_private
from datetime import datetime
from pathlib import Path

from PIL import Image, ExifTags

from src.models import MetadataResult

logger = logging.getLogger(__name__)

def ratio_to_float(value):
    try:
        return float(value)
    except Exception:
        return None

def dms_to_decimal(values, reference):
    try:
        degrees = ratio_to_float(values[0])
        minutes = ratio_to_float(values[1])
        seconds = ratio_to_float(values[2])

        if None in (degrees, minutes, seconds):
            return None

        result = degrees + minutes / 60 + seconds / 3600

        if str(reference).upper() in {"S", "W"}:
            result = -result

        return result
    except Exception:
        return None

def extract_image_metadata(path: Path, opts: Optional[RuntimeOptions] = None) -> MetadataResult:
    result = MetadataResult()
    try:
        with Image.open(path) as image:
            exif = image.getexif()

            if not exif:
                return result

            # Try to get date
            date_taken = (
                exif.get(36867)
                or exif.get(36868)
                or exif.get(306)
            )

            if date_taken:
                try:
                    # Typical EXIF format: "YYYY:MM:DD HH:MM:SS"
                    dt = datetime.strptime(str(date_taken).strip(), "%Y:%m:%d %H:%M:%S")
                    result.date_taken = dt.isoformat()
                except ValueError:
                    pass

            try:
                gps_ifd = exif.get_ifd(34853)
            except Exception:
                gps_ifd = {}

            if gps_ifd:
                gps = {
                    ExifTags.GPSTAGS.get(key, key): value
                    for key, value in gps_ifd.items()
                }

                lat_values = gps.get("GPSLatitude")
                lat_ref = gps.get("GPSLatitudeRef")
                lon_values = gps.get("GPSLongitude")
                lon_ref = gps.get("GPSLongitudeRef")

                latitude = dms_to_decimal(lat_values, lat_ref) if lat_values else None
                longitude = dms_to_decimal(lon_values, lon_ref) if lon_values else None

                if latitude is not None and longitude is not None:
                    result.latitude = latitude
                    result.longitude = longitude
                    result.has_gps = True

    except Exception as e:
        logger.warning("Failed to extract image metadata: error=%s", type(e).__name__)
        if opts:
            log_private(logger, opts.verbose_private, "Failed to extract image metadata path=%r", str(path), exc_info=True)

    return result
