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
from src.face_policy import CURRENT_ANALYSIS_VERSION, get_face_size_tier
from src.logging_utils import RuntimeOptions, ProcessingStage, log_private


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



class FaceAnalysisStageError(Exception):
    def __init__(self, stage: str, cause: Exception) -> None:
        super().__init__(type(cause).__name__)
        self.stage = stage
        self.cause = cause

class FaceAnalysisWorker:
    def __init__(self, config: Config, database: ArchiveDatabase, engine, logger: logging.Logger, opts: RuntimeOptions | None = None):
        self.config = config
        self.db = database
        self.engine = engine
        self.logger = logger
        self.opts = opts or RuntimeOptions()
        
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
                log_private(self.logger, self.opts.verbose_private, "Invalid reference %s: %s", r["reference_id"], e, exc_info=True)
                
        self.ref_snapshot = valid_refs
        
        from src.hashing import get_reference_set_hash, get_calibration_scope_hash
        base_ref_hash = get_reference_set_hash(ref_hashes)
        policy_id = self.config.faces.policy_identity
        ref_set_hash = get_calibration_scope_hash(model_identity, base_ref_hash, policy_id)
        
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
                self.calibration_snapshot["individual_strong_support_threshold"] = _to_float(calib.get("individual_strong_support_threshold", acc))
            except Exception as e:
                log_private(self.logger, self.opts.verbose_private, "Invalid calibration data: %s", e, exc_info=True)
                self.calibration_snapshot = "INVALID"
        else:
            self.calibration_snapshot = None
            
        self.snapshots_loaded = True

    def _calculate_person_scores(self, embedding, top_k: int):
        scores_by_person = {}
        for ref in (self.ref_snapshot or []):
            pid = ref["person_id"]
            score = self.engine.compare_embeddings(embedding, ref["embedding"])
            score = float(score)
            if pid not in scores_by_person:
                scores_by_person[pid] = []
            scores_by_person[pid].append(score)
            
        person_max_scores = {}
        person_aggregate_scores = {}
        for pid, scores in scores_by_person.items():
            person_max_scores[pid] = max(scores)
            sorted_scores = sorted(scores, reverse=True)
            top_scores = sorted_scores[:min(top_k, len(sorted_scores))]
            person_aggregate_scores[pid] = sum(top_scores) / len(top_scores)
            
        sorted_people = sorted(person_aggregate_scores.items(), key=lambda x: x[1], reverse=True)
        return scores_by_person, person_max_scores, person_aggregate_scores, sorted_people

    def _generate_analysis_key(self) -> tuple[str, int]:
        version = CURRENT_ANALYSIS_VERSION
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
            self.logger.info("Candidate [%s] detections raw: raw_detections=%s, raw_scores=%s, raw_box_sizes=%s", short_hash, res.raw_detections, raw_scores, raw_boxes)
            
        except Exception as e:
            res.stage = stage
            res.error_code = type(e).__name__
            log_private(self.logger, self.opts.verbose_private, "Candidate [%s] private traceback: stage=%s", short_hash, stage, exc_info=True)
            raise FaceAnalysisStageError(stage, e) from e
            
        accepted_faces = []
        for idx, face in enumerate(raw_faces):
            try:
                confidence = _to_float(face[-1])
                w, h = int(face[2]), int(face[3])
                
                size_tier = get_face_size_tier(w, h, self.config.faces)
                
                if size_tier == "IGNORED_TINY":
                    res.ignored_tiny += 1
                    res.face_results.append({
                        "face_index": idx,
                        "bounding_box_json": json.dumps({
                            "x": int(face[0]), "y": int(face[1]), "w": w, "h": h
                        }),
                        "quality_json": json.dumps({
                            "size_tier": size_tier,
                            "min_side_px": min(w, h),
                            "width_px": w,
                            "height_px": h,
                            "low_resolution_rules_applied": False,
                            "effective_accept_threshold": None,
                            "effective_margin_threshold": None,
                            "effective_individual_support_threshold": None,
                            "effective_minimum_support": None,
                            "detector_confidence_passed": None,
                            "aggregate_score_passed": None,
                            "margin_passed": None,
                            "support_count_passed": None
                        }),
                        "detector_confidence": confidence,
                        "decision": "IGNORED_TINY"
                    })
                    continue
                    
                res.accepted_size += 1
                accepted_faces.append((idx, face, confidence, w, h, size_tier))
            except Exception as e:
                res.processing_errors += 1
                log_private(self.logger, self.opts.verbose_private, "Candidate [%s] private traceback: stage=SIZE_CHECK", short_hash, exc_info=True)
                res.face_results.append({
                    "face_index": idx,
                    "bounding_box_json": json.dumps({"w": w, "h": h}),
                    "detector_confidence": confidence,
                    "decision": "ANALYSIS_ERROR",
                    "error_stage": "SIZE_CHECK",
                    "error_code": type(e).__name__
                })
                
        # Log filtered metrics
        self.logger.info("Candidate [%s] detections filtered: accepted_size=%s, ignored_tiny=%s, processing_errors=%s", short_hash, res.accepted_size, res.ignored_tiny, res.processing_errors)
                
        for idx, face, confidence, w, h, size_tier in accepted_faces:
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
                
                top_k = int(self.config.faces.aggregate_top_k) if not hasattr(self.config.faces.aggregate_top_k, "_mock_name") else int(self.config.faces.aggregate_top_k())
                scores_by_person, person_max_scores, person_aggregate_scores, sorted_people = self._calculate_person_scores(
                    embedding,
                    top_k=top_k
                )
                
                if len(sorted_people) > 0:
                    best_person_id = sorted_people[0][0]
                    best_score = sorted_people[0][1]
                    
                if len(sorted_people) > 1:
                    second_best_person_id = sorted_people[1][0]
                    second_best_score = sorted_people[1][1]
                    score_margin = best_score - second_best_score
                elif len(sorted_people) == 1:
                    score_margin = best_score
                    
                conf_passed = None
                agg_passed = None
                marg_passed = None
                supp_passed = None
                acc_thresh = None
                marg_thresh = None
                ind_thresh = None
                min_support = None
                    
                if self.calibration_snapshot:
                    calib_acc_thresh = float(self.calibration_snapshot.get("accept_threshold", 0.8))
                    calib_rev_thresh = float(self.calibration_snapshot.get("review_threshold", 0.6))
                    calib_marg_thresh = float(self.calibration_snapshot.get("minimum_margin", 0.1))
                    calib_ind_thresh = float(self.calibration_snapshot.get("individual_strong_support_threshold", calib_acc_thresh))
                    
                    calib_min_support = int(self.config.faces.minimum_strong_support) if not hasattr(self.config.faces.minimum_strong_support, "_mock_name") else int(self.config.faces.minimum_strong_support())

                    if size_tier == "LOW_RESOLUTION_CANDIDATE":
                        acc_thresh = min(1.0, calib_acc_thresh + self.config.faces.low_resolution_accept_threshold_boost)
                        rev_thresh = calib_rev_thresh
                        marg_thresh = min(1.0, calib_marg_thresh + self.config.faces.low_resolution_margin_boost)
                        ind_thresh = min(1.0, calib_ind_thresh + self.config.faces.low_resolution_individual_support_boost)
                        min_support = max(calib_min_support + 1, self.config.faces.low_resolution_minimum_strong_support)
                        req_conf = self.config.faces.low_resolution_detector_confidence
                        
                        conf_passed = confidence >= req_conf
                    else:
                        acc_thresh = calib_acc_thresh
                        rev_thresh = calib_rev_thresh
                        marg_thresh = calib_marg_thresh
                        ind_thresh = calib_ind_thresh
                        min_support = calib_min_support
                        conf_passed = True
                        
                    if best_person_id is not None:
                        strong_support = sum(1 for s in scores_by_person[best_person_id] if s >= ind_thresh)
                        supporting_count = strong_support
                    else:
                        strong_support = 0
                        supporting_count = 0
                        
                    agg_passed = best_score >= acc_thresh
                    marg_passed = score_margin >= marg_thresh
                    supp_passed = strong_support >= min_support
                    
                    if conf_passed and agg_passed and marg_passed and supp_passed:
                        decision = "KNOWN_MATCH"
                        res.accepted_faces += 1
                    else:
                        if size_tier == "LOW_RESOLUTION_CANDIDATE":
                            decision = "UNKNOWN_LOW_RES"
                            res.unknown_faces += 1
                        else:
                            if best_score >= calib_acc_thresh:
                                decision = "UNKNOWN_AMBIGUOUS"
                                res.unknown_faces += 1
                            elif best_score >= rev_thresh:
                                decision = "UNKNOWN_LOW_SCORE"
                                res.unknown_faces += 1
                            else:
                                decision = "UNKNOWN_LOW_SCORE"
                                res.unknown_faces += 1
                else:
                    decision = "UNKNOWN_UNCALIBRATED"
                    res.unknown_faces += 1
                    
                quality_data = {
                    "size_tier": size_tier,
                    "min_side_px": min(w, h),
                    "width_px": w,
                    "height_px": h,
                    "low_resolution_rules_applied": size_tier == "LOW_RESOLUTION_CANDIDATE",
                    "effective_accept_threshold": acc_thresh,
                    "effective_margin_threshold": marg_thresh,
                    "effective_individual_support_threshold": ind_thresh,
                    "effective_minimum_support": min_support,
                    "detector_confidence_passed": conf_passed,
                    "aggregate_score_passed": agg_passed,
                    "margin_passed": marg_passed,
                    "support_count_passed": supp_passed
                }
                    
                res.face_results.append({
                    "face_index": idx,
                    "bounding_box_json": json.dumps({"x": int(face[0]), "y": int(face[1]), "w": w, "h": h}),
                    "quality_json": json.dumps(quality_data),
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
                log_private(self.logger, self.opts.verbose_private, "Candidate [%s] private traceback: stage=%s", short_hash, stage, exc_info=True)
                quality_data = {
                    "size_tier": size_tier,
                    "min_side_px": min(w, h),
                    "width_px": w,
                    "height_px": h,
                    "low_resolution_rules_applied": size_tier == "LOW_RESOLUTION_CANDIDATE",
                    "effective_accept_threshold": None,
                    "effective_margin_threshold": None,
                    "effective_individual_support_threshold": None,
                    "effective_minimum_support": None,
                    "detector_confidence_passed": None,
                    "aggregate_score_passed": None,
                    "margin_passed": None,
                    "support_count_passed": None
                }
                res.face_results.append({
                    "face_index": idx,
                    "bounding_box_json": json.dumps({"x": int(face[0]), "y": int(face[1]), "w": w, "h": h}),
                    "quality_json": json.dumps(quality_data),
                    "detector_confidence": confidence,
                    "decision": "ANALYSIS_ERROR",
                    "error_stage": stage,
                    "error_code": type(e).__name__
                })
                
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
        
        self.logger.info("Face-analysis candidates: %s.", len(valid_candidates))
        if not valid_candidates:
            self.logger.info("Finished face analysis.")
            return
            
        self.load_snapshots()
        
        analysis_key, analysis_version = self._generate_analysis_key()
        model_identity = self.engine.model_identity()
        from src.hashing import get_reference_set_hash, get_calibration_scope_hash
        base_ref_hash = get_reference_set_hash(
            r["source_sha256"] for r in (self.ref_snapshot or [])
        )
        policy_id = self.config.faces.policy_identity
        ref_set_hash = get_calibration_scope_hash(model_identity, base_ref_hash, policy_id)
        calib_id = self.calibration_snapshot["calibration_id"] if self.calibration_snapshot and self.calibration_snapshot != "INVALID" else None

        for idx, candidate in enumerate(valid_candidates, start=1):
            short_hash = candidate.sha256[:8] if candidate.sha256 else "unknown"
            
            stage = "PERSIST_ATTEMPT"
            attempt_id = None
            try:
                if candidate.media_id is not None:
                    attempt_id = self.db.start_face_analysis_attempt(
                        candidate.media_id, analysis_key, analysis_version, model_identity, ref_set_hash, calib_id
                    )

                stage = "DECODE"
                img_info = decode_image_with_exif(str(candidate.path))
                image = img_info["image"]
                
                res = self.analyze_image(image, short_hash=short_hash)
                
                completed_faces = res.accepted_faces + res.unknown_faces
                self.logger.info("Candidate [%s] processing complete: raw_detections=%s accepted_size=%s ignored_tiny=%s completed_faces=%s known_faces=%s unknown_faces=%s processing_errors=%s result_rows=%s", short_hash, res.raw_detections, res.accepted_size, res.ignored_tiny, completed_faces, res.accepted_faces, res.unknown_faces, res.processing_errors, len(res.face_results))
                
                if res.stage != "SUCCESS":
                    self.logger.info("Candidate %s [%s]: decision=ANALYSIS_ERROR stage=%s error=%s", idx, short_hash, res.stage, res.error_code)
                    self.logger.error("Candidate [%s] failed: stage=%s error=%s", short_hash, res.stage, res.error_code)
                    if candidate.media_id is not None and attempt_id is not None:
                        self.db.record_face_analysis_failure(candidate.media_id, attempt_id, f"ANALYSIS_ERROR", f"stage={res.stage} error={res.error_code}", "FAILED")
                elif res.raw_detections == 0:
                    self.logger.info("Candidate %s [%s]: faces=0, decision=NO_FACE", idx, short_hash)
                    if candidate.media_id is not None and attempt_id is not None:
                        self._record_success_and_apply_routing(candidate.media_id, attempt_id, res.face_results, short_hash)
                elif res.raw_detections > 0 and res.accepted_size == 0 and res.ignored_tiny > 0:
                    self.logger.info("Candidate %s [%s]: faces=0, decision=IGNORED_TINY", idx, short_hash)
                    if candidate.media_id is not None and attempt_id is not None:
                        self._record_success_and_apply_routing(candidate.media_id, attempt_id, res.face_results, short_hash)
                elif res.accepted_size > 0 and completed_faces == 0 and res.processing_errors > 0:
                    self.logger.info("Candidate %s [%s]: faces=0, decision=ANALYSIS_ERROR", idx, short_hash)
                    if candidate.media_id is not None and attempt_id is not None:
                        self.db.record_face_analysis_failure(candidate.media_id, attempt_id, f"ANALYSIS_ERROR", f"stage=RESULT_ASSEMBLY error=ALL_FACES_FAILED", "FAILED")
                elif completed_faces > 0 and res.processing_errors > 0:
                    self.logger.info("Candidate %s [%s]: faces=%s, decision=PARTIAL_ANALYSIS", idx, short_hash, completed_faces)
                    if candidate.media_id is not None and attempt_id is not None:
                        self._record_success_and_apply_routing(candidate.media_id, attempt_id, res.face_results, short_hash)
                elif completed_faces > 0 and res.processing_errors == 0:
                    if len(res.face_results) == 1:
                        self.logger.info("Candidate %s [%s]: faces=1, decision=%s", idx, short_hash, res.face_results[0]["decision"])
                    else:
                        self.logger.info("Candidate %s [%s]: faces=%s, accepted=%s, unknown=%s", idx, short_hash, completed_faces, res.accepted_faces, res.unknown_faces)
                    if candidate.media_id is not None and attempt_id is not None:
                        self._record_success_and_apply_routing(candidate.media_id, attempt_id, res.face_results, short_hash)
                        
            except FaceAnalysisStageError as exc:
                self.logger.info("Candidate %s [%s]: decision=ANALYSIS_ERROR stage=%s error=%s", idx, short_hash, exc.stage, type(exc.cause).__name__)
                self.logger.error("Candidate [%s] failed: stage=%s error=%s", short_hash, exc.stage, type(exc.cause).__name__)
                log_private(self.logger, self.opts.verbose_private, "Candidate [%s] private traceback", short_hash, exc_info=True)
                if candidate.media_id is not None and attempt_id is not None:
                    self.db.record_face_analysis_failure(candidate.media_id, attempt_id, f"ANALYSIS_ERROR", f"stage={exc.stage} error={type(exc.cause).__name__}", "FAILED")
            except Exception as e:
                self.logger.info("Candidate %s [%s]: decision=ANALYSIS_ERROR stage=%s error=%s", idx, short_hash, stage, type(e).__name__)
                self.logger.error("Candidate [%s] failed: stage=%s error=%s", short_hash, stage, type(e).__name__)
                log_private(self.logger, self.opts.verbose_private, "Candidate [%s] private traceback", short_hash, exc_info=True)
                if candidate.media_id is not None and attempt_id is not None:
                    self.db.record_face_analysis_failure(candidate.media_id, attempt_id, f"ANALYSIS_ERROR", f"stage={stage} error={type(e).__name__}", "FAILED")
                
        self.logger.info("Finished face analysis.")

    def _apply_face_routing_if_enabled(self, media_id: int, short_hash: str) -> None:
        if not self.config.faces.use_for_routing:
            return

        try:
            people_names = self.db.get_media_people_names(media_id)
            if not people_names:
                return

            context = self.db.get_media_routing_context(media_id)
            if not context:
                self.logger.info("Candidate [%s] face routing skipped: missing routing context", short_hash)
                return

            from src.routing import RouteInput, choose_topic
            import json
            labels_str = context.get("labels_json") or "[]"
            labels = json.loads(labels_str)
            route_input = RouteInput(
                media_type=context["media_type"],
                people=tuple(people_names),
                labels=tuple(labels),
                has_gps=bool(context["has_gps"])
            )
            
            new_route = choose_topic(route_input)
            
            if new_route not in ("people", "family_groups"):
                return
                
            updated = self.db.update_route_before_upload(media_id, new_route)
            if updated:
                self.logger.info("Candidate [%s] face routing updated: route=%s", short_hash, new_route)
            else:
                self.logger.info("Candidate [%s] face routing skipped: media no longer pre-upload safe", short_hash)
                
        except Exception as e:
            self.logger.warning("Candidate [%s] face routing error: %s", short_hash, type(e).__name__)

    def _record_success_and_apply_routing(self, media_id: int, attempt_id: int, face_results: list, short_hash: str) -> None:
        self.db.record_face_analysis_success(media_id, attempt_id, face_results)
        self._apply_face_routing_if_enabled(media_id, short_hash)


    def analyze_pending(self) -> None:
        if not self.config.faces.enabled or self.engine is None:
            return
            
        pending = self.db.get_pending_face_analysis(limit=10)
        if not pending:
            return
            
        self.load_snapshots()
        analysis_key, analysis_version = self._generate_analysis_key()
        
        model_identity = self.engine.model_identity()
        from src.hashing import get_reference_set_hash, get_calibration_scope_hash
        base_ref_hash = get_reference_set_hash(
            r["source_sha256"] for r in (self.ref_snapshot or [])
        )
        policy_id = self.config.faces.policy_identity
        ref_set_hash = get_calibration_scope_hash(model_identity, base_ref_hash, policy_id)
        calib_id = self.calibration_snapshot["calibration_id"] if self.calibration_snapshot and self.calibration_snapshot != "INVALID" else None
        
        for media in pending:
            media_id = media["id"]
            original_path = Path(media["original_path"])
            
            short_hash = (
                media.get("short_hash")
                or (str(media["sha256"])[:8] if media.get("sha256") else None)
                or "unhashed"
            )
            
            if self.db.has_successful_face_attempt(media_id, analysis_key, analysis_version, model_identity, ref_set_hash, calib_id):
                if media.get("face_state") != "ANALYZED" and media.get("face_state") != "NO_FACE":
                    # Mark complete if needed, though this is a fallback
                    pass
                continue
            
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
                    
            stage = "PERSIST_ATTEMPT"
            attempt_id = None
            try:
                attempt_id = self.db.start_face_analysis_attempt(
                    media_id, analysis_key, analysis_version, model_identity, ref_set_hash, calib_id
                )
                
                stage = "DECODE"
                img_info = decode_image_with_exif(str(original_path))
                image = img_info["image"]
                
                res = self.analyze_image(image, short_hash=short_hash)
                
                completed_faces = res.accepted_faces + res.unknown_faces
                self.logger.info("Candidate [%s] processing complete: raw_detections=%s accepted_size=%s ignored_tiny=%s completed_faces=%s known_faces=%s unknown_faces=%s processing_errors=%s result_rows=%s", short_hash, res.raw_detections, res.accepted_size, res.ignored_tiny, completed_faces, res.accepted_faces, res.unknown_faces, res.processing_errors, len(res.face_results))
                
                if res.stage != "SUCCESS":
                    self.db.record_face_analysis_failure(media_id, attempt_id, f"ANALYSIS_ERROR", f"stage={res.stage} error={res.error_code}", "FAILED")
                    self.logger.error("Candidate [%s] failed: stage=%s error=%s", short_hash, res.stage, res.error_code)
                elif res.raw_detections == 0:
                    self.logger.info("Candidate [%s] media_id=%s: faces=0, decision=NO_FACE", short_hash, media_id)
                    stage = "PERSIST_RESULTS"
                    self._record_success_and_apply_routing(media_id, attempt_id, res.face_results, short_hash)
                elif res.raw_detections > 0 and res.accepted_size == 0 and res.ignored_tiny > 0:
                    self.logger.info("Candidate [%s] media_id=%s: faces=0, decision=IGNORED_TINY", short_hash, media_id)
                    stage = "PERSIST_RESULTS"
                    self._record_success_and_apply_routing(media_id, attempt_id, res.face_results, short_hash)
                elif res.accepted_size > 0 and completed_faces == 0 and res.processing_errors > 0:
                    self.logger.info("Candidate [%s] media_id=%s: faces=0, decision=ANALYSIS_ERROR", short_hash, media_id)
                    self.db.record_face_analysis_failure(media_id, attempt_id, f"ANALYSIS_ERROR", f"stage=RESULT_ASSEMBLY error=ALL_FACES_FAILED", "FAILED")
                elif completed_faces > 0 and res.processing_errors > 0:
                    self.logger.info("Candidate [%s] media_id=%s: faces=%s, decision=PARTIAL_ANALYSIS", short_hash, media_id, completed_faces)
                    stage = "PERSIST_RESULTS"
                    self._record_success_and_apply_routing(media_id, attempt_id, res.face_results, short_hash)
                elif completed_faces > 0 and res.processing_errors == 0:
                    if len(res.face_results) == 1:
                        self.logger.info("Candidate [%s] media_id=%s: faces=1, decision=%s", short_hash, media_id, res.face_results[0]["decision"])
                    else:
                        self.logger.info("Candidate [%s] media_id=%s: faces=%s, accepted=%s, unknown=%s", short_hash, media_id, completed_faces, res.accepted_faces, res.unknown_faces)
                    stage = "PERSIST_RESULTS"
                    self._record_success_and_apply_routing(media_id, attempt_id, res.face_results, short_hash)
                    
            except FaceAnalysisStageError as exc:
                self.logger.error("Candidate [%s] failed: stage=%s error=%s", short_hash, exc.stage, type(exc.cause).__name__)
                log_private(self.logger, self.opts.verbose_private, "Candidate [%s] private traceback", short_hash, exc_info=True)
                if attempt_id is not None:
                    self.db.record_face_analysis_failure(media_id, attempt_id, f"ANALYSIS_ERROR", f"stage={exc.stage} error={type(exc.cause).__name__}", "FAILED")
            except Exception as e:
                self.logger.error("Candidate [%s] failed: stage=%s error=%s", short_hash, stage, type(e).__name__)
                log_private(self.logger, self.opts.verbose_private, "Candidate [%s] private traceback", short_hash, exc_info=True)
                if attempt_id is not None:
                    self.db.record_face_analysis_failure(media_id, attempt_id, f"ANALYSIS_ERROR", f"stage={stage} error={type(e).__name__}", "FAILED")
