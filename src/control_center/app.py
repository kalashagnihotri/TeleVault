import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import logging

from src.control_center.api import health, system, dashboard, jobs

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure logs and local db dirs exist
    os.makedirs("data/control_center_logs", exist_ok=True)
    from src.control_center.services.db_service import init_db
    init_db()
    
    # Recover stale running jobs
    from src.control_center.services import job_runner
    job_runner.recover_stale_jobs()
    
    logger.info("Control Center backend started.")
    yield
    # Shutdown
    logger.info("Control Center backend shutting down.")

app = FastAPI(
    title="Telegram Media Archive - Control Center",
    description="Local Admin API",
    version="1.0.0",
    lifespan=lifespan
)

# Restrict CORS to explicit localhost for Vite dev server and self
origins = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:5173",  # typical Vite port
    "http://localhost:5173",
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

# Serve UI if it exists
UI_DIR = Path("ui/dist")

# Serve UI if it exists

if UI_DIR.exists() and UI_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=UI_DIR / "assets"), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Fallback to index.html for React Router, unless it's a direct file hit
        file_path = UI_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(UI_DIR / "index.html")
else:
    @app.get("/")
    async def fallback_ui():
        return {"message": "Control Center API is running, but UI build (ui/dist) is missing. Start Vite dev server for UI."}
