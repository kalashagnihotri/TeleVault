from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

MediaType = Literal["image", "video", "other"]

@dataclass(slots=True)
class MetadataResult:
    date_taken: str | None = None
    has_gps: bool = False
    latitude: float | None = None
    longitude: float | None = None
    location_label: str = "Misc"

@dataclass(slots=True)
class MediaCandidate:
    path: Path
    media_type: MediaType
    size_bytes: int
    modified_ns: int
    sha256: str | None = None
    metadata: MetadataResult | None = None
    proposed_route: str | None = None
    media_id: int | None = None
    is_duplicate: bool = False

@dataclass(slots=True)
class RecognitionResult:
    people: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    confidence_reached: bool = False
@dataclass(slots=True)
class ImageFaceAnalysisResult:
    stage: str = "SUCCESS"
    error_code: str | None = None
    face_results: list[dict] = field(default_factory=list)
    accepted_faces: int = 0
    unknown_faces: int = 0
    raw_detections: int = 0
    accepted_size: int = 0
    ignored_tiny: int = 0
    processing_errors: int = 0
