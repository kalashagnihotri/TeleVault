import argparse
import sys
import os
import hashlib
from pathlib import Path
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_config
from src.face_engine import OPENCV_AVAILABLE, Cv2FaceEngine
from src.image_utils import decode_image_with_exif
import logging

class DummyLogger(logging.Logger):
    def __init__(self):
        super().__init__("dummy")
        self.setLevel(logging.CRITICAL)

def _report(name, image, detector_dim, faces):
    print("\n--- %s ---", name)
    
    if faces is None:
        faces = []
    elif isinstance(faces, tuple) and len(faces) == 2:
        faces = faces[1] if faces[1] is not None else []
    
    if isinstance(faces, np.ndarray):
        faces = faces.tolist()
        
    num_faces = len(faces)
    
    print("ndarray shape: %s", image.shape)
    print("dtype: %s", image.dtype)
    print("C_CONTIGUOUS: %s", image.flags['C_CONTIGUOUS'])
    print("detector input dimensions: %s", detector_dim)
    print("detection matrix shape: (%s, %s)", num_faces, len(faces[0]) if num_faces > 0 else 0)
    print("detection count: %s", num_faces)
    
    for idx, face in enumerate(faces, 1):
        conf = float(face[-1])
        w, h = int(face[2]), int(face[3])
        print("  Face %s: conf=%s, size=%sx%s", idx, conf:.4f, w, h)

def main():
    parser = argparse.ArgumentParser(description="Read-only face detector parity diagnostic")
    parser.add_argument("--source", type=str, nargs="+", required=True, help="Paths to image files")
    parser.add_argument("--verbose-private", action="store_true", help="Print actual filenames instead of hashes")
    
    args = parser.parse_args()
    config = load_config()
    
    if not OPENCV_AVAILABLE:
        print("Error: OpenCV is not available. Please install Phase 5 dependencies.")
        sys.exit(1)
        
    import cv2
    detector_path = config.faces.model_root / config.faces.detector_model
    if not detector_path.exists():
        print("Error: Detector model missing at %s", detector_path)
        sys.exit(1)
        
    logger = DummyLogger()
    
    # Pre-decode all images
    images_info = []
    for source in args.source:
        source_path = Path(source)
        if not source_path.exists():
            print("Error: %s does not exist.", source_path)
            sys.exit(1)
            
        try:
            with open(source_path, "rb") as f:
                short_hash = hashlib.sha256(f.read()).hexdigest()[:8]
                
            img_info = decode_image_with_exif(str(source_path))
            img_info["short_hash"] = short_hash
            img_info["filename"] = source_path.name
            images_info.append(img_info)
        except Exception as e:
            if args.verbose_private:
                print("Failed to decode %s: %s", source_path.name, e)
            else:
                print("Failed to decode image: %s", e)
            sys.exit(1)
            
    # Persistent Engine (C and D)
    persistent_engine = Cv2FaceEngine(config, logger)
    persistent_engine.detector_path = detector_path
    
    print("\n================ PASS 1 ================")
    
    for img_info in images_info:
        if args.verbose_private:
            print("\n================ Image: %s ================", img_info['filename'])
        else:
            print("\n================ Image Hash: %s ================", img_info['short_hash'])
            
        raw_image = img_info["image"]
        
        # A. Fresh Raw YuNet
        # Safe normalization exactly as Cv2FaceEngine now does
        image = np.asarray(raw_image)
        image = np.ascontiguousarray(image)
        height, width = image.shape[:2]
        new_size = (width, height)
        
        raw_detector = cv2.FaceDetectorYN.create(
            str(detector_path), "", new_size, config.faces.detector_confidence, 0.3, 5000
        )
        _, raw_faces = raw_detector.detect(image)
        _report("A. Fresh raw YuNet detector", image, new_size, raw_faces)
        
        # B. Fresh Cv2FaceEngine
        fresh_engine = Cv2FaceEngine(config, logger)
        fresh_engine.detector_path = detector_path
        fresh_faces = fresh_engine.detect_faces(raw_image)
        _report("B. Fresh Cv2FaceEngine", image, new_size, fresh_faces)
        
        # C. Persistent Cv2FaceEngine
        persistent_faces = persistent_engine.detect_faces(raw_image)
        _report("C. Persistent Cv2FaceEngine", image, new_size, persistent_faces)
        
    print("\n================ PASS 2 ================")
    
    for img_info in images_info:
        if args.verbose_private:
            print("\n================ Image: %s ================", img_info['filename'])
        else:
            print("\n================ Image Hash: %s ================", img_info['short_hash'])
            
        raw_image = img_info["image"]
        image = np.asarray(raw_image)
        image = np.ascontiguousarray(image)
        height, width = image.shape[:2]
        new_size = (width, height)
        
        # D. Persistent Cv2FaceEngine Second Pass
        persistent_faces = persistent_engine.detect_faces(raw_image)
        _report("D. Persistent Cv2FaceEngine Second Pass", image, new_size, persistent_faces)

if __name__ == "__main__":
    main()
