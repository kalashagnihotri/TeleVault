import time
import hashlib
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import math

from src.config import Config
from src.database import ArchiveDatabase
from src.face_engine import Cv2FaceEngine, OPENCV_AVAILABLE, FaceEngineError
from src.image_utils import decode_image_with_exif
from src.models import ImageFaceAnalysisResult


def _to_float(score) -> float:
    try:
        import numpy as np
        if isinstance(score, np.ndarray):
            if score.size != 1:
                raise ValueError(f"Score array has size {score.size}, expected 1")
            val = float(score.item())
        else:
            val = float(score)
            
        if math.isnan(val) or math.isinf(val):
            raise ValueError(f"Score is not finite: {val}")
            
        return val
    except ImportError:
        val = float(score)
        if math.isnan(val) or math.isinf(val):
            raise ValueError(f"Score is not finite: {val}")
        return val


class FaceAnalysisWorker:
    def __init__(self, config: Config, database: ArchiveDatabase, engine, logger: logging.Logger):
        self.config = config
        self.db = database
        self.engine = engine
        self.logger = logger
        
        self.ref_snapshot = None
        self.calibration_snapshot = None
        self.snapshots_loaded = False
        
    def load_snapshots(self) -> None:
        if self.snapshots_loaded or self.engine is None:
            return
            
        model_identity = self.engine.model_identity()
        raw_refs = self.db.get_active_references(model_identity)
        
        import numpy as np
        
        valid_refs = []
        ref_hashes = []
        for r in raw_refs:
            blob = r["embedding_blob"]
            try:
                emb = np.frombuffer(blob, dtype=np.float32).copy()
                if emb.size != r["embedding_dimension"]:
                    raise ValueError(f"Embedding size {emb.size} != {r['embedding_dimension']}")
                if not np.isfinite(emb).all():
                    raise ValueError("Embedding contains non-finite values")
                norm = np.linalg.norm(emb)
                if not np.isfinite(norm) or norm == 0:
                    raise ValueError("Embedding norm is invalid")
                
                emb = emb.flatten()
                
                valid_refs.append({
                    "person_id": r["person_id"],
                    "embedding": emb,
                    "source_sha256": r["source_sha256"]
                })
                ref_hashes.append(r["source_sha256"])
            except Exception as e:
                self.logger.debug(f"Invalid reference {r['reference_id']}: {e}", exc_info=True)
                
        self.ref_snapshot = valid_refs
        
        ref_hashes.sort()
        ref_set_hash = hashlib.sha256("".join(ref_hashes).encode()).hexdigest() if ref_hashes else "empty"
        
        calib = self.db.get_active_calibration(model_identity, ref_set_hash)
        if calib:
            try:
                acc = _to_float(calib["accept_threshold"])
                rev = _to_float(calib["review_threshold"])
                marg = _to_float(calib["minimum_margin"])
                if not (0 <= rev < acc <= 1):
                    raise ValueError(f"Invalid thresholds: review={rev}, accept={acc}")
                if marg <= 0:
                    raise ValueError(f"Invalid minimum margin: {marg}")
                
                self.calibration_snapshot = dict(calib)
                self.calibration_snapshot["accept_threshold"] = acc
                self.calibration_snapshot["review_threshold"] = rev
                self.calibration_snapshot["minimum_margin"] = marg
            except Exception as e:
                self.logger.debug(f"Invalid calibration data: {e}", exc_info=True)
                self.calibration_snapshot = "INVALID"
        else:
            self.calibration_snapshot = None
            
        self.snapshots_loaded = True

    def _generate_analysis_key(self) -> tuple[str, int]:
        version = 2
        if not self.calibration_snapshot or self.calibration_snapshot == "INVALID":
            return ("UNCALIBRATED", version)
        return ("CALIBRATED", version)

    def analyze_image(self, image, short_hash="unknown") -> ImageFaceAnalysisResult:
        res = ImageFaceAnalysisResult()
        
        if self.calibration_snapshot == "INVALID":
            res.stage = "CALIBRATION_LOAD"
            res.error_code = "ValueError"
            return res
            
        stage = "DETECTION"
        try:
            raw_faces = self.engine.detect_faces(image)
            res.raw_detections = len(raw_faces)
            
            # Log raw metrics
            raw_scores = [round(float(f[-1]), 4) for f in raw_faces] if res.raw_detections > 0 else []
            raw_boxes = [f"{int(f[2])}x{int(f[3])}" for f in raw_faces] if res.raw_detections > 0 else []
            self.logger.info(
                f"Candidate {short_hash} detections raw: "
                f"raw_detections={res.raw_detections}, "
                f"raw_scores={raw_scores}, "
                f"raw_box_sizes={raw_boxes}"
            )
            
        except Exception as e:
            res.stage = stage
            res.error_code = type(e).__name__
            self.logger.debug("Face analysis traceback for candidate", exc_info=True)
            return res
            
        accepted_faces = []
        for idx, face in enumerate(raw_faces):
            try:
                confidence = _to_float(face[-1])
                w, h = int(face[2]), int(face[3])
                
                if w < self.config.faces.minimum_face_size_px or h < self.config.faces.minimum_face_size_px:
                    res.ignored_tiny += 1
                    res.face_results.append({
                        "face_index": idx,
                        "bounding_box_json": json.dumps({"x": int(face[0]), "y": int(face[1]), "w": w, "h": h}),
                        "detector_confidence": confidence,
                        "decision": "IGNORED_TINY"
                    })
                    continue
                    
                res.accepted_size += 1
                accepted_faces.append((idx, face, confidence, w, h))
            except Exception as e:
                res.processing_errors += 1
                self.logger.debug("Face analysis traceback for candidate size check", exc_info=True)
                pass
                
        # Log filtered metrics
        self.logger.info(
            f"Candidate {short_hash} detections filtered: "
            f"accepted_size={res.accepted_size}, "
            f"ignored_tiny={res.ignored_tiny}, "
            f"processing_errors={res.processing_errors}"
        )
                
        for idx, face, confidence, w, h in accepted_faces:
            try:
                stage = "ALIGNMENT"
                
                aligned = self.engine.align_face(image, face)
                
                stage = "EMBEDDING"
                embedding = self.engine.create_embedding(aligned)
                
                stage = "MATCHING"
                best_person_id = None
                best_score = -1.0
                second_best_person_id = None
                second_best_score = -1.0
                
                decision = "UNKNOWN_UNCALIBRATED"
                score_margin = 0.0
                supporting_count = 0
                
                if self.calibration_snapshot:
                    scores_by_person = {}
                    for ref in self.ref_snapshot:
                        pid = ref["person_id"]
                        score = self.engine.compare_embeddings(embedding, ref["embedding"])
                        score = _to_float(score)
                        if pid not in scores_by_person:
                            scores_by_person[pid] = []
                        scores_by_person[pid].append(score)
                        
                    person_max_scores = {pid: max(scores) for pid, scores in scores_by_person.items()}
                    sorted_people = sorted(person_max_scores.items(), key=lambda x: x[1], reverse=True)
                    
                    if len(sorted_people) > 0:
                        best_person_id = sorted_people[0][0]
                        best_score = sorted_people[0][1]
                        
                    if len(sorted_people) > 1:
                        second_best_person_id = sorted_people[1][0]
                        second_best_score = sorted_people[1][1]
                        score_margin = best_score - second_best_score
                    elif len(sorted_people) == 1:
                        score_margin = best_score
                        
                    if best_score >= self.calibration_snapshot["accept_threshold"]:
                        if score_margin >= self.calibration_snapshot["minimum_margin"]:
                            supporting_count = sum(1 for s in scores_by_person[best_person_id] if s >= self.calibration_snapshot["review_threshold"])
                            if supporting_count >= self.config.faces.minimum_supporting_references:
                                decision = "KNOWN_MATCH"
                                res.accepted_faces += 1
                            else:
                                decision = "UNKNOWN_AMBIGUOUS"
                                res.unknown_faces += 1
                        else:
                            decision = "UNKNOWN_AMBIGUOUS"
                            res.unknown_faces += 1
                    elif best_score >= self.calibration_snapshot["review_threshold"]:
                        decision = "UNKNOWN_LOW_SCORE"
                        res.unknown_faces += 1
                    else:
                        decision = "UNKNOWN_LOW_SCORE"
                        res.unknown_faces += 1
                else:
                    decision = "UNKNOWN_UNCALIBRATED"
                    res.unknown_faces += 1
                    
                res.face_results.append({
                    "face_index": idx,
                    "bounding_box_json": json.dumps({"x": int(face[0]), "y": int(face[1]), "w": w, "h": h}),
                    "detector_confidence": confidence,
                    "embedding_blob": embedding.tobytes(),
                    "embedding_dimension": embedding.size,
                    "model_identity": self.engine.model_identity(),
                    "best_person_id": best_person_id,
                    "best_score": float(best_score) if best_score >= 0 else None,
                    "second_best_person_id": second_best_person_id,
                    "second_best_score": float(second_best_score) if second_best_score >= 0 else None,
                    "score_margin": float(score_margin),
                    "supporting_reference_count": supporting_count,
                    "decision": decision
                })
                
            except Exception as e:
                res.processing_errors += 1
                self.logger.debug("Face analysis traceback for candidate face", exc_info=True)
                res.face_results.append({
                    "face_index": idx,
                    "bounding_box_json": json.dumps({"x": int(face[0]), "y": int(face[1]), "w": w, "h": h}),
                    "detector_confidence": confidence,
                    "decision": "ANALYSIS_ERROR",
                    "error_stage": stage,
                    "error_code": type(e).__name__
                })
                continue
                
        if len(res.face_results) != res.raw_detections:
            res.stage = "RESULT_ASSEMBLY"
            res.error_code = "MISSING_FACE_RESULT"
            
        return res

    def analyze_candidates(self, candidates: list) -> None:
        if not self.config.faces.enabled or self.engine is None:
            return
            
        self.logger.info("Starting face analysis.")
        valid_candidates = [c for c in candidates if c.media_type == "image" and not c.is_duplicate]
        valid_candidates.sort(key=lambda c: str(c.path).lower())
        
        self.logger.info(f"Face-analysis candidates: {len(valid_candidates)}.")
        if not valid_candidates:
            self.logger.info("Finished face analysis.")
            return
            
        self.load_snapshots()
        
        for idx, candidate in enumerate(valid_candidates, start=1):
            short_hash = candidate.sha256[:8] if candidate.sha256 else "unknown"
            log_prefix = f"Candidate {idx} [{short_hash}]: "
            
            stage = "DECODE"
            try:
                img_info = decode_image_with_exif(str(candidate.path))
                image = img_info["image"]
                
                res = self.analyze_image(image, short_hash=short_hash)
                
                completed_faces = res.accepted_faces + res.unknown_faces
                self.logger.info(
                    f"Candidate {short_hash} processing complete: "
                    f"raw_detections={res.raw_detections} "
                    f"accepted_size={res.accepted_size} "
                    f"ignored_tiny={res.ignored_tiny} "
                    f"completed_faces={completed_faces} "
                    f"known_faces={res.accepted_faces} "
                    f"unknown_faces={res.unknown_faces} "
                    f"processing_errors={res.processing_errors} "
                    f"result_rows={len(res.face_results)}"
                )
                
                if res.stage != "SUCCESS":
                    self.logger.info(f"{log_prefix}decision=ANALYSIS_ERROR stage={res.stage} error={res.error_code}")
                    self.logger.error(f"Face analysis failed for candidate {short_hash}: stage={res.stage} error={res.error_code}")
                elif res.raw_detections == 0:
                    self.logger.info(f"{log_prefix}faces=0, decision=NO_FACE")
                elif res.raw_detections > 0 and res.accepted_size == 0 and res.ignored_tiny > 0:
                    self.logger.info(f"{log_prefix}faces=0, decision=IGNORED_TINY")
                elif res.accepted_size > 0 and completed_faces == 0 and res.processing_errors > 0:
                    self.logger.info(f"{log_prefix}faces=0, decision=ANALYSIS_ERROR")
                elif completed_faces > 0 and res.processing_errors > 0:
                    self.logger.info(f"{log_prefix}faces={completed_faces}, decision=PARTIAL_ANALYSIS")
                elif completed_faces > 0 and res.processing_errors == 0:
                    if len(res.face_results) == 1:
                        self.logger.info(f"{log_prefix}faces=1, decision={res.face_results[0]['decision']}")
                    else:
                        self.logger.info(f"{log_prefix}faces={completed_faces}, accepted={res.accepted_faces}, unknown={res.unknown_faces}")
                        
            except Exception as e:
                self.logger.info(f"{log_prefix}decision=ANALYSIS_ERROR stage={stage} error={type(e).__name__}")
                self.logger.error(f"Face analysis failed for candidate {short_hash}: stage={stage} error={type(e).__name__}")
                self.logger.debug(f"Face analysis traceback for candidate {short_hash}", exc_info=True)
                
        self.logger.info("Finished face analysis.")

    def analyze_pending(self) -> None:
        if not self.config.faces.enabled or self.engine is None:
            return
            
        pending = self.db.get_pending_face_analysis(limit=10)
        if not pending:
            return
            
        self.load_snapshots()
        analysis_key, analysis_version = self._generate_analysis_key()
        
        model_identity = self.engine.model_identity()
        ref_set_hash = hashlib.sha256("".join(sorted([r["source_sha256"] for r in (self.ref_snapshot or [])]))).hexdigest() if self.ref_snapshot else "empty"
        calib_id = self.calibration_snapshot["calibration_id"] if self.calibration_snapshot and self.calibration_snapshot != "INVALID" else None
        
        for media in pending:
            media_id = media["id"]
            original_path = Path(media["original_path"])
            short_hash = media.get("short_hash", str(media_id))
            
            if not original_path.exists():
                self.db.record_face_analysis_failure(media_id, -1, "SOURCE_MISSING", f"File missing", "FAILED")
                continue
                
            if original_path.suffix.lower() in [".mp4", ".mov", ".mkv"]:
                if not self.config.faces.analyze_videos:
                    self.db.record_face_analysis_failure(media_id, -1, "VIDEO_SKIPPED", "Video analysis disabled", "NO_FACE")
                    continue
                else:
                    self.db.record_face_analysis_failure(media_id, -1, "VIDEO_UNSUPPORTED", "Video analysis not yet implemented", "FAILED")
                    continue
                    
            attempt_id = self.db.start_face_analysis_attempt(
                media_id, analysis_key, analysis_version, model_identity, ref_set_hash, calib_id
            )
            
            stage = "DECODE"
            try:
                img_info = decode_image_with_exif(str(original_path))
                image = img_info["image"]
                
                res = self.analyze_image(image, short_hash=short_hash)
                
                completed_faces = res.accepted_faces + res.unknown_faces
                self.logger.info(
                    f"Candidate {short_hash} processing complete: "
                    f"raw_detections={res.raw_detections} "
                    f"accepted_size={res.accepted_size} "
                    f"ignored_tiny={res.ignored_tiny} "
                    f"completed_faces={completed_faces} "
                    f"known_faces={res.accepted_faces} "
                    f"unknown_faces={res.unknown_faces} "
                    f"processing_errors={res.processing_errors} "
                    f"result_rows={len(res.face_results)}"
                )
                
                if res.stage != "SUCCESS":
                    self.db.record_face_analysis_failure(media_id, attempt_id, f"ANALYSIS_ERROR", f"stage={res.stage} error={res.error_code}", "FAILED")
                    self.logger.error(f"Face analysis failed for candidate {short_hash}: stage={res.stage} error={res.error_code}")
                elif res.raw_detections == 0:
                    self.logger.info(f"{log_prefix}faces=0, decision=NO_FACE")
                    self.db.record_face_analysis_success(media_id, attempt_id, res.face_results)
                elif res.raw_detections > 0 and res.accepted_size == 0 and res.ignored_tiny > 0:
                    self.logger.info(f"{log_prefix}faces=0, decision=IGNORED_TINY")
                    self.db.record_face_analysis_success(media_id, attempt_id, res.face_results)
                elif res.accepted_size > 0 and completed_faces == 0 and res.processing_errors > 0:
                    self.logger.info(f"{log_prefix}faces=0, decision=ANALYSIS_ERROR")
                    self.db.record_face_analysis_failure(media_id, attempt_id, f"ANALYSIS_ERROR", f"stage=RESULT_ASSEMBLY error=ALL_FACES_FAILED", "FAILED")
                elif completed_faces > 0 and res.processing_errors > 0:
                    self.logger.info(f"{log_prefix}faces={completed_faces}, decision=PARTIAL_ANALYSIS")
                    self.db.record_face_analysis_success(media_id, attempt_id, res.face_results)
                elif completed_faces > 0 and res.processing_errors == 0:
                    if len(res.face_results) == 1:
                        self.logger.info(f"{log_prefix}faces=1, decision={res.face_results[0]['decision']}")
                    else:
                        self.logger.info(f"{log_prefix}faces={completed_faces}, accepted={res.accepted_faces}, unknown={res.unknown_faces}")
                    self.db.record_face_analysis_success(media_id, attempt_id, res.face_results)
                    
            except Exception as e:
                self.logger.error(f"Face analysis failed for candidate {short_hash}: stage={stage} error={type(e).__name__}")
                self.logger.debug(f"Face analysis traceback for candidate {short_hash}", exc_info=True)
                self.db.record_face_analysis_failure(media_id, attempt_id, f"ANALYSIS_ERROR", f"stage={stage} error={type(e).__name__}", "FAILED")
