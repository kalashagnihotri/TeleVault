from fastapi import APIRouter
from src.control_center.schemas.dashboard import DashboardResponse, ArchiveStats, QueueStats
from src.config import load_config
from pathlib import Path
from src.database import ArchiveDatabase

router = APIRouter()

@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard():
    config = load_config()
    
    backed_up = 0
    ready = 0
    failed = 0
    
    db_path = Path(config.app.database_path)
    if db_path.exists():
        try:
            db = ArchiveDatabase(db_path)
            with db.connect() as conn:
                backed_up = conn.execute("SELECT COUNT(*) FROM media WHERE state = 'BACKED_UP'").fetchone()[0]
                ready = conn.execute("SELECT COUNT(*) FROM media WHERE state = 'READY_TO_UPLOAD'").fetchone()[0]
                
                # Check how many media have failed states
                failed = conn.execute("SELECT COUNT(*) FROM media WHERE face_state = 'FAILED' OR scene_state = 'FAILED'").fetchone()[0]
        except Exception:
            pass
            
    img_path = Path(config.queue.incoming_images)
    vid_path = Path(config.queue.incoming_videos)
    
    img_count = len(list(img_path.iterdir())) if img_path.exists() and img_path.is_dir() else 0
    vid_count = len(list(vid_path.iterdir())) if vid_path.exists() and vid_path.is_dir() else 0
    
    return DashboardResponse(
        archive=ArchiveStats(backed_up=backed_up, ready=ready, failed=failed),
        queue=QueueStats(incoming_images=img_count, incoming_videos=vid_count)
    )
