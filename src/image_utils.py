import numpy as np
from PIL import Image, ImageOps

def decode_image_with_exif(image_path: str) -> dict:
    """
    Decodes an image, applies EXIF orientation transpose, and converts it to an OpenCV BGR array.
    Returns:
        dict: {
            "image": numpy array (BGR),
            "raw_width": int,
            "raw_height": int,
            "normalized_width": int,
            "normalized_height": int,
            "exif_orientation": int or None,
            "was_normalized": bool
        }
    """
    # OpenCV is imported locally to avoid hard dependency on it if not needed,
    # though face detection requires it.
    import cv2
    
    with Image.open(image_path) as img:
        raw_width, raw_height = img.size
        
        exif = img.getexif()
        orientation = exif.get(0x0112) if exif else None
        
        img_transposed = ImageOps.exif_transpose(img)
        was_normalized = (orientation is not None and orientation != 1)
        
        normalized_width, normalized_height = img_transposed.size
        
        img_rgb = img_transposed.convert("RGB")
        img_np = np.array(img_rgb)
        img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        
        return {
            "image": img_bgr,
            "raw_width": raw_width,
            "raw_height": raw_height,
            "normalized_width": normalized_width,
            "normalized_height": normalized_height,
            "exif_orientation": orientation,
            "was_normalized": was_normalized
        }
