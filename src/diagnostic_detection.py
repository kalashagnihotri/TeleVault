import argparse
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_config
from src.face_engine import OPENCV_AVAILABLE
from src.image_utils import decode_image_with_exif

def main():
    parser = argparse.ArgumentParser(description="Read-only face detection diagnostic")
    parser.add_argument("--source", type=str, required=True, help="Path to image file")
    parser.add_argument("--thresholds", type=float, nargs="+", default=[0.90, 0.85, 0.80], help="Thresholds to test")
    parser.add_argument("--verbose-private", action="store_true", help="Print actual filenames instead of hashes")
    
    args = parser.parse_args()
    source_path = Path(args.source)
    
    if not source_path.exists():
        print(f"Error: {source_path} does not exist.")
        sys.exit(1)
        
    config = load_config()
    
    if not OPENCV_AVAILABLE:
        print("Error: OpenCV is not available. Please install Phase 5 dependencies.")
        sys.exit(1)
        
    import cv2
    
    try:
        img_info = decode_image_with_exif(str(source_path))
    except Exception as e:
        if args.verbose_private:
            print(f"Failed to decode image {source_path.name}: {e}")
        else:
            print(f"Failed to decode image: {e}")
        sys.exit(1)
        
    image = img_info["image"]
    raw_width = img_info["raw_width"]
    raw_height = img_info["raw_height"]
    norm_width = img_info["normalized_width"]
    norm_height = img_info["normalized_height"]
    exif_orientation = img_info["exif_orientation"]
    was_normalized = img_info["was_normalized"]
    
    print(f"--- Image Diagnostics ---")
    if args.verbose_private:
        print(f"Source file: {source_path.name}")
    else:
        import hashlib
        with open(source_path, "rb") as f:
            short_hash = hashlib.sha256(f.read()).hexdigest()[:8]
        print(f"Source file: {short_hash}")
        
    print(f"Raw stored pixel dimensions: {raw_width}x{raw_height}")
    print(f"EXIF orientation value: {exif_orientation}")
    print(f"Orientation normalization applied: {was_normalized}")
    print(f"Orientation-normalized dimensions: {norm_width}x{norm_height}")
    
    # We create a new detector instance per threshold, bypassing Cv2FaceEngine which loads everything
    detector_path = config.faces.model_root / config.faces.detector_model
    if not detector_path.exists():
        print(f"Error: Detector model missing at {detector_path}")
        sys.exit(1)
        
    for threshold in args.thresholds:
        # Create a fresh isolated detector
        detector = cv2.FaceDetectorYN.create(
            str(detector_path),
            "",
            (320, 320),
            threshold,
            0.3,
            5000
        )
        
        height, width, _ = image.shape
        detector.setInputSize((width, height))
        
        print(f"\n--- Threshold: {threshold:.2f} ---")
        print(f"Detector input dimensions: {width}x{height}")
        
        _, faces = detector.detect(image)
        detected = faces if faces is not None else []
        
        print(f"Detection count: {len(detected)}")
        
        for idx, face in enumerate(detected, 1):
            conf = float(face[-1])
            w, h = int(face[2]), int(face[3])
            
            # Minimum size decision in normalized coordinates
            if w < config.faces.minimum_face_size_px or h < config.faces.minimum_face_size_px:
                decision = "IGNORED_TINY"
            else:
                decision = "ACCEPTED_SIZE"
                
            print(f"  Face {idx}:")
            print(f"    confidence: {conf:.4f}")
            print(f"    bounding-box width: {w}")
            print(f"    bounding-box height: {h}")
            print(f"    minimum-size decision (orientation-normalized detector-input coordinate space): {decision}")
            
if __name__ == "__main__":
    main()
