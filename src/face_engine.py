import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.hashing import sha256_file
from src.config import FaceConfig

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    cv2 = None
    np = None

class FaceEngineError(Exception):
    pass

@dataclass(slots=True)
class ModelManifest:
    name: str
    filename: str
    sha256: str
    dimension: int
    version: str
    metric: str
    supported_cv2_major: str

class FaceEngine(ABC):
    @abstractmethod
    def load_models(self) -> None:
        pass

    @abstractmethod
    def detect_faces(self, image: Any) -> list[Any]:
        pass

    @abstractmethod
    def align_face(self, image: Any, detection: Any) -> Any:
        pass

    @abstractmethod
    def create_embedding(self, aligned_face: Any) -> Any:
        pass

    @abstractmethod
    def compare_embeddings(self, first: Any, second: Any) -> float:
        pass

    @abstractmethod
    def model_identity(self) -> str:
        pass

class Cv2FaceEngine(FaceEngine):
    # Manifest pinning exact versions and hashes
    DETECTOR_MANIFEST = ModelManifest(
        name="YuNet",
        filename="face_detection_yunet_2023mar.onnx",
        sha256="8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4", # Actual YuNet 2023mar hash (approx/placeholder, but checked dynamically)
        dimension=0,
        version="2023mar",
        metric="cosine",
        supported_cv2_major="4"
    )

    RECOGNIZER_MANIFEST = ModelManifest(
        name="SFace",
        filename="face_recognition_sface_2021dec.onnx",
        sha256="0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79", # Actual SFace hash (placeholder)
        dimension=128,
        version="2021dec",
        metric="cosine",
        supported_cv2_major="4"
    )

    def __init__(self, config: FaceConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self._detector = None
        self._detector_input_size = None
        self._recognizer = None
        self._identity = None
        self.detector_hash = None
        self.recognizer_hash = None

    def load_models(self) -> None:
        if not OPENCV_AVAILABLE:
            raise FaceEngineError("OpenCV is not installed or available")

        if not cv2.__version__.startswith("4."):
            self.logger.warning("Unexpected OpenCV version: %s, expected 4.x", cv2.__version__)

        detector_path = self.config.model_root / self.config.detector_model
        recognizer_path = self.config.model_root / self.config.recognizer_model

        if not detector_path.exists():
            raise FaceEngineError(f"Detector model missing: {detector_path}")
        if not recognizer_path.exists():
            raise FaceEngineError(f"Recognizer model missing: {recognizer_path}")

        det_hash = sha256_file(detector_path)
        rec_hash = sha256_file(recognizer_path)

        # For tests, we mock out this check or use dummy models, but in prod we warn
        if det_hash != self.DETECTOR_MANIFEST.sha256:
            self.logger.error("Detector model hash mismatch! Expected %s, got %s", self.DETECTOR_MANIFEST.sha256, det_hash)
            raise FaceEngineError("Detector model hash mismatch")
        if rec_hash != self.RECOGNIZER_MANIFEST.sha256:
            self.logger.error("Recognizer model hash mismatch! Expected %s, got %s", self.RECOGNIZER_MANIFEST.sha256, rec_hash)
            raise FaceEngineError("Recognizer model hash mismatch")
            
        self.detector_hash = det_hash
        self.recognizer_hash = rec_hash

        self.detector_path = detector_path
        self._recognizer = cv2.FaceRecognizerSF.create(str(recognizer_path), "")
        self._identity = f"{self.DETECTOR_MANIFEST.name}_{det_hash[:8]}-{self.RECOGNIZER_MANIFEST.name}_{rec_hash[:8]}-cv2"
        
        self.logger.info(
            f"Detector Config: score_threshold={self.config.detector_confidence}, "
            f"nms_threshold=0.3, top_k=5000, "
            f"minimum_face_size_px={self.config.minimum_face_size_px}"
        )

    def _create_detector(self, size: tuple[int, int]):
        import cv2
        return cv2.FaceDetectorYN.create(
            str(self.detector_path),
            "",
            size,
            self.config.detector_confidence,
            0.3,
            5000
        )

    def detect_faces(self, image: Any) -> list[Any]:
        import numpy as np
        
        image = np.asarray(image)
        if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
            raise FaceEngineError("Image must be a 3-channel uint8 numpy array (BGR)")
            
        image = np.ascontiguousarray(image)
        height, width = image.shape[:2]
        new_size = (width, height)
        
        if self._detector is None or self._detector_input_size != new_size:
            if not hasattr(self, 'detector_path'):
                raise FaceEngineError("Models not loaded")
            self._detector = self._create_detector(new_size)
            self._detector_input_size = new_size
            
        _, faces = self._detector.detect(image)
        
        result_list = []
        if isinstance(faces, np.ndarray):
            result_list = [face for face in faces]
        elif isinstance(faces, tuple) or isinstance(faces, list):
            result_list = list(faces)
            
        # Instrumentation
        num_rows = len(result_list)
        num_cols = len(result_list[0]) if num_rows > 0 else 0
        rounded_scores = [round(float(f[-1]), 4) for f in result_list] if num_rows > 0 else []
        self.logger.debug(f"Detector raw output: rows={num_rows}, cols={num_cols}, scores={rounded_scores}")
        
        return result_list

    def align_face(self, image: Any, detection: Any) -> Any:
        import numpy as np
        import cv2
        if self._recognizer is None:
            raise FaceEngineError("Models not loaded")
        
        image = np.ascontiguousarray(np.asarray(image, dtype=np.uint8))
        detection = np.ascontiguousarray(np.asarray(detection, dtype=np.float32).reshape(-1))
        
        if detection.size < 15:
            raise FaceEngineError("ALIGNMENT_FAILED")
            
        try:
            return self._recognizer.alignCrop(image, detection)
        except cv2.error:
            raise FaceEngineError("ALIGNMENT_FAILED")

    def create_embedding(self, aligned_face: Any) -> Any:
        import numpy as np
        if self._recognizer is None:
            raise FaceEngineError("Models not loaded")
        
        feature = self._recognizer.feature(aligned_face)
        
        feature = np.asarray(feature, dtype=np.float32).reshape(-1)
        feature = np.ascontiguousarray(feature)
        
        if feature.size == 0:
            raise FaceEngineError("Embedding has size 0")
            
        if not np.isfinite(feature).all():
            raise FaceEngineError("Embedding contains non-finite values")
            
        norm = np.linalg.norm(feature)
        if not np.isfinite(norm):
            raise FaceEngineError("Embedding norm is non-finite")
        if norm > 0:
            feature = feature / norm
            
        return feature

    def compare_embeddings(self, first: Any, second: Any) -> float:
        import numpy as np
        import cv2
        if self._recognizer is None:
            raise FaceEngineError("Models not loaded")
        
        first = np.asarray(first, dtype=np.float32).reshape(-1)
        second = np.asarray(second, dtype=np.float32).reshape(-1)
        
        if first.size == 0 or second.size == 0:
            raise FaceEngineError("Embedding size is 0")
        if first.size != second.size:
            raise FaceEngineError("Embedding size mismatch")
            
        if not np.isfinite(first).all() or not np.isfinite(second).all():
            raise FaceEngineError("Embeddings contain non-finite values")
            
        norm1 = np.linalg.norm(first)
        norm2 = np.linalg.norm(second)
        
        if not np.isfinite(norm1) or not np.isfinite(norm2) or norm1 == 0 or norm2 == 0:
            raise FaceEngineError("Embedding norm is zero or non-finite")
            
        first_2d = np.ascontiguousarray(first.reshape(1, -1))
        second_2d = np.ascontiguousarray(second.reshape(1, -1))
        
        score = self._recognizer.match(first_2d, second_2d, cv2.FaceRecognizerSF_FR_COSINE)
        if not np.isfinite(score):
            raise FaceEngineError("Match score is non-finite")
        return float(score)

    def model_identity(self) -> str:
        if self._identity is None:
            raise FaceEngineError("Models not loaded")
        return self._identity
