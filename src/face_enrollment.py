import argparse
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
import logging
from src.logging_utils import log_private

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
        logger.error("Enrollment failed: error=%s", type(e).__name__)
        log_private(
            logger,
            getattr(args, "verbose_private", False),
            "Enrollment private failure details",
            exc_info=True,
        )
        return 1
        
    write_allowed = check_write_permission(args, config, logger)
    
    source_dir = Path(args.source)
    if not source_dir.is_dir():
        logger.error("Source is not a directory: %s", source_dir)
        return 1
        
    # Analyze in memory
    planned_accepted = []
    planned_rejected = []
    
    success_count = 0
    fail_count = 0
    
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        for img_path in source_dir.rglob(f"*{ext}"):
            if not img_path.is_file() or img_path.is_symlink():
                logger.warning("Skipping unsafe or non-regular file: %s", img_path)
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
                logger.debug("File outside reference root rejected: %s", img_path)
                fail_count += 1
                continue
                
            file_hash = sha256_file(img_path)
            if db.reference_exists(file_hash):
                logger.debug("Skipping duplicate reference: %s", img_path)
                continue
                
            import cv2
            image = cv2.imread(str(img_path))
            if image is None:
                planned_rejected.append((str(img_path), file_hash, "UNREADABLE", "OpenCV imread failed"))
                logger.warning("Rejected reference: UNREADABLE")
                logger.debug("Unreadable image: %s", img_path)
                fail_count += 1
                continue
                
            faces = engine.detect_faces(image)
            if len(faces) == 0:
                planned_rejected.append((str(img_path), file_hash, "NO_FACE", "No face detected"))
                logger.warning("Rejected reference: NO_FACE")
                logger.debug("No face detected: %s", img_path)
                fail_count += 1
                continue
            if len(faces) > 1:
                planned_rejected.append((str(img_path), file_hash, "MULTIPLE_FACES", "Multiple faces detected"))
                logger.warning("Rejected reference: MULTIPLE_FACES")
                logger.debug("Multiple faces detected: %s", img_path)
                fail_count += 1
                continue
                
            face = faces[0]
            confidence = float(face[-1])
            w, h = int(face[2]), int(face[3])
            
            min_side = min(w, h)
            if min_side < config.faces.minimum_face_size_px:
                planned_rejected.append((str(img_path), file_hash, "TINY_FACE", f"Face {w}x{h} below minimum size"))
                logger.warning("Rejected reference: TINY_FACE")
                logger.debug("Tiny face: %s", img_path)
                fail_count += 1
                continue
                
            try:
                aligned = engine.align_face(image, face)
                embedding = engine.create_embedding(aligned)
            except FaceEngineError as e:
                planned_rejected.append((str(img_path), file_hash, "ENGINE_ERROR", str(e)))
                logger.warning("Rejected reference: ENGINE_ERROR")
                logger.debug("Engine error on %s: %s", img_path, e)
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
        logger.info("Insufficient accepted references: %s found, %s required.", success_count, config.faces.minimum_references_per_person)
        if write_allowed:
            return 1
        
    if not write_allowed:
        for i, ref in enumerate(planned_accepted):
            logger.info("[DRY-RUN] Would accept reference %s of %s", i+1, success_count)
        logger.info("Enrollment complete: accepted=%s rejected=%s", success_count, fail_count)
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
                logger.info("Accepted reference %s of %s", i+1, success_count)
                logger.debug("Enrolled %s for %s", ref['source_path'], args.person_slug)

            # 3. insert rejected
            for img_path_str, file_hash, r_code, r_msg in planned_rejected:
                conn.execute(
                    "INSERT INTO face_references "
                    "(person_id, source_sha256, source_path, active, enrolled_at, rejection_code, rejection_message) "
                    "VALUES (?, ?, ?, 0, ?, ?, ?)",
                    (person_id, file_hash, img_path_str, now, r_code, r_msg)
                )
    except Exception as e:
        logger.error("Enrollment transaction failed: %s", e)
        return 1

    logger.info("Enrollment complete: accepted=%s rejected=%s", success_count, fail_count)
    return 0

def cmd_list(args, config, db: ArchiveDatabase, logger: logging.Logger):
    people = db.get_active_people()
    for p in people:
        print("[%s] %s: %s", p['person_id'], p['person_slug'], p['display_name'])
    return 0

def cmd_deactivate(args, config, db: ArchiveDatabase, logger: logging.Logger):
    write_allowed = check_write_permission(args, config, logger)
    if not write_allowed:
        logger.info("[DRY-RUN] Would deactivate %s", args.person_slug)
        return 0
        
    if db.deactivate_person(args.person_slug):
        logger.info("Deactivated person: %s", args.person_slug)
    else:
        logger.warning("Person not found or already inactive: %s", args.person_slug)
    return 0

def cmd_rebuild(args, config, db: ArchiveDatabase, logger: logging.Logger):
    if not OPENCV_AVAILABLE:
        logger.error("Configuration error: Face processing dependency unavailable: install the Phase 5 requirements.")
        return 1

    try:
        engine = get_engine(config=config, logger=logger)
    except FaceEngineError as e:
        logger.error("Rebuild failed: %s", e)
        return 1

    write_allowed = check_write_permission(args, config, logger)

    person = db.find_person_by_slug(args.person_slug)
    if not person or not person["active"]:
        logger.error("Person not found or inactive: %s", args.person_slug)
        return 1
        
    person_id = person["person_id"]
    
    try:
        ref_root = config.faces.reference_root.resolve(strict=True)
    except Exception:
        logger.error("Reference root does not exist: %s", config.faces.reference_root)
        return 1
        
    person_folder = Path(config.faces.reference_root) / args.person_slug
    try:
        person_folder = person_folder.resolve(strict=True)
    except Exception:
        logger.error("Person folder does not exist: %s", person_folder)
        return 1
        
    if not person_folder.is_dir():
        logger.error("Person folder is not a directory: %s", person_folder)
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
    
    logger.info("Discovered references: %s", len(discovered_files))
    
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
            logger.debug("Duplicate file: %s", img_path)
            fail_count += 1
            continue
        seen_hashes.add(file_hash)
        
        import cv2
        image = cv2.imread(str(img_path))
        if image is None:
            planned_rejected.append((str(img_path), file_hash, "UNREADABLE", "OpenCV imread failed"))
            logger.warning("Rejected reference: UNREADABLE")
            logger.debug("Unreadable image: %s", img_path)
            fail_count += 1
            continue
            
        faces = engine.detect_faces(image)
        if len(faces) == 0:
            planned_rejected.append((str(img_path), file_hash, "NO_FACE", "No face detected"))
            logger.warning("Rejected reference: NO_FACE")
            logger.debug("No face detected: %s", img_path)
            fail_count += 1
            continue
        if len(faces) > 1:
            planned_rejected.append((str(img_path), file_hash, "MULTIPLE_FACES", "Multiple faces detected"))
            logger.warning("Rejected reference: MULTIPLE_FACES")
            logger.debug("Multiple faces detected: %s", img_path)
            fail_count += 1
            continue
            
        face = faces[0]
        confidence = float(face[-1])
        w, h = int(face[2]), int(face[3])
        
        min_side = min(w, h)
        if min_side < config.faces.minimum_face_size_px:
            planned_rejected.append((str(img_path), file_hash, "TINY_FACE", f"Face {w}x{h} below minimum size"))
            logger.warning("Rejected reference: TINY_FACE")
            logger.debug("Tiny face: %s", img_path)
            fail_count += 1
            continue
            
        try:
            aligned = engine.align_face(image, face)
            embedding = engine.create_embedding(aligned)
        except FaceEngineError as e:
            planned_rejected.append((str(img_path), file_hash, "ENGINE_ERROR", str(e)))
            logger.warning("Rejected reference: ENGINE_ERROR")
            logger.debug("Engine error on %s: %s", img_path, e)
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
        logger.info("Insufficient accepted references: %s found, %s required.", success_count, config.faces.minimum_references_per_person)
        if write_allowed:
            return 1
            
    if not write_allowed:
        logger.info("Accepted references: %s", success_count)
        logger.info("Rejected references: %s", fail_count)
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
        logger.error("Rebuild transaction failed: %s", e)
        return 1

    logger.info("Accepted references: %s", success_count)
    logger.info("Rejected references: %s", fail_count)
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
        logger.error("Calibration failed: %s", e)
        return 1
        
    write_allowed = check_write_permission(args, config, logger)
    model_identity = engine.model_identity()
    
    negatives_dir = Path(args.negatives_dir) if args.negatives_dir else None
    calibration_negatives = []
    holdout_negatives = []
    
    if negatives_dir:
        calib_dir = negatives_dir / "calibration"
        holdout_dir = negatives_dir / "holdout"
        
        if calib_dir.exists():
            for p in calib_dir.iterdir():
                if p.is_file():
                    calibration_negatives.append(p)
                    
        if holdout_dir.exists():
            for p in holdout_dir.iterdir():
                if p.is_file():
                    holdout_negatives.append(p)
    
    from src.image_utils import decode_image_with_exif
    
    def extract_negative_embeddings(paths):
        embeddings = []
        for path in paths:
            try:
                img_info = decode_image_with_exif(str(path))
                faces = engine.detect_faces(img_info["image"])
                for face in faces:
                    w = face[2]
                    h = face[3]
                    min_side = min(w, h)
                    if min_side < config.faces.minimum_face_size_px:
                        continue
                    aligned = engine.align_face(img_info["image"], face)
                    emb = engine.create_embedding(aligned)
                    embeddings.append((emb, str(path)))
            except Exception as e:
                logger.debug("Failed to extract negative from %s: %s", path, e)
        return embeddings

    logger.info("Extracting negative embeddings...")
    calib_neg_embs = extract_negative_embeddings(calibration_negatives)
    holdout_neg_embs = extract_negative_embeddings(holdout_negatives)
    logger.info("Found %s calibration negative faces and %s holdout negative faces.", len(calib_neg_embs), len(holdout_neg_embs))
    
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
            logger.error("Person %s has only %s references (minimum %s).", p['person_slug'], count, config.faces.minimum_references_per_person)
            return 1
            
    from src.hashing import get_reference_set_hash, get_calibration_scope_hash
    base_ref_hash = get_reference_set_hash(ref_hashes)
    ref_set_hash = get_calibration_scope_hash(model_identity, base_ref_hash, config.faces.policy_identity)
    
    # Generate scores
    positive_aggregate_scores = []
    positive_individual_scores = []
    negative_aggregate_scores = []
    
    top_k = config.faces.aggregate_top_k
    
    pids = list(person_refs.keys())
    for i in range(len(pids)):
        refs_A = person_refs[pids[i]]
        
        # Positive pairs (LOOCV)
        for r_test in refs_A:
            e_test = np.frombuffer(r_test["embedding_blob"], dtype=np.float32)
            
            # Scores against other references of the SAME person
            same_person_scores = []
            for r_ref in refs_A:
                # Exclude exact same reference ID and same file hash
                if r_test["reference_id"] == r_ref["reference_id"]:
                    continue
                if r_test["source_sha256"] == r_ref["source_sha256"]:
                    continue
                
                e_ref = np.frombuffer(r_ref["embedding_blob"], dtype=np.float32)
                score = engine.compare_embeddings(e_test, e_ref)
                same_person_scores.append(score)
                positive_individual_scores.append(score)
                
            if len(same_person_scores) > 0:
                sorted_scores = sorted(same_person_scores, reverse=True)
                top_scores = sorted_scores[:min(top_k, len(sorted_scores))]
                agg_score = sum(top_scores) / len(top_scores)
                positive_aggregate_scores.append(agg_score)
                
            # Negative pairs against OTHER enrolled people
            for j in range(len(pids)):
                if i == j: continue
                refs_B = person_refs[pids[j]]
                other_person_scores = []
                for r_ref in refs_B:
                    e_ref = np.frombuffer(r_ref["embedding_blob"], dtype=np.float32)
                    score = engine.compare_embeddings(e_test, e_ref)
                    other_person_scores.append(score)
                
                if len(other_person_scores) > 0:
                    sorted_scores = sorted(other_person_scores, reverse=True)
                    top_scores = sorted_scores[:min(top_k, len(sorted_scores))]
                    agg_score = sum(top_scores) / len(top_scores)
                    negative_aggregate_scores.append(agg_score)
                    
            # Negative pairs against CALIBRATION unknowns
            # For each unknown face, we treat it as a query against this person's references
            # Or we treat the known reference as a query against... wait, the unknown is the query.
            pass
            
    # Now use calibration negatives as queries against all enrolled people
    for neg_emb, neg_path in calib_neg_embs:
        for pid in pids:
            refs = person_refs[pid]
            scores = []
            for r_ref in refs:
                e_ref = np.frombuffer(r_ref["embedding_blob"], dtype=np.float32)
                score = engine.compare_embeddings(neg_emb, e_ref)
                scores.append(score)
                
            if len(scores) > 0:
                sorted_scores = sorted(scores, reverse=True)
                top_scores = sorted_scores[:min(top_k, len(sorted_scores))]
                agg_score = sum(top_scores) / len(top_scores)
                negative_aggregate_scores.append(agg_score)

    if not positive_aggregate_scores or not negative_aggregate_scores:
        logger.error("Insufficient pairs to calibrate.")
        return 1
        
    max_neg_agg = max(negative_aggregate_scores)
    min_pos_agg = min(positive_aggregate_scores)
    
    # We want conservative: accept threshold must be higher than all negative aggregates
    aggregate_accept_threshold = max_neg_agg + 0.05
    aggregate_review_threshold = max_neg_agg + 0.01
    minimum_aggregate_margin = 0.05
    
    # Enforce bounds
    if aggregate_accept_threshold >= 1.0:
        aggregate_accept_threshold = 0.99
    if aggregate_review_threshold >= aggregate_accept_threshold:
        aggregate_review_threshold = aggregate_accept_threshold - 0.01
        
    # Calibrate individual strong support threshold
    # Look at the distribution of individual positive scores that contributed to matches
    if positive_individual_scores:
        # A simple heuristic: the strong support threshold shouldn't be so high that 
        # legitimate positive references fail to meet it. 
        # We can set it to the 10th percentile of positive individual scores, or 
        # bounded above max individual negative score (which we didn't explicitly track, 
        # but we can approximate it or use the aggregate accept threshold as a floor)
        individual_strong_support_threshold = aggregate_accept_threshold
    else:
        individual_strong_support_threshold = aggregate_accept_threshold
        
    # Holdout evaluation
    holdout_false_matches = 0
    holdout_errors = 0
    highest_false_agg = -1.0
    
    for neg_emb, neg_path in holdout_neg_embs:
        for pid in pids:
            refs = person_refs[pid]
            scores = []
            for r_ref in refs:
                e_ref = np.frombuffer(r_ref["embedding_blob"], dtype=np.float32)
                score = engine.compare_embeddings(neg_emb, e_ref)
                scores.append(score)
                
            if len(scores) > 0:
                sorted_scores = sorted(scores, reverse=True)
                top_scores = sorted_scores[:min(top_k, len(sorted_scores))]
                agg_score = sum(top_scores) / len(top_scores)
                
                support_at_strong = sum(1 for s in scores if s >= individual_strong_support_threshold)
                
                if agg_score > highest_false_agg:
                    highest_false_agg = agg_score
                    
                if agg_score >= aggregate_accept_threshold and support_at_strong >= config.faces.minimum_strong_support:
                    # We don't have a second-best person in this loop, so margin is just agg_score.
                    # Since margin requirement is agg_score >= minimum_aggregate_margin (usually 0.05),
                    # if agg_score is e.g. 0.8, it will easily pass the margin check.
                    if agg_score >= minimum_aggregate_margin:
                        holdout_false_matches += 1
                        logger.error(
                            "Holdout failure: unknown negative produced a known match: "
                            "aggregate_score=%.4f support=%s",
                            float(agg_score),
                            support_at_strong,
                        )
                        log_private(
                            logger,
                            getattr(args, "verbose_private", False),
                            "Holdout failure private details: path=%r person_id=%s",
                            str(neg_path),
                            pid,
                        )
        
    report = {
        "positive_aggregate_pairs": len(positive_aggregate_scores),
        "negative_aggregate_pairs": len(negative_aggregate_scores),
        "max_negative_aggregate": max_neg_agg,
        "min_positive_aggregate": min_pos_agg,
        "proposed_aggregate_accept": aggregate_accept_threshold,
        "proposed_aggregate_review": aggregate_review_threshold,
        "proposed_aggregate_margin": minimum_aggregate_margin,
        "proposed_individual_strong_support": individual_strong_support_threshold,
        "holdout_faces": len(holdout_neg_embs),
        "holdout_false_matches": holdout_false_matches,
        "highest_false_aggregate": highest_false_agg
    }
    
    logger.info("Calibration proposed: Accept=%.3f, Review=%.3f, Margin=%.3f", aggregate_accept_threshold, aggregate_review_threshold, minimum_aggregate_margin)
    logger.info("Holdout evaluation: %s false matches on %s faces.", holdout_false_matches, len(holdout_neg_embs))
    
    if holdout_false_matches > 0 and not args.allow_failed_holdout:
        logger.error("Calibration failed holdout evaluation. Refusing to activate.")
        return 1
    
    if not write_allowed:
        logger.info("[DRY-RUN] Would activate this calibration.")
    else:
        db.activate_calibration(
            model_identity, ref_set_hash, aggregate_accept_threshold, aggregate_review_threshold, minimum_aggregate_margin, 
            individual_strong_support_threshold, len(positive_aggregate_scores), len(negative_aggregate_scores), json.dumps(report)
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
    p_calibrate.add_argument("--negatives-dir", help="Path to directory containing 'calibration' and 'holdout' unknown faces")
    p_calibrate.add_argument("--allow-failed-holdout", action="store_true", help="Allow calibration to be saved even if it fails holdout validation")
    
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
