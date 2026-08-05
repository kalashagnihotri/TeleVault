import sys; sys.path.insert(0, '')
from pathlib import Path
from src.config import load_config
from src.face_engine import Cv2FaceEngine
from src.image_utils import decode_image_with_exif
import numpy as np

config = load_config()
import logging
logger = logging.getLogger()
engine = Cv2FaceEngine(config.faces, logger)
engine.load_models()

CALIBRATION_DIR = Path("private_negatives/calibration")
HOLDOUT_DIR = Path("private_negatives/holdout")

exported_files = list(CALIBRATION_DIR.glob("*.jpg")) + list(HOLDOUT_DIR.glob("*.jpg"))
failed = 0
for exported_file in exported_files:
    image = decode_image_with_exif(str(exported_file))["image"]
    raw_faces = engine.detect_faces(image)
    accepted = [
        face
        for face in raw_faces
        if int(face[2]) >= config.faces.minimum_face_size_px
        and int(face[3]) >= config.faces.minimum_face_size_px
    ]
    if len(accepted) != 1:
        print(f"FAILED on {exported_file}: found {len(accepted)} accepted faces.")
        print(f"Raw faces: {raw_faces}")
        failed += 1

print(f"Total failed: {failed}")
