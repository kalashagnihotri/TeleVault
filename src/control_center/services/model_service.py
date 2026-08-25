"""
AI Model Service for Control Center.
Manages model discovery, SHA-256 integrity verification, and synthetic benchmark testing.
"""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np

logger = logging.getLogger(__name__)

MODELS_REGISTRY = [
    {
        "id": "face_detector_yunet",
        "name": "YuNet Face Detector",
        "category": "FACE",
        "path": "private_data/faces/models/face_detection_yunet_2023mar.onnx",
        "version": "2023mar",
        "expected_sha_prefix": "8f2383e4",
        "backend": "OpenCV DNN (YuNet)",
        "description": "High-performance lightweight face detector for 16px-1024px faces."
    },
    {
        "id": "face_recognizer_sface",
        "name": "SFace Face Recognizer",
        "category": "FACE",
        "path": "private_data/faces/models/face_recognition_sface_2021dec.onnx",
        "version": "2021dec",
        "expected_sha_prefix": "0ba9fbfa",
        "backend": "OpenCV DNN (SFace)",
        "description": "128-dimensional deep metric embedding generator for cosine face recognition."
    },
    {
        "id": "scene_classifier_places365",
        "name": "Places365 Scene Classifier",
        "category": "SCENE",
        "path": "private_data/scenes/models/resnet18_places365.onnx",
        "version": "ResNet18-v3",
        "expected_sha_prefix": None,
        "backend": "ONNX Runtime",
        "description": "Places365 neural network classifier recognizing 365 scene categories."
    }
]


def _compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def get_models_status() -> List[Dict[str, Any]]:
    """Return status, file size, and existence for all registered models."""
    results: List[Dict[str, Any]] = []

    for item in MODELS_REGISTRY:
        p = Path(item["path"])
        exists = p.exists() and p.is_file()
        size_bytes = p.stat().st_size if exists else 0
        status = "READY" if exists else "MISSING"

        results.append({
            "id": item["id"],
            "name": item["name"],
            "category": item["category"],
            "path": item["path"],
            "version": item["version"],
            "backend": item["backend"],
            "description": item["description"],
            "exists": exists,
            "status": status,
            "size_bytes": size_bytes,
            "expected_sha_prefix": item["expected_sha_prefix"],
        })

    return results


def verify_models() -> List[Dict[str, Any]]:
    """Verify SHA-256 hashes of all models against registry signatures."""
    results: List[Dict[str, Any]] = []

    for item in MODELS_REGISTRY:
        p = Path(item["path"])
        exists = p.exists() and p.is_file()
        if not exists:
            results.append({
                "id": item["id"],
                "name": item["name"],
                "status": "MISSING",
                "verified": False,
                "error": "Model file not found on disk."
            })
            continue

        sha256 = _compute_sha256(p)
        expected_prefix = item["expected_sha_prefix"]
        verified = True
        if expected_prefix:
            verified = sha256.startswith(expected_prefix)

        results.append({
            "id": item["id"],
            "name": item["name"],
            "sha256": sha256,
            "sha256_prefix": sha256[:8],
            "expected_prefix": expected_prefix,
            "verified": verified,
            "status": "VERIFIED" if verified else "HASH_MISMATCH"
        })

    return results


def benchmark_model(model_id: str) -> Dict[str, Any]:
    """Run synthetic tensor forward pass to benchmark model inference latency."""
    model_def = next((m for m in MODELS_REGISTRY if m["id"] == model_id), None)
    if not model_def:
        raise ValueError(f"Unknown model ID: {model_id}")

    p = Path(model_def["path"])
    if not p.exists():
        raise FileNotFoundError(f"Model file {p} not found.")

    t0 = time.perf_counter()

    if model_id == "face_detector_yunet":
        import cv2
        detector = cv2.FaceDetectorYN.create(
            str(p), "", (300, 300), score_threshold=0.85, nms_threshold=0.3, top_k=5000
        )
        dummy_img = np.zeros((300, 300, 3), dtype=np.uint8)
        # Warmup + Benchmark
        detector.detect(dummy_img)
        t_start = time.perf_counter()
        for _ in range(5):
            detector.detect(dummy_img)
        t_end = time.perf_counter()
        avg_ms = round(((t_end - t_start) / 5) * 1000, 2)

    elif model_id == "face_recognizer_sface":
        import cv2
        recognizer = cv2.FaceRecognizerSF.create(str(p), "")
        dummy_face = np.zeros((112, 112, 3), dtype=np.uint8)
        # Warmup + Benchmark
        recognizer.feature(dummy_face)
        t_start = time.perf_counter()
        for _ in range(5):
            recognizer.feature(dummy_face)
        t_end = time.perf_counter()
        avg_ms = round(((t_end - t_start) / 5) * 1000, 2)

    elif model_id == "scene_classifier_places365":
        import onnxruntime as ort
        session = ort.InferenceSession(str(p), providers=["CPUExecutionProvider"])
        input_name = session.get_inputs()[0].name
        dummy_tensor = np.zeros((1, 3, 224, 224), dtype=np.float32)
        session.run(None, {input_name: dummy_tensor})
        t_start = time.perf_counter()
        for _ in range(5):
            session.run(None, {input_name: dummy_tensor})
        t_end = time.perf_counter()
        avg_ms = round(((t_end - t_start) / 5) * 1000, 2)

    else:
        avg_ms = 0.0

    return {
        "id": model_id,
        "name": model_def["name"],
        "latency_ms": avg_ms,
        "status": "PASSED",
        "benchmark_iterations": 5,
        "timestamp": time.time()
    }
