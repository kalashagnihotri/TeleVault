from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config import FaceConfig

CURRENT_ANALYSIS_VERSION = 5

def get_face_size_tier(width: int, height: int, config: FaceConfig) -> str:
    min_side = min(width, height)
    if min_side < config.low_resolution_min_face_size_px:
        return "IGNORED_TINY"
    if min_side < config.minimum_face_size_px:
        return "LOW_RESOLUTION_CANDIDATE"
    return "ACCEPTED_NORMAL_SIZE"
