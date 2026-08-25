"""Worker Coordinator Manager (Phase 6.5G Pillar 11)

Coordinates distributed multi-machine worker nodes and reports system fleet status.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.workers.face_worker import FaceWorker
from src.workers.scene_worker import SceneWorker
from src.workers.upload_worker import UploadWorker

logger = logging.getLogger(__name__)

_FACE_WORKER = FaceWorker("face_worker_local")
_SCENE_WORKER = SceneWorker("scene_worker_local")
_UPLOAD_WORKER = UploadWorker("upload_worker_local")


def get_worker_fleet_status() -> Dict[str, Any]:
    """Return status of all registered worker nodes in the cluster."""
    workers = [
        _FACE_WORKER.get_status(),
        _SCENE_WORKER.get_status(),
        _UPLOAD_WORKER.get_status()
    ]
    return {
        "cluster_status": "ONLINE",
        "total_workers": len(workers),
        "workers": workers
    }
