import argparse
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
import logging

from src.config import load_config
from src.database import ArchiveDatabase
from src.face_engine import Cv2FaceEngine, OPENCV_AVAILABLE, FaceEngineError
from src.hashing import sha256_file
from src.logger import setup_logger

def get_engine(config, logger: logging.Logger) -> Cv2FaceEngine:
    engine = Cv2FaceEngine(config=config.faces, logger=logger)
    engine.load_models()
    return engine

def check_write_permission(args, config, logger: logging.Logger) -> bool:
    if getattr(args, "commit", False):
        if config.app.dry_run:
            logger.error("Commit refused: app.dry_run is true. Cannot write to database.")
            sys.exit(2)
        return True
    return False

def cmd_enroll(args, config, db: ArchiveDatabase, logger: logging.Logger):
    if not OPENCV_AVAILABLE:
        logger.error("Configuration error: Face processing dependency unavailable: install the Phase 5 requirements.")
        return 1

    try:
        engine = get_engine(config=config, logger=logger)
    except FaceEngineError as e:
        logger.error(f"Enrollment failed: {e}")
        return 1
        
    write_allowed = check_write_permission(args, config, logger)
    
    source_dir = Path(args.source)
    if not source_dir.is_dir():
        logger.error(f"Source is not a directory: {source_dir}")
        return 1
        
    # Analyze in memory
    planned_accepted = []
    planned_rejected = []
    
    success_count = 0
    fail_count = 0
    
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        for img_path in source_dir.rglob(f"*{ext}"):
            if not img_path.is_file() or img_path.is_symlink():
                logger.warning(f"Skipping unsafe or non-regular file: {img_path}")
                continue
                
            try:
                resolved = img_path.resolve()
                if not str(resolved).startswith(str(config.faces.reference_root.resolve())):
                    pass 
            except Exception:
                continue

            if not str(img_path.resolve()).startswith(str(config.faces.reference_root.resolve())):
                planned_rejected.append((str(img_path), "unknown", "OUTSIDE_ROOT", "Path outside reference root"))
                logger.warning("Rejected reference: OUTSIDE_ROOT")
                logger.debug(f"File outside reference root rejected: {img_path}")
                fail_count += 1
                continue
                
            file_hash = sha256_file(img_path)
            if db.reference_exists(file_hash):
                logger.debug(f"Skipping duplicate reference: {img_path}")
                continue
                
            import cv2
            image = cv2.imread(str(img_path))
            if image is None:
                planned_rejected.append((str(img_path), file_hash, "UNREADABLE", "OpenCV imread failed"))
                logger.warning("Rejected reference: UNREADABLE")
                logger.debug(f"Unreadable image: {img_path}")
                fail_count += 1
                continue
                
            faces = engine.detect_faces(image)
            if len(faces) == 0:
                planned_rejected.append((str(img_path), file_hash, "NO_FACE", "No face detected"))
                logger.warning("Rejected reference: NO_FACE")
                logger.debug(f"No face detected: {img_path}")
                fail_count += 1
                continue
            if len(faces) > 1:
                planned_rejected.append((str(img_path), file_hash, "MULTIPLE_FACES", "Multiple faces detected"))
                logger.warning("Rejected reference: MULTIPLE_FACES")
                logger.debug(f"Multiple faces detected: {img_path}")
                fail_count += 1
                continue
                
            face = faces[0]
            confidence = float(face[-1])
            w, h = int(face[2]), int(face[3])
            
            if w < config.faces.minimum_face_size_px or h < config.faces.minimum_face_size_px:
                planned_rejected.append((str(img_path), file_hash, "TINY_FACE", f"Face {w}x{h} below minimum size"))
                logger.warning("Rejected reference: TINY_FACE")
                logger.debug(f"Tiny face: {img_path}")
                fail_count += 1
                continue
                
            try:
                aligned = engine.align_face(image, face)
                embedding = engine.create_embedding(aligned)
            except FaceEngineError as e:
                planned_rejected.append((str(img_path), file_hash, "ENGINE_ERROR", str(e)))
                logger.warning("Rejected reference: ENGINE_ERROR")
                logger.debug(f"Engine error on {img_path}: {e}")
                fail_count += 1
                continue
                
            quality_json = json.dumps({"w": w, "h": h})
            planned_accepted.append({
                "source_path": str(img_path),
                "source_sha256": file_hash,
                "detector_confidence": confidence,
                "face_width": w,
                "face_height": h,
                "quality_json": quality_json,
                "embedding_blob": embedding.tobytes(),
                "embedding_dimension": embedding.size,
                "model_identity": engine.model_identity()
            })
            success_count += 1

    if success_count < config.faces.minimum_references_per_person:
        logger.info(f"Insufficient accepted references: {success_count} found, {config.faces.minimum_references_per_person} required.")
        if write_allowed:
            return 1
        
    if not write_allowed:
        for i, ref in enumerate(planned_accepted):
            logger.info(f"[DRY-RUN] Would accept reference {i+1} of {success_count}")
        logger.info(f"Enrollment complete: accepted={success_count} rejected={fail_count}")
        return 0

    if success_count < config.faces.minimum_references_per_person:
        return 1

    try:
        with db.transaction() as conn:
            # 1. get_or_create_person inside transaction
            now = datetime.now(timezone.utc).isoformat()
            row = conn.execute("SELECT person_id, display_name, active FROM people WHERE person_slug = ?", (args.person_slug,)).fetchone()
            if row:
                person_id = row["person_id"]
                if row["display_name"] != args.display_name or not row["active"]:
                    conn.execute("UPDATE people SET display_name = ?, active = 1, updated_at = ? WHERE person_id = ?", (args.display_name, now, person_id))
            else:
                cursor = conn.execute(
                    "INSERT INTO people (person_slug, display_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (args.person_slug, args.display_name, now, now)
                )
                person_id = cursor.lastrowid
            
            # 2. insert references
            for i, ref in enumerate(planned_accepted):
                conn.execute(
                    "INSERT INTO face_references "
                    "(person_id, source_sha256, source_path, detector_confidence, face_width, face_height, quality_json, embedding_blob, embedding_dimension, model_identity, enrolled_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (person_id, ref["source_sha256"], ref["source_path"], ref["detector_confidence"], ref["face_width"], ref["face_height"], ref["quality_json"], ref["embedding_blob"], ref["embedding_dimension"], ref["model_identity"], now)
                )
                logger.info(f"Accepted reference {i+1} of {success_count}")
                logger.debug(f"Enrolled {ref['source_path']} for {args.person_slug}")

            # 3. insert rejected
            for img_path_str, file_hash, r_code, r_msg in planned_rejected:
                conn.execute(
                    "INSERT INTO face_references "
                    "(person_id, source_sha256, source_path, active, enrolled_at, rejection_code, rejection_message) "
                    "VALUES (?, ?, ?, 0, ?, ?, ?)",
                    (person_id, file_hash, img_path_str, now, r_code, r_msg)
                )
    except Exception as e:
        logger.error(f"Enrollment transaction failed: {e}")
        return 1

    logger.info(f"Enrollment complete: accepted={success_count} rejected={fail_count}")
    return 0

def cmd_list(args, config, db: ArchiveDatabase, logger: logging.Logger):
    people = db.get_active_people()
    for p in people:
        print(f"[{p['person_id']}] {p['person_slug']}: {p['display_name']}")
    return 0

def cmd_deactivate(args, config, db: ArchiveDatabase, logger: logging.Logger):
    write_allowed = check_write_permission(args, config, logger)
    if not write_allowed:
        logger.info(f"[DRY-RUN] Would deactivate {args.person_slug}")
        return 0
        
    if db.deactivate_person(args.person_slug):
        logger.info(f"Deactivated person: {args.person_slug}")
    else:
        logger.warning(f"Person not found or already inactive: {args.person_slug}")
    return 0

def cmd_rebuild(args, config, db: ArchiveDatabase, logger: logging.Logger):
    if not OPENCV_AVAILABLE:
        logger.error("Configuration error: Face processing dependency unavailable: install the Phase 5 requirements.")
        return 1

    try:
        engine = get_engine(config=config, logger=logger)
    except FaceEngineError as e:
        logger.error(f"Rebuild failed: {e}")
        return 1

    write_allowed = check_write_permission(args, config, logger)

    person = db.find_person_by_slug(args.person_slug)
    if not person or not person["active"]:
        logger.error(f"Person not found or inactive: {args.person_slug}")
        return 1
        
    person_id = person["person_id"]
    
    try:
        ref_root = config.faces.reference_root.resolve(strict=True)
    except Exception:
        logger.error(f"Reference root does not exist: {config.faces.reference_root}")
        return 1
        
    person_folder = Path(config.faces.reference_root) / args.person_slug
    try:
        person_folder = person_folder.resolve(strict=True)
    except Exception:
        logger.error(f"Person folder does not exist: {person_folder}")
        return 1
        
    if not person_folder.is_dir():
        logger.error(f"Person folder is not a directory: {person_folder}")
        return 1
        
    if not str(person_folder).startswith(str(ref_root)):
        logger.error("Person folder escapes reference root.")
        return 1
        
    with db.connect() as conn:
        old_refs = [dict(r) for r in conn.execute(
            "SELECT * FROM face_references WHERE person_id = ? AND active = 1", (person_id,)
        ).fetchall()]
        
    discovered_files = []
    for p in person_folder.iterdir():
        if p.is_file() and not p.is_symlink():
            if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                discovered_files.append(p)
                
    discovered_files.sort(key=lambda x: str(x).lower())
    
    logger.info(f"Discovered references: {len(discovered_files)}")
    
    planned_accepted = []
    planned_rejected = []
    
    success_count = 0
    fail_count = 0
    seen_hashes = set()
    
    for img_path in discovered_files:
        file_hash = sha256_file(img_path)
        if file_hash in seen_hashes:
            planned_rejected.append((str(img_path), file_hash, "DUPLICATE_FILE", "Duplicate file in candidate set"))
            logger.warning("Rejected reference: DUPLICATE_FILE")
            logger.debug(f"Duplicate file: {img_path}")
            fail_count += 1
            continue
        seen_hashes.add(file_hash)
        
        import cv2
        image = cv2.imread(str(img_path))
        if image is None:
            planned_rejected.append((str(img_path), file_hash, "UNREADABLE", "OpenCV imread failed"))
            logger.warning("Rejected reference: UNREADABLE")
            logger.debug(f"Unreadable image: {img_path}")
            fail_count += 1
            continue
            
        faces = engine.detect_faces(image)
        if len(faces) == 0:
            planned_rejected.append((str(img_path), file_hash, "NO_FACE", "No face detected"))
            logger.warning("Rejected reference: NO_FACE")
            logger.debug(f"No face detected: {img_path}")
            fail_count += 1
            continue
        if len(faces) > 1:
            planned_rejected.append((str(img_path), file_hash, "MULTIPLE_FACES", "Multiple faces detected"))
            logger.warning("Rejected reference: MULTIPLE_FACES")
            logger.debug(f"Multiple faces detected: {img_path}")
            fail_count += 1
            continue
            
        face = faces[0]
        confidence = float(face[-1])
        w, h = int(face[2]), int(face[3])
        
        if w < config.faces.minimum_face_size_px or h < config.faces.minimum_face_size_px:
            planned_rejected.append((str(img_path), file_hash, "TINY_FACE", f"Face {w}x{h} below minimum size"))
            logger.warning("Rejected reference: TINY_FACE")
            logger.debug(f"Tiny face: {img_path}")
            fail_count += 1
            continue
            
        try:
            aligned = engine.align_face(image, face)
            embedding = engine.create_embedding(aligned)
        except FaceEngineError as e:
            planned_rejected.append((str(img_path), file_hash, "ENGINE_ERROR", str(e)))
            logger.warning("Rejected reference: ENGINE_ERROR")
            logger.debug(f"Engine error on {img_path}: {e}")
            fail_count += 1
            continue
            
        quality_json = json.dumps({"w": w, "h": h})
        planned_accepted.append({
            "source_path": str(img_path),
            "source_sha256": file_hash,
            "detector_confidence": confidence,
            "face_width": w,
            "face_height": h,
            "quality_json": quality_json,
            "embedding_blob": embedding.tobytes(),
            "embedding_dimension": embedding.size,
            "model_identity": engine.model_identity()
        })
        success_count += 1

    if success_count < config.faces.minimum_references_per_person:
        logger.info(f"Insufficient accepted references: {success_count} found, {config.faces.minimum_references_per_person} required.")
        if write_allowed:
            return 1
            
    if not write_allowed:
        logger.info(f"Accepted references: {success_count}")
        logger.info(f"Rejected references: {fail_count}")
        return 0

    if success_count < config.faces.minimum_references_per_person:
        return 1

    try:
        with db.transaction() as conn:
            now = datetime.now(timezone.utc).isoformat()
            
            accepted_hashes = {r["source_sha256"] for r in planned_accepted}
            old_ids_to_deactivate = [r["reference_id"] for r in old_refs if r["source_sha256"] not in accepted_hashes]
            
            if old_ids_to_deactivate:
                placeholders = ",".join("?" for _ in old_ids_to_deactivate)
                conn.execute(f"UPDATE face_references SET active = 0 WHERE reference_id IN ({placeholders})", old_ids_to_deactivate)
            
            for ref in planned_accepted:
                existing = conn.execute(
                    "SELECT reference_id FROM face_references WHERE person_id = ? AND source_sha256 = ? AND model_identity = ?",
                    (person_id, ref["source_sha256"], ref["model_identity"])
                ).fetchone()
                
                if existing:
                    conn.execute(
                        "UPDATE face_references SET active = 1, enrolled_at = ?, source_path = ?, detector_confidence = ?, face_width = ?, face_height = ?, quality_json = ?, embedding_blob = ?, embedding_dimension = ? WHERE reference_id = ?",
                        (now, ref["source_path"], ref["detector_confidence"], ref["face_width"], ref["face_height"], ref["quality_json"], ref["embedding_blob"], ref["embedding_dimension"], existing["reference_id"])
                    )
                else:
                    conn.execute(
                        "INSERT INTO face_references "
                        "(person_id, source_sha256, source_path, detector_confidence, face_width, face_height, quality_json, embedding_blob, embedding_dimension, model_identity, enrolled_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (person_id, ref["source_sha256"], ref["source_path"], ref["detector_confidence"], ref["face_width"], ref["face_height"], ref["quality_json"], ref["embedding_blob"], ref["embedding_dimension"], ref["model_identity"], now)
                    )
            
            for img_path_str, file_hash, r_code, r_msg in planned_rejected:
                existing_rej = conn.execute(
                    "SELECT reference_id FROM face_references WHERE person_id = ? AND source_sha256 = ? AND model_identity = ?",
                    (person_id, file_hash, engine.model_identity())
                ).fetchone()
                if existing_rej:
                    conn.execute(
                        "UPDATE face_references SET active = 0, enrolled_at = ?, source_path = ?, rejection_code = ?, rejection_message = ? WHERE reference_id = ?",
                        (now, img_path_str, r_code, r_msg, existing_rej["reference_id"])
                    )
                else:
                    conn.execute(
                        "INSERT INTO face_references "
                        "(person_id, source_sha256, source_path, active, enrolled_at, rejection_code, rejection_message) "
                        "VALUES (?, ?, ?, 0, ?, ?, ?)",
                        (person_id, file_hash, img_path_str, now, r_code, r_msg)
                    )
                
            conn.execute("UPDATE face_calibrations SET active = 0")
            logger.info("Rebuild committed successfully.")
            
    except Exception as e:
        logger.error(f"Rebuild transaction failed: {e}")
        return 1

    logger.info(f"Accepted references: {success_count}")
    logger.info(f"Rejected references: {fail_count}")
    return 0

def cmd_calibrate(args, config, db: ArchiveDatabase, logger: logging.Logger):
    if not OPENCV_AVAILABLE:
        logger.error("Configuration error: Face processing dependency unavailable: install the Phase 5 requirements.")
        return 1

    try:
        import numpy as np
    except ImportError:
        logger.error("Configuration error: Face processing dependency unavailable: install the Phase 5 requirements.")
        return 1

    try:
        engine = get_engine(config=config, logger=logger)
    except FaceEngineError as e:
        logger.error(f"Calibration failed: {e}")
        return 1
        
    write_allowed = check_write_permission(args, config, logger)
    model_identity = engine.model_identity()
    
    people = db.get_active_people()
    if len(people) < 2:
        logger.error("Calibration requires at least two enrolled people.")
        return 1
        
    person_refs = {}
    ref_hashes = []
    
    all_refs = db.get_active_references(model_identity)
    
    for ref in all_refs:
        pid = ref["person_id"]
        if pid not in person_refs:
            person_refs[pid] = []
        person_refs[pid].append(ref)
        ref_hashes.append(ref["source_sha256"])
        
    for p in people:
        pid = p["person_id"]
        count = len(person_refs.get(pid, []))
        if count < config.faces.minimum_references_per_person:
            logger.error(f"Person {p['person_slug']} has only {count} references (minimum {config.faces.minimum_references_per_person}).")
            return 1
            
    import hashlib
    ref_hashes.sort()
    ref_set_hash = hashlib.sha256("".join(ref_hashes).encode()).hexdigest()
    
    # Generate scores
    positive_scores = []
    negative_scores = []
    
    pids = list(person_refs.keys())
    for i in range(len(pids)):
        refs_A = person_refs[pids[i]]
        # Positive pairs
        for r1 in range(len(refs_A)):
            for r2 in range(r1 + 1, len(refs_A)):
                e1 = np.frombuffer(refs_A[r1]["embedding_blob"], dtype=np.float32)
                e2 = np.frombuffer(refs_A[r2]["embedding_blob"], dtype=np.float32)
                score = engine.compare_embeddings(e1, e2)
                positive_scores.append(score)
                
        # Negative pairs
        for j in range(i + 1, len(pids)):
            refs_B = person_refs[pids[j]]
            for rA in refs_A:
                for rB in refs_B:
                    e1 = np.frombuffer(rA["embedding_blob"], dtype=np.float32)
                    e2 = np.frombuffer(rB["embedding_blob"], dtype=np.float32)
                    score = engine.compare_embeddings(e1, e2)
                    negative_scores.append(score)
                    
    if not positive_scores or not negative_scores:
        logger.error("Insufficient pairs to calibrate.")
        return 1
        
    max_neg = max(negative_scores)
    min_pos = min(positive_scores)
    
    # We want conservative: accept threshold must be higher than all negatives
    accept_threshold = max_neg + 0.05
    review_threshold = max_neg + 0.01
    minimum_margin = 0.05
    
    # Enforce bounds
    if accept_threshold >= 1.0:
        accept_threshold = 0.99
    if review_threshold >= accept_threshold:
        review_threshold = accept_threshold - 0.01
        
    report = {
        "positive_pairs": len(positive_scores),
        "negative_pairs": len(negative_scores),
        "max_negative": max_neg,
        "min_positive": min_pos,
        "proposed_accept": accept_threshold,
        "proposed_review": review_threshold,
        "proposed_margin": minimum_margin
    }
    
    logger.info(f"Calibration proposed: Accept={accept_threshold:.3f}, Review={review_threshold:.3f}, Margin={minimum_margin:.3f}")
    
    if not write_allowed:
        logger.info("[DRY-RUN] Would activate this calibration.")
    else:
        db.activate_calibration(
            model_identity, ref_set_hash, accept_threshold, review_threshold, minimum_margin, 
            len(positive_scores), len(negative_scores), json.dumps(report)
        )
        logger.info("Calibration activated successfully.")
        
    return 0

def main():
    parser = argparse.ArgumentParser(description="Face Enrollment CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    p_enroll = subparsers.add_parser("enroll")
    p_enroll.add_argument("--person-slug", required=True)
    p_enroll.add_argument("--display-name", required=True)
    p_enroll.add_argument("--source", required=True)
    p_enroll.add_argument("--commit", action="store_true", help="Commit changes to database")
    
    p_list = subparsers.add_parser("list")
    
    p_deactivate = subparsers.add_parser("deactivate-person")
    p_deactivate.add_argument("--person-slug", required=True)
    p_deactivate.add_argument("--commit", action="store_true", help="Commit changes to database")
    
    p_rebuild = subparsers.add_parser("rebuild")
    p_rebuild.add_argument("--person-slug", required=True)
    p_rebuild.add_argument("--commit", action="store_true", help="Commit changes to database")
    
    p_calibrate = subparsers.add_parser("calibrate")
    p_calibrate.add_argument("--commit", action="store_true", help="Commit changes to database")
    
    args = parser.parse_args()
    
    try:
        config = load_config()
    except Exception as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 1
        
    logger = setup_logger(config)
    db = ArchiveDatabase(config.app.database_path)
    
    try:
        if args.command == "enroll":
            return cmd_enroll(args, config, db, logger)
        elif args.command == "list":
            return cmd_list(args, config, db, logger)
        elif args.command == "deactivate-person":
            return cmd_deactivate(args, config, db, logger)
        elif args.command == "rebuild":
            return cmd_rebuild(args, config, db, logger)
        elif args.command == "calibrate":
            return cmd_calibrate(args, config, db, logger)
    except SystemExit as e:
        return e.code
        
    return 1

if __name__ == "__main__":
    sys.exit(main())
