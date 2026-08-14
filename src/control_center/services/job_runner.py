import os
import asyncio
import uuid
import time
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import logging
import traceback

from src.control_center.services import db_service, command_registry
from src.config import load_config

logger = logging.getLogger(__name__)

# In-memory tracking of the SINGLE active job
_ACTIVE_JOB = None
_ACTIVE_PROCESS = None
_JOB_SEQ = 0
_EVENT_LOCK = asyncio.Lock()

# Subscribers is a list of tuples: (asyncio.Queue, after_seq_when_subscribed)
_LOG_SUBSCRIBERS = {}  # job_id -> list of asyncio.Queue

def redact_secrets(text: str) -> str:
    # A simple centralized redaction helper
    try:
        config = load_config()
        token = config.secrets.bot_token
        if token and token != "YOUR_TELEGRAM_BOT_TOKEN":
            text = text.replace(token, "[REDACTED_BOT_TOKEN]")
    except Exception:
        pass
    return text

def recover_stale_jobs():
    """Recover jobs that were RUNNING when the server was previously shut down."""
    jobs = db_service.get_all_jobs()
    for job in jobs:
        if job["status"] == "RUNNING":
            job["status"] = "INTERRUPTED"
            job["error_summary"] = "Control Center restarted before job completion."
            job["finished_at"] = datetime.now(timezone.utc).isoformat()
            db_service.save_job(job)
            
            # Persist an interrupt event to the journal
            log_dir = Path("data/control_center_logs")
            events_path = log_dir / f"{job['id']}.events.jsonl"
            if events_path.parent.exists():
                seq = 1
                if events_path.exists():
                    with open(events_path, "r", encoding="utf-8") as f:
                        lines = f.read().splitlines()
                        if lines:
                            try:
                                last = json.loads(lines[-1])
                                seq = last.get("seq", 0) + 1
                            except:
                                pass
                
                event = {
                    "seq": seq,
                    "type": "job_status",
                    "status": "INTERRUPTED",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                with open(events_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event) + "\n")

async def _emit_event(job_id: str, event_data: dict, log_path: Path, events_path: Path):
    global _JOB_SEQ
    
    async with _EVENT_LOCK:
        _JOB_SEQ += 1
        event_data["seq"] = _JOB_SEQ
        
        # Redact any text fields
        for k, v in event_data.items():
            if isinstance(v, str):
                event_data[k] = redact_secrets(v)
                
        # 1. Persist to JSONL
        with open(events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_data) + "\n")
            f.flush()
            
        # 2. Persist to raw .log if it's a log event or important status
        with open(log_path, "a", encoding="utf-8") as f:
            if event_data["type"] == "log" and "text" in event_data:
                f.write(event_data["text"])
            elif event_data["type"] == "job_started":
                f.write(f"--- Job {job_id} started at {event_data.get('timestamp')} ---\n")
            elif event_data["type"] == "job_finished":
                f.write(f"\n--- Job {job_id} finished with exit code {event_data.get('exit_code')} ---\n")
            elif event_data["type"] == "error":
                f.write(f"\nInternal error: {event_data.get('message')}\n")
            f.flush()
            
        # 3. Publish to subscribers
        for q in _LOG_SUBSCRIBERS.get(job_id, []):
            try:
                q.put_nowait(event_data)
            except Exception:
                pass

def get_active_job_id() -> str | None:
    return _ACTIVE_JOB

async def start_job(profile_id: str) -> str:
    global _ACTIVE_JOB, _JOB_SEQ
    
    async with _EVENT_LOCK:
        if _ACTIVE_JOB is not None:
            raise ValueError("JOB_ALREADY_RUNNING")
            
        profile = command_registry.get_profile(profile_id)
        if not profile:
            raise ValueError("UNKNOWN_PROFILE")
            
        job_id = f"job-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        
        log_dir = Path("data/control_center_logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{job_id}.log"
        events_path = log_dir / f"{job_id}.events.jsonl"
        
        # Ensure fresh files
        if log_path.exists(): log_path.unlink()
        if events_path.exists(): events_path.unlink()
        
        job_dict = {
            "id": job_id,
            "profile_id": profile_id,
            "status": "RUNNING",
            "created_at": now,
            "started_at": now,
            "finished_at": None,
            "exit_code": None,
            "log_path": str(log_path),
            "events_path": str(events_path),
            "duration": None,
            "error_summary": None
        }
        
        db_service.save_job(job_dict)
        _ACTIVE_JOB = job_id
        _JOB_SEQ = 0
        _LOG_SUBSCRIBERS[job_id] = []
        
    # Run in background
    asyncio.create_task(_run_job(job_id, profile, log_path, events_path))
    return job_id

def _parse_pytest_line(line: str) -> dict | None:
    # Look for [ 31%] or [100%]
    match = re.search(r'\[\s*(\d+)%\]', line)
    if match:
        return {"type": "job_progress", "progress": int(match.group(1))}
    
    # Look for summary: 231 passed, 1 skipped, 3 warnings in 68.22s
    summary_match = re.search(r'((?:\d+\s+[a-z]+(?:,\s+)?)+)\s+in\s+([\d\.]+)s', line)
    if summary_match:
        parts = summary_match.group(1).split(",")
        summary = {"type": "job_summary", "duration_seconds": float(summary_match.group(2))}
        for p in parts:
            p = p.strip()
            if not p: continue
            count_str, state = p.split(" ", 1)
            summary[state.lower()] = int(count_str)
        return summary
    return None

async def _run_job(job_id: str, profile: dict, log_path: Path, events_path: Path):
    global _ACTIVE_JOB, _ACTIVE_PROCESS
    
    start_time = time.time()
    
    try:
        await _emit_event(job_id, {
            "type": "job_started",
            "profile_id": profile["id"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, log_path, events_path)
        
        # Subprocess
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONPATH"] = "."
        
        _ACTIVE_PROCESS = await asyncio.create_subprocess_exec(
            profile["executable"],
            *profile["args"],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            cwd="." # project root
        )
        
        async for line in _ACTIVE_PROCESS.stdout:
            line_str = line.decode("utf-8", errors="replace")
            
            # Emit raw log event
            await _emit_event(job_id, {
                "type": "log",
                "stream": "stdout",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "text": line_str
            }, log_path, events_path)
            
            # Optionally emit parsed progress event
            if profile["id"].startswith("pytest_"):
                parsed = _parse_pytest_line(line_str)
                if parsed:
                    parsed["timestamp"] = datetime.now(timezone.utc).isoformat()
                    await _emit_event(job_id, parsed, log_path, events_path)
                    
        await _ACTIVE_PROCESS.wait()
        exit_code = _ACTIVE_PROCESS.returncode
        
        status = "PASSED" if exit_code == 0 else "FAILED"
        if exit_code is not None and exit_code < 0:
            status = "CANCELLED"
            
        await _emit_event(job_id, {
            "type": "job_finished",
            "status": status,
            "exit_code": exit_code,
            "duration_seconds": time.time() - start_time,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, log_path, events_path)
            
    except Exception as e:
        exit_code = -1
        status = "FAILED"
        err = traceback.format_exc()
        await _emit_event(job_id, {
            "type": "error",
            "message": err,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, log_path, events_path)
        
        await _emit_event(job_id, {
            "type": "job_finished",
            "status": status,
            "exit_code": exit_code,
            "duration_seconds": time.time() - start_time,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, log_path, events_path)
    finally:
        end_time = time.time()
        
        job = db_service.get_job(job_id)
        if job:
            if job["status"] == "CANCELLED":
                status = "CANCELLED"
                
            job["status"] = status
            job["finished_at"] = datetime.now(timezone.utc).isoformat()
            job["exit_code"] = exit_code
            job["duration"] = end_time - start_time
            db_service.save_job(job)
            
        async with _EVENT_LOCK:
            if _ACTIVE_JOB == job_id:
                _ACTIVE_JOB = None
                _ACTIVE_PROCESS = None
                
            for q in _LOG_SUBSCRIBERS.get(job_id, []):
                try:
                    q.put_nowait(None) # Sentinel
                except:
                    pass
            _LOG_SUBSCRIBERS.pop(job_id, None)

def cancel_job(job_id: str):
    global _ACTIVE_JOB, _ACTIVE_PROCESS
    
    if _ACTIVE_JOB == job_id and _ACTIVE_PROCESS is not None:
        try:
            _ACTIVE_PROCESS.terminate()
            job = db_service.get_job(job_id)
            if job:
                job["status"] = "CANCELLED"
                db_service.save_job(job)
        except Exception as e:
            logger.error("Error terminating process: %s", e)

async def subscribe_log(job_id: str, after_seq: int) -> tuple[list[dict], asyncio.Queue]:
    """
    Returns (historical_events, live_queue).
    Uses _EVENT_LOCK to ensure no events are dropped between reading historical and subscribing.
    """
    historical = []
    q = asyncio.Queue()
    
    job = db_service.get_job(job_id)
    if not job:
        return [], q
        
    events_path = Path(f"data/control_center_logs/{job_id}.events.jsonl")
    
    async with _EVENT_LOCK:
        if events_path.exists():
            with open(events_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        ev = json.loads(line)
                        if ev.get("seq", 0) > after_seq:
                            historical.append(ev)
                    except:
                        pass
                        
        if job_id in _LOG_SUBSCRIBERS:
            _LOG_SUBSCRIBERS[job_id].append(q)
        else:
            q.put_nowait(None)
            
    return historical, q
