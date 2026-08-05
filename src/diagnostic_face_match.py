import argparse
import sys
import os
import json
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_config
from src.database import ArchiveDatabase
from src.face_engine import Cv2FaceEngine, OPENCV_AVAILABLE
from src.image_utils import decode_image_with_exif
from src.face_analysis import FaceAnalysisWorker
from src.logger import setup_logger

def get_iou(bb1: dict, bb2: dict) -> float:
    x_left = max(bb1['x'], bb2['x'])
    y_top = max(bb1['y'], bb2['y'])
    x_right = min(bb1['x'] + bb1['w'], bb2['x'] + bb2['w'])
    y_bottom = min(bb1['y'] + bb1['h'], bb2['y'] + bb2['h'])

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    intersection_area = (x_right - x_left) * (y_bottom - y_top)
    bb1_area = bb1['w'] * bb1['h']
    bb2_area = bb2['w'] * bb2['h']
    iou = intersection_area / float(bb1_area + bb2_area - intersection_area)
    return iou

def main():
    parser = argparse.ArgumentParser(description="Read-only Phase 5 face-match diagnostic CLI")
    parser.add_argument("--source", type=str, required=True, help="Path to image file")
    parser.add_argument("--verbose-private", action="store_true", help="Print actual filenames instead of hashes")
    
    args = parser.parse_args()
    source_path = Path(args.source)
    
    if not source_path.exists():
        print("Error: %s does not exist." % source_path)
        sys.exit(1)
        
    config = load_config()
    
    if not OPENCV_AVAILABLE:
        print("Error: OpenCV is not available. Please install Phase 5 dependencies.")
        sys.exit(1)
        
    logger = setup_logger(config)
    logger.name = "diagnostic"
    if args.verbose_private:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
        
    try:
        img_info = decode_image_with_exif(str(source_path))
    except Exception as e:
        logger.debug("Image decode traceback", exc_info=True)
        if args.verbose_private:
            print("Failed to decode image %s: %s" % (source_path.name, e))
        else:
            print("Failed to decode image: %s" % e.__class__.__name__)
        sys.exit(1)
        
    image = img_info["image"]
    
    print("--- Face Match Diagnostics ---")
    if args.verbose_private:
        print("Source file: %s" % source_path.name)
    else:
        import hashlib
        with open(source_path, "rb") as f:
            short_hash = hashlib.sha256(f.read()).hexdigest()[:8]
        print("Source file: %s" % short_hash)
        
    print("Loading models and active calibration...")
    try:
        engine = Cv2FaceEngine(
            config=config.faces,
            logger=logger,
        )
        engine.load_models()
    except Exception as e:
        logger.debug("Face diagnostic initialization traceback", exc_info=True)
        if args.verbose_private:
            print("Failed to initialize face engine: %s" % e)
        else:
            print("Failed to initialize face engine: %s" % e.__class__.__name__)
        sys.exit(1)
        
    try:
        database_path = config.app.database_path
        db = ArchiveDatabase(database_path, read_only=True)
    except Exception as e:
        logger.debug("Database initialization traceback", exc_info=True)
        if args.verbose_private:
            print("Failed to open diagnostic database: %s" % e)
        else:
            print("Failed to open diagnostic database: %s" % e.__class__.__name__)
        sys.exit(1)
        
    worker = FaceAnalysisWorker(config, db, engine, logger)
    worker.load_snapshots()
    
    if not worker.calibration_snapshot:
        print("Warning: No active calibration found. Matches will be UNKNOWN_UNCALIBRATED.")
    
    print("Analyzing image...")
    res = worker.analyze_image(image)
    
    completed_faces = res.accepted_faces + res.unknown_faces + res.processing_errors
    print("\nCompleted faces: %s" % completed_faces)
    print("Accepted matches: %s" % res.accepted_faces)
    print("Unknown faces: %s" % res.unknown_faces)
    print("Ignored tiny: %s" % res.ignored_tiny)
    print("Errors: %s\n" % res.processing_errors)
    
    accepted_boxes = []
    
    for face in res.face_results:
        print("-" * 50)
        print("Face Index : %s" % face.get('face_index'))
        bb_json = face.get("bounding_box_json")
        print("Bounding Box: %s" % bb_json)
        print(
            f"Confidence  : "
            f"{float(face.get('detector_confidence') or 0.0):.4f}"
        )
        print("Decision    : %s" % face.get('decision'))
        
        if "IGNORED" in face.get("decision", ""):
            print("Size Decision: Rejected (Too small)")
            continue
        elif "ERROR" in face.get("decision", ""):
            print("Error Stage : %s" % face.get('error_stage'))
            print("Error Code  : %s" % face.get('error_code'))
            continue
        else:
            print("Size Decision: Accepted")
            
        print("Best Person ID    : %s" % face.get('best_person_id'))
        if face.get('best_score') is not None:
            print(f"Best Score        : {float(face.get('best_score') or 0.0):.4f}")
        print("Second Best Person: %s" % face.get('second_best_person_id'))
        if face.get('second_best_score') is not None:
            print(f"Second Best Score : {float(face.get('second_best_score') or 0.0):.4f}")
        
        if face.get('score_margin') is not None:
            print(f"Score Margin      : {float(face.get('score_margin') or 0.0):.4f}")
        print("Supporting Refs   : %s" % face.get('supporting_reference_count'))
        
        diag_data = face.get("diagnostic_data")
        if diag_data and diag_data.get("scores_by_person"):
            print("\nScores against every reference for the best person:")
            best_id = face.get('best_person_id')
            if best_id:
                scores = diag_data["scores_by_person"].get(best_id, [])
                scores_sorted = sorted(scores, reverse=True)
                print(f"  Person {best_id}: " + ", ".join(f"{s:.4f}" for s in scores_sorted))
                
            print("\nAggregate person scores:")
            for pid, pscore in diag_data.get("person_aggregate_scores", {}).items():
                print(f"  Person {pid}: {float(pscore or 0.0):.4f}")
                
            print("\nMaximum person scores:")
            for pid, pscore in diag_data.get("person_max_scores", {}).items():
                print(f"  Person {pid}: {float(pscore or 0.0):.4f}")
                
        # Track boxes for overlap check
        if face.get("decision") == "KNOWN_MATCH":
            bb = json.loads(bb_json)
            bb["face_index"] = face.get("face_index")
            accepted_boxes.append(bb)
            
    print("-" * 50)
    
    if len(accepted_boxes) > 1:
        print("\nChecking for possible duplicate detections (IoU > 0.5)...")
        found_overlap = False
        for i in range(len(accepted_boxes)):
            for j in range(i + 1, len(accepted_boxes)):
                iou = get_iou(accepted_boxes[i], accepted_boxes[j])
                if iou > 0.5:
                    found_overlap = True
                    print(f"WARNING: Face {accepted_boxes[i]['face_index']} and Face {accepted_boxes[j]['face_index']} have a strong overlap (IoU = {iou:.4f}). They may be duplicate detections of the same physical face.")
        
        if not found_overlap:
            print("No strong overlaps found.")
            
if __name__ == "__main__":
    main()
