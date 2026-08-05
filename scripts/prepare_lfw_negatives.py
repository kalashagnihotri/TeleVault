from __future__ import annotations

import argparse
import hashlib
import random
import shutil
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import logging

from sklearn.datasets import fetch_lfw_people

# Add project root to path
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_config, Config
from src.face_engine import Cv2FaceEngine
from src.image_utils import decode_image_with_exif
from src.logger import setup_logger
from src.logging_utils import RuntimeOptions, log_private

PROJECT = Path(__file__).resolve().parent.parent

CACHE_DIR = PROJECT / "private_data" / "lfw_cache"
CALIBRATION_DIR = PROJECT / "private_negatives" / "calibration"
HOLDOUT_DIR = PROJECT / "private_negatives" / "holdout"

class InsufficientValidIdentitiesError(RuntimeError):
    pass

@dataclass(frozen=True)
class SelectedSource:
    identity_key: str
    source_path: Path
    source_sha256: str

@dataclass(frozen=True)
class ExportedNegative:
    identity_key: str
    source_path: Path
    source_sha256: str
    destination_path: Path
    split: str

def find_lfw_root(cache_directory: Path) -> Path:
    possible_roots = [
        path
        for path in cache_directory.rglob("lfw")
        if path.is_dir() and any(path.glob("*/*.jpg"))
    ]

    if not possible_roots:
        raise RuntimeError(
            "The downloaded LFW image directory could not be located."
        )

    return possible_roots[0]

def select_negatives(
    config: Config,
    engine: Cv2FaceEngine,
    seed: int,
    calibration_count: int,
    holdout_count: int,
    logger: logging.Logger,
    opts: RuntimeOptions
) -> tuple[list[SelectedSource], dict[str, Any]]:
    fetch_lfw_people(
        data_home=CACHE_DIR,
        funneled=False,
        resize=0.1,
        color=False,
        min_faces_per_person=0,
        download_if_missing=True,
    )
    
    lfw_root = find_lfw_root(CACHE_DIR)
    
    identity_folders = [
        folder
        for folder in lfw_root.iterdir()
        if folder.is_dir() and any(folder.glob("*.jpg"))
    ]
    
    rng = random.Random(seed)
    rng.shuffle(identity_folders)
    
    total_required = calibration_count + holdout_count
    selected_sources: list[SelectedSource] = []
    selected_hashes: set[str] = set()
    
    report = {
        "identities_available": len(identity_folders),
        "identities_examined": 0,
        "identities_exhausted": 0,
        "images_examined": 0,
        "decode_errors": 0,
        "zero_detections": 0,
        "tiny_only": 0,
        "multiple_accepted_faces": 0,
        "duplicate_content": 0,
        "alignment_errors": 0,
        "embedding_errors": 0,
        "accepted_calibration": 0,
        "accepted_holdout": 0,
        "seed": seed,
    }
    
    for identity_folder in identity_folders:
        if len(selected_sources) >= total_required:
            break
            
        report["identities_examined"] += 1
        images = sorted(identity_folder.glob("*.jpg"))
        rng.shuffle(images)
        
        found_valid = False
        for img_path in images:
            report["images_examined"] += 1
            
            with open(img_path, "rb") as f:
                file_bytes = f.read()
            source_sha256 = hashlib.sha256(file_bytes).hexdigest()
            
            if source_sha256 in selected_hashes:
                report["duplicate_content"] += 1
                continue
                
            try:
                img_info = decode_image_with_exif(str(img_path))
            except Exception:
                report["decode_errors"] += 1
                continue
                
            image = img_info["image"]
            try:
                raw_faces = engine.detect_faces(image)
            except Exception:
                report["decode_errors"] += 1 # Or generic error
                continue
                
            if not raw_faces:
                report["zero_detections"] += 1
                continue
                
            accepted_faces = [
                face
                for face in raw_faces
                if int(face[2]) >= config.faces.minimum_face_size_px
                and int(face[3]) >= config.faces.minimum_face_size_px
            ]
            
            if len(accepted_faces) == 0:
                report["tiny_only"] += 1
                continue
            elif len(accepted_faces) > 1:
                report["multiple_accepted_faces"] += 1
                continue
                
            # Exactly one accepted-size face
            accepted_face = accepted_faces[0]
            
            try:
                aligned = engine.align_face(image, accepted_face)
            except Exception:
                report["alignment_errors"] += 1
                continue
                
            try:
                embedding = engine.create_embedding(aligned)
            except Exception:
                report["embedding_errors"] += 1
                continue
                
            if embedding is None or getattr(embedding, "size", 0) == 0:
                report["embedding_errors"] += 1
                continue
                
            # Success!
            selected_hashes.add(source_sha256)
            selected_sources.append(
                SelectedSource(
                    identity_key=identity_folder.name,
                    source_path=img_path,
                    source_sha256=source_sha256,
                )
            )
            found_valid = True
            break # Move to next identity
            
        if not found_valid:
            report["identities_exhausted"] += 1
            
    if len(selected_sources) < total_required:
        raise InsufficientValidIdentitiesError(
            f"Only found {len(selected_sources)} valid identities; required {total_required}."
        )
        
    report["accepted_calibration"] = calibration_count
    report["accepted_holdout"] = holdout_count
        
    return selected_sources, report

def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare negative samples from LFW dataset.")
    parser.add_argument("--seed", type=int, default=20260805, help="Random seed")
    parser.add_argument("--calibration-count", type=int, default=25, help="Number of calibration negatives")
    parser.add_argument("--holdout-count", type=int, default=25, help="Number of holdout negatives")
    parser.add_argument("--verbose-private", action="store_true", help="Enable private verbose logging")
    args = parser.parse_args()
    
    if args.calibration_count < 0 or args.holdout_count < 0 or (args.calibration_count + args.holdout_count) <= 0:
        logger.info("Error: Required counts must be positive.")
        return 1
        
    config = load_config()
    opts = RuntimeOptions(verbose_private=args.verbose_private)
    logger = setup_logger(config, verbose_private=opts.verbose_private)
    engine = Cv2FaceEngine(config.faces, logger)
    engine.load_models()
    
    try:
        selected_sources, report = select_negatives(
            config=config,
            engine=engine,
            seed=args.seed,
            calibration_count=args.calibration_count,
            holdout_count=args.holdout_count,
            logger=logger,
            opts=opts
        )
    except InsufficientValidIdentitiesError as exc:
        logger.info("Unable to build the requested negative dataset.")
        return 1
        
    calibration_sources = selected_sources[:args.calibration_count]
    holdout_sources = selected_sources[args.calibration_count:]
    
    run_id = uuid.uuid4().hex
    cal_staging_dir = PROJECT / "private_negatives" / f".calibration_staging_{run_id}"
    hld_staging_dir = PROJECT / "private_negatives" / f".holdout_staging_{run_id}"
    
    cal_staging_dir.mkdir(parents=True, exist_ok=True)
    hld_staging_dir.mkdir(parents=True, exist_ok=True)
    
    exported_negatives = []
    
    try:
        # Build staging
        for i, src in enumerate(calibration_sources, start=1):
            dest = cal_staging_dir / f"calibration_unknown_{i:03d}.jpg"
            shutil.copy2(src.source_path, dest)
            exported_negatives.append(ExportedNegative(
                identity_key=src.identity_key,
                source_path=src.source_path,
                source_sha256=src.source_sha256,
                destination_path=dest,
                split="calibration"
            ))
            
        for i, src in enumerate(holdout_sources, start=1):
            dest = hld_staging_dir / f"holdout_unknown_{i:03d}.jpg"
            shutil.copy2(src.source_path, dest)
            exported_negatives.append(ExportedNegative(
                identity_key=src.identity_key,
                source_path=src.source_path,
                source_sha256=src.source_sha256,
                destination_path=dest,
                split="holdout"
            ))
            
        # Verify sizes
        if len(list(cal_staging_dir.glob("*.jpg"))) != args.calibration_count or \
           len(list(hld_staging_dir.glob("*.jpg"))) != args.holdout_count:
            raise RuntimeError("Staging directory file count mismatch.")
            
        # Transactional replacement
        cal_backup_dir = PROJECT / "private_negatives" / f".calibration_backup_{run_id}"
        hld_backup_dir = PROJECT / "private_negatives" / f".holdout_backup_{run_id}"
        
        # Ensure final dirs exist so rename works even if they didn't
        CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
        HOLDOUT_DIR.mkdir(parents=True, exist_ok=True)
        
        CALIBRATION_DIR.rename(cal_backup_dir)
        HOLDOUT_DIR.rename(hld_backup_dir)
        
        success = False
        try:
            cal_staging_dir.rename(CALIBRATION_DIR)
            hld_staging_dir.rename(HOLDOUT_DIR)
            success = True
        finally:
            if not success:
                # Rollback
                if not CALIBRATION_DIR.exists() and cal_backup_dir.exists():
                    cal_backup_dir.rename(CALIBRATION_DIR)
                if not HOLDOUT_DIR.exists() and hld_backup_dir.exists():
                    hld_backup_dir.rename(HOLDOUT_DIR)
    
        # Delete backups if successful
        if success:
            shutil.rmtree(cal_backup_dir, ignore_errors=True)
            shutil.rmtree(hld_backup_dir, ignore_errors=True)
            
    except Exception as e:
        logger.info("Failure during installation. Rolling back.")
        shutil.rmtree(cal_staging_dir, ignore_errors=True)
        shutil.rmtree(hld_staging_dir, ignore_errors=True)
        return 1

    logger.info("\n--- LFW Negative Dataset Report ---")
    logger.info("Random seed: %s", report['seed'])
    logger.info("Identities available: %s", report['identities_available'])
    logger.info("Identities examined: %s", report['identities_examined'])
    logger.info("Identities exhausted: %s", report['identities_exhausted'])
    logger.info("Images examined: %s", report['images_examined'])
    logger.info("Decode errors: %s", report['decode_errors'])
    logger.info("Zero detections: %s", report['zero_detections'])
    logger.info("Tiny-only images: %s", report['tiny_only'])
    logger.info("Multiple accepted-face images: %s", report['multiple_accepted_faces'])
    logger.info("Duplicate-content images: %s", report['duplicate_content'])
    logger.info("Alignment errors: %s", report['alignment_errors'])
    logger.info("Embedding errors: %s", report['embedding_errors'])
    logger.info("Accepted calibration identities: %s", report['accepted_calibration'])
    logger.info("Accepted holdout identities: %s", report['accepted_holdout'])
    logger.info("-----------------------------------")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
