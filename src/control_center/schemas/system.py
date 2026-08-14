from pydantic import BaseModel
from typing import Optional

class HealthResponse(BaseModel):
    status: str

class ControlCenterInfo(BaseModel):
    backend_running: bool
    version: str

class PythonInfo(BaseModel):
    executable: str
    version: str

class ArchiveDbInfo(BaseModel):
    exists: bool
    readable: bool
    latest_migration: str
    media_count: int
    integrity_status: Optional[str]

class QueueInfo(BaseModel):
    images_reachable: bool
    videos_reachable: bool
    image_count: int
    video_count: int

class FaceInfo(BaseModel):
    enabled: bool
    models_present: bool
    calibration_status: str

class SceneInfo(BaseModel):
    enabled: bool
    model_present: bool
    analysis_version: int

class TelegramInfo(BaseModel):
    configured: bool

class SystemHealthResponse(BaseModel):
    control_center: ControlCenterInfo
    python: PythonInfo
    archive_db: ArchiveDbInfo
    queue: QueueInfo
    faces: FaceInfo
    scenes: SceneInfo
    telegram: TelegramInfo
