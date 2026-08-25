"""
Diagnostics & Health API Endpoints for Control Center.
"""
from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.control_center.services import health_service, diagnostic_service

router = APIRouter()


class HealthCheckItem(BaseModel):
    id: str
    name: str
    score: int
    max_score: int
    status: str
    message: str


class SystemHealthResponse(BaseModel):
    score: int
    status: str
    checks: List[HealthCheckItem]
    evaluated_at: str


@router.get("/system/health_score", response_model=SystemHealthResponse)
def get_system_health_score():
    """Return aggregated 0-100% system health score and component breakdown."""
    return health_service.compute_system_health()


@router.post("/system/run_diagnostic")
def execute_full_diagnostic():
    """Run comprehensive 1-click system diagnostic and return results."""
    try:
        return diagnostic_service.run_full_diagnostic()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Diagnostic run failed: {e}")


@router.get("/system/diagnostic_reports")
def list_diagnostic_reports():
    """List historical diagnostic reports."""
    return diagnostic_service.list_diagnostic_reports()


@router.get("/system/diagnostic_reports/{filename}/download")
def download_diagnostic_report(filename: str):
    """Download a diagnostic report JSON file."""
    path = diagnostic_service.get_report_file_path(filename)
    if not path:
        raise HTTPException(status_code=404, detail="Diagnostic report file not found.")
    return FileResponse(
        path=path,
        media_type="application/json",
        filename=filename
    )


@router.get("/system/security_audit")
def get_security_audit():
    """Audit logs, diagnostics, and configurations for potential secret leaks."""
    from src.control_center.services import security_service
    try:
        return security_service.audit_secrets_in_logs_and_diagnostics()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

