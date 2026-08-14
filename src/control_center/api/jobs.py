from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from typing import List
from src.control_center.schemas.jobs import JobSummary, JobCreateRequest, ApiError, CommandProfile
from src.control_center.services import db_service, job_runner, command_registry
import asyncio
from pathlib import Path

router = APIRouter()

@router.get("/jobs", response_model=List[JobSummary])
async def list_jobs():
    return db_service.get_all_jobs()

@router.get("/jobs/current", response_model=JobSummary | None)
async def get_current_job():
    job_id = job_runner.get_active_job_id()
    if job_id:
        return db_service.get_job(job_id)
    return None

@router.get("/jobs/profiles", response_model=List[CommandProfile])
async def list_profiles():
    return command_registry.get_all_profiles()

@router.post("/jobs/start", response_model=JobSummary)
async def start_job(req: JobCreateRequest):
    try:
        job_id = await job_runner.start_job(req.profile_id)
        return db_service.get_job(job_id)
    except ValueError as e:
        err = str(e)
        if err == "JOB_ALREADY_RUNNING":
            raise HTTPException(status_code=409, detail={"code": err, "message": "Another execution job is currently running."})
        elif err == "UNKNOWN_PROFILE":
            raise HTTPException(status_code=400, detail={"code": err, "message": "Unknown command profile."})
        raise HTTPException(status_code=500, detail={"code": "INTERNAL_ERROR", "message": err})

@router.post("/jobs/{job_id}/cancel", response_model=JobSummary)
async def cancel_job(job_id: str):
    job = db_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job["status"] == "RUNNING":
        job_runner.cancel_job(job_id)
        
    return db_service.get_job(job_id)

@router.get("/jobs/{job_id}/log")
async def get_job_log(job_id: str):
    job = db_service.get_job(job_id)
    if not job or not job.get("log_path"):
        raise HTTPException(status_code=404, detail="Job or log not found")
        
    path = Path(job["log_path"])
    if not path.exists():
        return ""
        
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

@router.websocket("/jobs/{job_id}/stream")
async def stream_job_log(websocket: WebSocket, job_id: str):
    # 1. Validate Origin
    origin = websocket.headers.get("origin", "")
    allowed_origins = [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://localhost:5173"
    ]
    if origin and origin not in allowed_origins:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    
    after_seq_str = websocket.query_params.get("after_seq", "0")
    try:
        after_seq = int(after_seq_str)
    except:
        after_seq = 0
        
    job = db_service.get_job(job_id)
    if not job:
        await websocket.close(code=1000)
        return

    # Subscribe safely
    historical, q = await job_runner.subscribe_log(job_id, after_seq)
    
    try:
        # Replay persisted events
        for ev in historical:
            await websocket.send_json(ev)
            
        # Drain live events
        while True:
            ev = await q.get()
            if ev is None:
                # Sentinel meaning job finished
                break
            await websocket.send_json(ev)
            
        # Close explicitly only because the server has finished its stream
        if websocket.client_state.name == "CONNECTED":
            await websocket.close(code=1000)
            
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        pass
    finally:
        # Client may disconnect at any time. Do NOT attempt to close unconditionally here.
        pass
