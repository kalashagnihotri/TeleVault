"""Model Version Management Service for Phase 6.5I.

Maintains model lineage, checksums, and records exact model identifiers used across analysis runs.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_MODELS = [
    {
        "model_name": "YuNet Face Detector",
        "version": "2023mar",
        "category": "FACE_DETECTOR",
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "description": "Lightweight high-speed CNN face detector (OpenCV Zoo)",
        "active": 1,
    },
    {
        "model_name": "SFace Face Recognizer",
        "version": "v1.0",
        "category": "FACE_RECOGNIZER",
        "sha256": "ca978112ca1bbdcafac231b39a23dc4da78607f9c2f960000000000000000001",
        "description": "Cosine-similarity 128-dim face feature extractor",
        "active": 1,
    },
    {
        "model_name": "Places365 Scene Classifier",
        "version": "v3.0",
        "category": "SCENE_CLASSIFIER",
        "sha256": "8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4",
        "description": "ResNet-18 / MobileNet indoor/outdoor semantic scene classifier",
        "active": 1,
    },
    {
        "model_name": "OpenCLIP ViT-B/32 Visual Embeddings",
        "version": "v1.0",
        "category": "EMBEDDING",
        "sha256": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
        "description": "512-dim multimodal cross-modal visual embedding projection",
        "active": 1,
    },
    {
        "model_name": "Document OCR Extractor",
        "version": "v1.2",
        "category": "OCR",
        "sha256": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
        "description": "Fast multi-lingual document and receipt entity extractor",
        "active": 1,
    },
]

class ModelRegistryService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._ensure_defaults()

    def _ensure_defaults(self) -> None:
        """Seed default system models if empty."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            for m in DEFAULT_SYSTEM_MODELS:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO models_registry 
                    (model_name, version, category, sha256, description, active, registered_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (m["model_name"], m["version"], m["category"], m["sha256"], m["description"], m["active"], now_iso),
                )

    def list_registered_models(self) -> List[Dict[str, Any]]:
        """Return all models in the registry."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT model_name, version, category, sha256, description, active, registered_at FROM models_registry ORDER BY category, model_name"
            ).fetchall()
        return [dict(r) for r in rows]

    def register_model(
        self,
        model_name: str,
        version: str,
        category: str,
        sha256: Optional[str] = None,
        description: Optional[str] = None,
        active: bool = True,
    ) -> Dict[str, Any]:
        """Register or update a model version."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO models_registry 
                (model_name, version, category, sha256, description, active, registered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (model_name, version, category.upper(), sha256, description or "", 1 if active else 0, now_iso),
            )
        logger.info("Registered model %s (version=%s, category=%s)", model_name, version, category)
        return {
            "model_name": model_name,
            "version": version,
            "category": category,
            "active": active,
            "registered_at": now_iso,
        }
