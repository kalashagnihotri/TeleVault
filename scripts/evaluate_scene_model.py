import sys
from pathlib import Path
from src.scene_analysis import SceneClassifier, PLACES365_MAPPING

def main():
    if len(sys.argv) != 2:
        print("Usage: python evaluate_scene_model.py <image_path>")
        sys.exit(1)
        
    image_path = Path(sys.argv[1])
    if not image_path.exists():
        print(f"Image not found: {image_path}")
        sys.exit(1)
        
    import time
    
    t0 = time.time()
    model_path = Path("private_data/scenes/models/resnet18_places365.onnx")
    cat_path = Path("private_data/scenes/models/categories_places365.txt")
    classifier = SceneClassifier(str(model_path), str(cat_path))
    t1 = time.time()
    print(f"Initialization: {t1-t0:.3f}s")
    
    print(f"Evaluating: {image_path}")
    t2 = time.time()
    predictions = classifier.classify(image_path)
    t3 = time.time()
    print(f"Inference: {t3-t2:.3f}s")
    
    print("\n--- Top 15 Raw Places365 Predictions ---")
    
    ml_labels_map = {}
    for i, pred in enumerate(predictions[:15]):
        raw_lbl = pred.get("label", "")
        conf = pred.get("confidence", 0.0)
        print(f"{i+1:2d}. {raw_lbl:<30} (conf: {conf:.4f})")
        
        if raw_lbl in PLACES365_MAPPING:
            for m in PLACES365_MAPPING[raw_lbl]:
                ml_labels_map[m] = max(ml_labels_map.get(m, 0.0), conf)
                
    print("\n--- Mapped Canonical Labels ---")
    if not ml_labels_map:
        print("No mapped labels found in Top 15.")
    else:
        for lbl, conf in sorted(ml_labels_map.items(), key=lambda x: -x[1]):
            print(f"- {lbl:<20} (max conf: {conf:.4f})")

if __name__ == "__main__":
    main()
