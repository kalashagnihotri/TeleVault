from __future__ import annotations

import json
import logging
from pathlib import Path

from src.config import Config
from src.database import ArchiveDatabase
from src.image_heuristics import extract_heuristic_scene_labels, is_photographic
from src.routing import RouteInput, choose_topic
import onnxruntime as ort
import numpy as np
from PIL import Image

CURRENT_SCENE_ANALYSIS_VERSION = 4

PLACES365_MAPPING = {
    "mountain": ["mountains", "nature"],
    "mountain_snowy": ["mountains", "snow", "nature"],
    "mountain_path": ["mountains", "nature"],
    "lake/natural": ["lake", "nature"],
    "river": ["river", "nature"],
    "creek": ["river", "nature"],
    "ocean": ["ocean", "nature"],
    "coast": ["beach", "nature"],
    "beach": ["beach", "nature"],
    "forest/broadleaf": ["forest", "nature"],
    "forest_path": ["forest", "nature"],
    "forest_road": ["forest", "nature"],
    "rainforest": ["forest", "nature"],
    "snowfield": ["snow", "nature"],
    "glacier": ["snow", "nature"],
    "sky": ["sky", "nature"],
    "street": ["urban"],
    "downtown": ["urban"],
    "residential_neighborhood": ["urban"],
    "living_room": ["indoor"],
    "bedroom": ["indoor"],
    "kitchen": ["indoor"],
    "office": ["indoor"],
    "valley": ["mountains", "nature"],
    "volcano": ["mountains", "nature"],
    "restaurant": ["indoor"],
    "conference_room": ["indoor"],
    "conference_center": ["indoor"],
    "dining_room": ["indoor"],
    "hotel_room": ["indoor"],
    "pub/indoor": ["indoor"]
}

class SceneClassifier:
    """ONNX-based ML classifier for Places365 (Phase 6B)."""
    def __init__(self, model_path: str, categories_path: str):
        self.model_path = model_path
        self.categories_path = categories_path
        self.session = None
        self.categories = []

        if not Path(self.model_path).exists():
            raise FileNotFoundError(f"Scene model not found: {self.model_path}")
        if not Path(self.categories_path).exists():
            raise FileNotFoundError(f"Scene categories not found: {self.categories_path}")

        with open(self.categories_path, "r") as f:
            for line in f:
                # e.g., "/a/airfield 0" -> "airfield", "/b/bazaar/indoor 46" -> "bazaar/indoor"
                cat_name = line.strip().split(' ')[0]
                if cat_name.startswith('/'):
                    cat_name = '/'.join(cat_name.split('/')[2:])
                self.categories.append(cat_name)
                
        if len(self.categories) != 365:
            raise ValueError(f"Expected 365 categories, got {len(self.categories)}")
            
        manifest_path = Path(self.model_path).parent / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path, "r") as mf:
                manifest = json.load(mf)
                
            def hash_file(p: str) -> str:
                import hashlib
                h = hashlib.sha256()
                with open(p, "rb") as fp:
                    for chunk in iter(lambda: fp.read(65536), b""):
                        h.update(chunk)
                return h.hexdigest().lower()
                
            expected_onnx = manifest.get("onnx_sha256", "").lower()
            if expected_onnx and hash_file(self.model_path) != expected_onnx:
                raise ValueError("ONNX model hash mismatch according to manifest.")
                
            expected_cat = manifest.get("categories_sha256", "").lower()
            if expected_cat and hash_file(self.categories_path) != expected_cat:
                raise ValueError("Categories hash mismatch according to manifest.")

        # Delay importing onnxruntime until initialization to prevent startup crashes if missing
        import onnxruntime as ort
        self.session = ort.InferenceSession(self.model_path, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        
    def _preprocess(self, path: Path) -> np.ndarray:
        # Load image safely
        img = Image.open(path)
        if img.mode != "RGB":
            img = img.convert("RGB")
            
        # Resize to 256x256, then CenterCrop 224x224
        img = img.resize((256, 256), Image.Resampling.BILINEAR)
        left = (256 - 224) / 2
        top = (256 - 224) / 2
        right = (256 + 224) / 2
        bottom = (256 + 224) / 2
        img = img.crop((left, top, right, bottom))
        
        # Convert to numpy and normalize
        img_np = np.array(img).astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        img_np = (img_np - mean) / std
        
        # HWC to NCHW
        img_np = np.transpose(img_np, (2, 0, 1))
        img_np = np.expand_dims(img_np, axis=0)
        return img_np
        
    def classify(self, path: Path) -> list[dict]:
        img_tensor = self._preprocess(path)
        
        logits = self.session.run(None, {self.input_name: img_tensor})[0][0]
        
        # Softmax
        exp_logits = np.exp(logits - np.max(logits))
        probs = exp_logits / np.sum(exp_logits)
        
        # Return all predictions ranked
        sorted_indices = np.argsort(probs)[::-1]
        
        results = []
        for idx in sorted_indices:
            results.append({
                "label": self.categories[idx],
                "confidence": float(probs[idx])
            })
            
        return results

class SceneAnalysisWorker:
    def __init__(self, config: Config, db: ArchiveDatabase, logger: logging.Logger):
        self.config = config
        self.db = db
        self.logger = logger
        self.classifier = None
        
        # Test hook
        self._fake_classifier = None
        
    def _apply_scene_routing_if_enabled(self, media_id: int, short_hash: str, new_labels: list[str]) -> None:
        if not new_labels:
            return
            
        try:
            # We don't overwrite face routes, so we check people first
            people_names = self.db.get_media_people_names(media_id)
            context = self.db.get_media_routing_context(media_id)
            if not context:
                return
                
            route_input = RouteInput(
                media_type=context["media_type"],
                people=tuple(people_names),
                labels=tuple(new_labels),
                has_gps=bool(context["has_gps"])
            )
            
            new_route = choose_topic(route_input)
            
            # If the new route is family_groups or people, that means face routing took precedence
            # We should only update the route if the scene labels actually caused a change,
            # but updating to the *same* or expected route is fine.
            if new_route != context["route_key"]:
                self.db.update_route_before_upload(media_id, new_route)
        except Exception as e:
            self.logger.warning("Failed to apply scene routing for [%s]: %s", short_hash, e)

    def run_pending(self) -> None:
        if not getattr(self.config, "scenes", None) or not self.config.scenes.enabled:
            return
            
        pending = self.db.get_pending_scene_media(limit=50)
        if not pending:
            return
            
        for media in pending:
            media_id = media["id"]
            short_hash = media["short_hash"]
            original_path = Path(media["original_path"])
            
            # Start with heuristic labels
            heuristic_labels = []
            try:
                heuristic_labels = extract_heuristic_scene_labels(original_path, self.config.scenes)
            except Exception as e:
                self.logger.warning("Heuristics failed for [%s]: %s", short_hash, e)
                
            if "document" in heuristic_labels:
                skip_ml = True
            elif "screenshot" in heuristic_labels:
                skip_ml = not is_photographic(original_path)
            else:
                skip_ml = False
                
            if skip_ml:
                final_labels = sorted(heuristic_labels)
                labels_json = json.dumps(final_labels)
                self.db.complete_scene_analysis(media_id, labels_json, CURRENT_SCENE_ANALYSIS_VERSION)
                self._apply_scene_routing_if_enabled(media_id, short_hash, final_labels)
                continue

            if not self._fake_classifier and not self.classifier:
                try:
                    categories_path = str(Path(self.config.scenes.model_path).parent / "categories_places365.txt")
                    self.classifier = SceneClassifier(self.config.scenes.model_path, categories_path)
                except Exception as e:
                    self.logger.warning("Failed to initialize ML classifier: %s", e)
                    # classifier remains None
                
            try:
                ml_labels_map = {} # canonical label -> max confidence
                
                # 2. ML Engine
                classifier = self._fake_classifier or self.classifier
                if not classifier:
                    raise RuntimeError("SCENE_MODEL_INIT_FAILED")
                    
                predictions = classifier.classify(original_path)
                    
                # Inspect a bounded raw top-N prediction set (e.g., top 15)
                top_predictions = predictions[:15]
                
                for pred in top_predictions:
                    raw_lbl = pred.get("label", "").lower()
                    conf = pred.get("confidence", 0.0)
                    
                    if raw_lbl in PLACES365_MAPPING:
                        mapped_labels = PLACES365_MAPPING[raw_lbl]
                        for m in mapped_labels:
                            ml_labels_map[m] = max(ml_labels_map.get(m, 0.0), conf)
                            
                # Filter by minimum confidence
                filtered_ml_labels = []
                for lbl, conf in ml_labels_map.items():
                    if conf >= self.config.scenes.minimum_confidence:
                        filtered_ml_labels.append((lbl, conf))
                        
                # Deterministic sort: descending by confidence, then alphabetical
                filtered_ml_labels.sort(key=lambda x: (-x[1], x[0]))
                
                # Limit to max_labels
                ml_final_labels = [x[0] for x in filtered_ml_labels[:self.config.scenes.max_labels]]
                
                # Combine heuristic and ML labels
                final_labels = sorted(list(set(heuristic_labels + ml_final_labels)))
                
                # Update database
                labels_json = json.dumps(final_labels)
                self.db.complete_scene_analysis(media_id, labels_json, CURRENT_SCENE_ANALYSIS_VERSION)
                
                # Try routing
                self._apply_scene_routing_if_enabled(media_id, short_hash, final_labels)
                
            except Exception as e:
                self.logger.warning("Scene analysis ML failed for [%s]: %s", short_hash, e)
                error_code = "SCENE_MODEL_INIT_FAILED" if str(e) == "SCENE_MODEL_INIT_FAILED" else "SCENE_INFERENCE_FAILED"
                self.db.fail_scene_analysis(media_id, CURRENT_SCENE_ANALYSIS_VERSION, error_code, str(e))
                # DO NOT block upload or change media state to failed.
