from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ExifTags
import numpy as np

logger = logging.getLogger(__name__)

def extract_heuristic_scene_labels(path: Path, config_scenes) -> list[str]:
    labels = set()
    
    # Early exit if both heuristics disabled
    if not config_scenes.enable_screenshot_heuristics and not config_scenes.enable_document_heuristics:
        return list(labels)
        
    name = path.name.lower()
    
    if config_scenes.enable_screenshot_heuristics:
        if _is_screenshot(path, name):
            labels.add("screenshot")
            
    if config_scenes.enable_document_heuristics:
        if _is_document(path, name):
            labels.add("document")
            
    return sorted(list(labels))

def _is_screenshot(path: Path, name: str) -> bool:
    # Strong filename evidence
    if name.startswith("screenshot") or name.startswith("screen-") or "screenshot" in name:
        return True
        
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return False
                
            software = exif.get(305, "")
            user_comment = exif.get(37510, b"")
            
            if isinstance(software, str) and "screenshot" in software.lower():
                return True
            if isinstance(user_comment, bytes) and b"screenshot" in user_comment.lower():
                return True
    except Exception as e:
        logger.debug("Failed to extract EXIF for screenshot heuristics: %s", e)
        
    return False

def _is_document(path: Path, name: str) -> bool:
    # Strong filename evidence
    if name.startswith("scan_") or name.startswith("scan-") or "scanned" in name:
        return True
        
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                pass
            else:
                software = exif.get(305, "")
                if isinstance(software, str) and any(kw in software.lower() for kw in ("scanner", "scan utility", "pdf")):
                    return True
    except Exception as e:
        logger.debug("Failed to extract EXIF for document heuristics: %s", e)
        
    # Visual document analysis fallback
    if is_document_like(path):
        return True
        
    return False

def is_photographic(path: Path) -> bool:
    """
    Conservatively deterministically check if an image is photographic 
    using a pixel-level unique color count. Pure UI screenshots usually have < 1000 colors.
    Photographs usually have > 10,000 colors even when thumbnailed.
    """
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail((256, 256))
            colors = len(set(img.getdata()))
            return colors > 5000
    except Exception as e:
        logger.debug("Failed to analyze photographic content: %s", e)
        return False

def is_document_like(path: Path) -> bool:
    """
    Conservatively evaluate if an image visually resembles a document/page.
    Uses multiple signals: brightness, text-like edges, low UI saturation,
    and color complexity.
    """
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            
            # Photographic color complexity
            thumb = img.copy()
            thumb.thumbnail((256, 256))
            colors = len(set(thumb.getdata()))
            
            arr = np.array(img, dtype=float)
            
        r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
        max_c = np.maximum(np.maximum(r, g), b)
        min_c = np.minimum(np.minimum(r, g), b)
        
        lightness = max_c
        delta = max_c - min_c
        sat = np.zeros_like(max_c)
        np.divide(delta, max_c, out=sat, where=max_c!=0)
        sat = sat * 255
        
        bright_ratio = np.mean((lightness > 200) & (sat < 40))
        high_sat_ratio = np.mean((sat > 100) & (lightness > 50))
        neutral_ratio = np.mean((sat < 60) & (lightness > 50))
        
        gray = 0.299*r + 0.587*g + 0.114*b
        
        dy = np.abs(gray[1:, :] - gray[:-1, :])[:, :-1]
        dx = np.abs(gray[:, 1:] - gray[:, :-1])[:-1, :]
        
        mag = np.sqrt(dx**2 + dy**2)
        vh_ratio = np.mean(mag > 30)
        
        is_doc = False
        
        # Branch A: Classic light document
        if neutral_ratio > 0.80 and vh_ratio > 0.005 and high_sat_ratio < 0.02:
            is_doc = True
            
        # Branch B: Darker/colored document
        if neutral_ratio > 0.50 and vh_ratio > 0.030 and high_sat_ratio < 0.05:
            is_doc = True
            
        return is_doc
            
    except Exception as e:
        logger.debug("Failed visual document analysis for [%s]: %s", path.name, e)
        
    return False
