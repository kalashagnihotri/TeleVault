"""Portable Archive Export API Router (Phase 6.5G Pillar 10)"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.control_center.services.portable_archive_service import export_portable_archive_bundle

router = APIRouter(prefix="/api/portable_archive", tags=["Portable Archive"])


@router.post("/export")
def post_export_portable_archive() -> Dict[str, Any]:
    try:
        return export_portable_archive_bundle()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{filename}")
def get_download_bundle(filename: str):
    file_path = Path("data/exports") / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archive bundle file not found.")
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/zip"
    )
