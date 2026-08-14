from pydantic import BaseModel
from typing import Optional, List

class CommandProfile(BaseModel):
    id: str
    display_name: str
    description: str
    risk_level: str
    category: str

class JobCreateRequest(BaseModel):
    profile_id: str

class JobSummary(BaseModel):
    id: str
    profile_id: str
    status: str
    created_at: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]
    exit_code: Optional[int]
    log_path: Optional[str]
    duration: Optional[float]
    error_summary: Optional[str]

class ApiError(BaseModel):
    code: str
    message: str
    details: Optional[str] = None
