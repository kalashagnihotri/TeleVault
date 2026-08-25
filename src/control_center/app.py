import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import logging

from src.control_center.api import (
    health, system, dashboard, jobs, ingestion, archive, config, 
    models, maintenance, diagnostics, metrics, integrity, faces_scenes, media_delivery,
    feedback_audit, automation, deduplication, portable_archive, memory_evaluation,
    production_intelligence, production_reliability, personal_ai, architecture_evolution
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure logs and local db dirs exist
    os.makedirs("data/control_center_logs", exist_ok=True)
    from src.control_center.services.db_service import init_db
    init_db()

    # Ensure archive db is migrated
    try:
        from src.database import ArchiveDatabase
        from src.config import load_config
        c = load_config()
        sql_dir = Path("sql")
        if sql_dir.exists():
            ArchiveDatabase(c.app.database_path).apply_migrations(sql_dir)
    except Exception as e:
        logger.warning("Failed to auto-migrate archive db on startup: %s", e)
    
    # Recover stale running jobs
    from src.control_center.services import job_runner
    job_runner.recover_stale_jobs()
    
    logger.info("Control Center backend started.")
    yield
    logger.info("Control Center backend shutting down.")

app = FastAPI(
    title="Telegram Media Archive - Control Center",
    description="Local Admin API",
    version="1.0.0",
    lifespan=lifespan
)

origins = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:5174",
    "http://localhost:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(health.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(ingestion.router, prefix="/api")
app.include_router(archive.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(models.router, prefix="/api")
app.include_router(maintenance.router, prefix="/api")
app.include_router(diagnostics.router, prefix="/api")
app.include_router(metrics.router, prefix="/api")
app.include_router(integrity.router, prefix="/api")
app.include_router(faces_scenes.router, prefix="/api")
app.include_router(media_delivery.router, prefix="/api")
app.include_router(feedback_audit.router)
app.include_router(automation.router)
app.include_router(deduplication.router)
app.include_router(portable_archive.router)
app.include_router(memory_evaluation.router)
app.include_router(production_intelligence.router)
app.include_router(production_reliability.router)
app.include_router(personal_ai.router)
app.include_router(architecture_evolution.router)

# Serve UI if it exists
UI_DIR = Path("ui/dist")

if UI_DIR.exists() and UI_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=UI_DIR / "assets"), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = UI_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(UI_DIR / "index.html")
else:
    @app.get("/")
    async def fallback_ui():
        return {"message": "Control Center API is running, but UI build (ui/dist) is missing. Start Vite dev server for UI."}
