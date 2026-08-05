from __future__ import annotations

import logging
from enum import Enum
from dataclasses import dataclass

@dataclass(frozen=True)
class RuntimeOptions:
    verbose_private: bool = False

class ProcessingStage(str, Enum):
    HASH = "HASH"
    DECODE = "DECODE"
    METADATA = "METADATA"
    FACE_DETECTION = "FACE_DETECTION"
    FACE_ALIGNMENT = "FACE_ALIGNMENT"
    FACE_EMBEDDING = "FACE_EMBEDDING"
    FACE_MATCHING = "FACE_MATCHING"
    UPLOAD = "UPLOAD"
    CLEANUP = "CLEANUP"

def safe_candidate_id(
    content_hash: str | None,
    *,
    fallback_number: int | None = None,
) -> str:
    if content_hash:
        normalized = content_hash.strip().lower()

        if len(normalized) >= 8:
            return normalized[:8]

    if fallback_number is not None:
        return f"unhashed-{fallback_number:04d}"

    return "unhashed"

def log_private(
    logger: logging.Logger,
    enabled: bool,
    message: str,
    *args: object,
    exc_info: bool = False,
) -> None:
    if not enabled:
        return

    logger.debug(
        message,
        *args,
        exc_info=exc_info,
    )
