import logging
import subprocess
from pathlib import Path
from PIL import Image

logger = logging.getLogger(__name__)

def generate_image_preview(source_path: Path, output_path: Path) -> bool:
    """
    Generates a scaled-down preview of an image.
    Returns True if successful, False if it failed.
    """
    try:
        with Image.open(source_path) as img:
            # Convert to RGB if it's RGBA or P to avoid JPEG save errors
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            img.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
            img.save(output_path, "JPEG", quality=80)
            return True
    except Exception as e:
        logger.warning(f"Failed to generate image preview for {source_path.name}: {e}")
        return False

def generate_video_thumbnail(source_path: Path, output_path: Path) -> bool:
    """
    Generates a thumbnail for a video trying multiple fallbacks for a representative frame.
    Returns True if successful, False if it failed.
    """
    # Try 1 second, then 5 seconds, then the very first frame (0s).
    fallbacks = ["1", "5", "0"]
    
    for offset in fallbacks:
        cmd = [
            "ffmpeg",
            "-v", "error",
            "-y",
            "-ss", offset,
            "-i", str(source_path),
            "-vframes", "1",
            "-vf", "scale=1280:1280:force_original_aspect_ratio=decrease",
            "-f", "image2",
            "-c:v", "mjpeg",
            str(output_path)
        ]
        
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if proc.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                return True
        except subprocess.TimeoutExpired:
            logger.warning(f"ffmpeg timeout while generating thumbnail for {source_path.name} at {offset}s")
        except Exception as e:
            logger.warning(f"ffmpeg error while generating thumbnail for {source_path.name} at {offset}s: {e}")
            
    return False
