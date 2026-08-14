import sys
import platform
import os
from pathlib import Path
from src.config import load_config, Config
from src.database import ArchiveDatabase
from src.control_center.schemas.system import (
    SystemHealthResponse,
    ControlCenterInfo,
    PythonInfo,
    ArchiveDbInfo,
    QueueInfo,
    FaceInfo,
    SceneInfo,
    TelegramInfo
)

def get_system_health() -> SystemHealthResponse:
    config = load_config()
    
    # Python
    py_info = PythonInfo(
        executable=sys.executable,
        version=platform.python_version()
    )
    
    # Archive DB
    db_path = Path(config.app.database_path)
    db_exists = db_path.exists()
    db_readable = False
    media_count = 0
    latest_mig = "unknown"
    
    if db_exists:
        try:
            db = ArchiveDatabase(db_path)
            db_readable = True
            with db.connect() as conn:
                media_count = conn.execute("SELECT COUNT(*) FROM media").fetchone()[0]
                mig = conn.execute("SELECT version FROM schema_migrations ORDER BY applied_at DESC LIMIT 1").fetchone()
                if mig:
                    latest_mig = mig[0]
        except Exception:
            pass
            
    db_info = ArchiveDbInfo(
        exists=db_exists,
        readable=db_readable,
        latest_migration=latest_mig,
        media_count=media_count,
        integrity_status=None
    )
    
    # Queue
    img_path = Path(config.queue.incoming_images)
    vid_path = Path(config.queue.incoming_videos)
    
    img_reachable = img_path.exists() and img_path.is_dir()
    vid_reachable = vid_path.exists() and vid_path.is_dir()
    
    q_info = QueueInfo(
        images_reachable=img_reachable,
        videos_reachable=vid_reachable,
        image_count=len(list(img_path.iterdir())) if img_reachable else 0,
        video_count=len(list(vid_path.iterdir())) if vid_reachable else 0
    )
    
    # Faces
    face_enabled = config.faces.enabled
    model_root = Path(config.faces.model_root)
    yunet_path = model_root / config.faces.detector_model
    sface_path = model_root / config.faces.recognizer_model
    models_present = yunet_path.exists() and sface_path.exists()
    
    # Determine calibration safely
    calibration = "UNKNOWN"
    if face_enabled:
        # Just check if representations exist
        rep_path = Path(config.faces.reference_root) / "representations"
        if rep_path.exists() and len(list(rep_path.glob("*.pkl"))) > 0:
            calibration = "CALIBRATED (ESTIMATED)"
        else:
            calibration = "NOT CALIBRATED"
            
    f_info = FaceInfo(
        enabled=face_enabled,
        models_present=models_present,
        calibration_status=calibration
    )
    
    # Scenes
    scene_enabled = config.scenes.enabled
    scene_model = Path(config.scenes.model_path)
    from src.scene_analysis import CURRENT_SCENE_ANALYSIS_VERSION
    s_info = SceneInfo(
        enabled=scene_enabled,
        model_present=scene_model.exists(),
        analysis_version=CURRENT_SCENE_ANALYSIS_VERSION
    )
    
    # Telegram
    t_info = TelegramInfo(
        configured=bool(config.secrets.bot_token and config.secrets.bot_token != "YOUR_TELEGRAM_BOT_TOKEN")
    )
    
    cc_info = ControlCenterInfo(
        backend_running=True,
        version="1.0.0"
    )
    
    return SystemHealthResponse(
        control_center=cc_info,
        python=py_info,
        archive_db=db_info,
        queue=q_info,
        faces=f_info,
        scenes=s_info,
        telegram=t_info
    )

def get_diagnostic_report() -> dict:
    health = get_system_health()
    report = health.model_dump()
    
    # Safe extra diagnostic info
    report["diagnostic_version"] = "1.0.0"
    
    from src.control_center.services import db_service
    recent_jobs = db_service.get_all_jobs()[:10]
    
    # ensure no secrets in error summaries
    safe_jobs = []
    for j in recent_jobs:
        sj = j.copy()
        if sj.get("log_path"): sj["log_path"] = "[REDACTED]"
        if sj.get("events_path"): sj["events_path"] = "[REDACTED]"
        safe_jobs.append(sj)
        
    report["recent_jobs"] = safe_jobs
    return report
