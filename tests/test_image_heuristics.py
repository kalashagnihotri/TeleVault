from pathlib import Path
from PIL import Image

from src.image_heuristics import extract_heuristic_scene_labels
from src.config import SceneConfig

def test_screenshot_filename_heuristics(tmp_path: Path):
    config = SceneConfig(enabled=True, model_path="", minimum_confidence=0.25, max_labels=3, enable_screenshot_heuristics=True, enable_document_heuristics=True)
    p = tmp_path / "screenshot_123.jpg"
    p.touch()
    labels = extract_heuristic_scene_labels(p, config)
    assert "screenshot" in labels
    
def test_png_alone_not_screenshot(tmp_path: Path):
    config = SceneConfig(enabled=True, model_path="", minimum_confidence=0.25, max_labels=3, enable_screenshot_heuristics=True, enable_document_heuristics=True)
    p = tmp_path / "photo.png"
    p.touch()
    labels = extract_heuristic_scene_labels(p, config)
    assert "screenshot" not in labels

def test_ordinary_camera_image_not_screenshot(tmp_path: Path):
    config = SceneConfig(enabled=True, model_path="", minimum_confidence=0.25, max_labels=3, enable_screenshot_heuristics=True, enable_document_heuristics=True)
    p = tmp_path / "IMG_1234.jpg"
    p.touch()
    labels = extract_heuristic_scene_labels(p, config)
    assert "screenshot" not in labels

def test_document_filename_heuristics(tmp_path: Path):
    config = SceneConfig(enabled=True, model_path="", minimum_confidence=0.25, max_labels=3, enable_screenshot_heuristics=True, enable_document_heuristics=True)
    p = tmp_path / "scan_invoice.jpg"
    p.touch()
    labels = extract_heuristic_scene_labels(p, config)
    assert "document" in labels
    
def test_ordinary_image_not_document(tmp_path: Path):
    config = SceneConfig(enabled=True, model_path="", minimum_confidence=0.25, max_labels=3, enable_screenshot_heuristics=True, enable_document_heuristics=True)
    p = tmp_path / "IMG_1234.jpg"
    p.touch()
    labels = extract_heuristic_scene_labels(p, config)
    assert "document" not in labels
