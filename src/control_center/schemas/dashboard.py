from pydantic import BaseModel

class ArchiveStats(BaseModel):
    backed_up: int
    ready: int
    failed: int

class QueueStats(BaseModel):
    incoming_images: int
    incoming_videos: int

class DashboardResponse(BaseModel):
    archive: ArchiveStats
    queue: QueueStats
