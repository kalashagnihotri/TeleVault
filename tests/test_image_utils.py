import pytest
import numpy as np
from PIL import Image
from src.image_utils import decode_image_with_exif

def create_dummy_image(path, size, orientation=None):
    img = Image.new("RGB", size, color="red")
    if orientation is not None:
        exif = img.getexif()
        exif[0x0112] = orientation
        # To save EXIF with PIL, we need to convert it to bytes
        img.save(path, exif=exif.tobytes())
    else:
        img.save(path)

def test_exif_orientation_1(tmp_path):
    path = tmp_path / "test1.jpg"
    create_dummy_image(path, (100, 50), orientation=1)
    
    info = decode_image_with_exif(str(path))
    assert info["raw_width"] == 100
    assert info["raw_height"] == 50
    assert info["normalized_width"] == 100
    assert info["normalized_height"] == 50
    assert info["exif_orientation"] == 1
    assert not info["was_normalized"]
    assert info["image"].shape == (50, 100, 3)

def test_exif_orientation_6(tmp_path):
    # Orientation 6: Rotated 90 CW. So original (100, 50) becomes (50, 100)
    path = tmp_path / "test6.jpg"
    create_dummy_image(path, (100, 50), orientation=6)
    
    info = decode_image_with_exif(str(path))
    assert info["raw_width"] == 100
    assert info["raw_height"] == 50
    assert info["normalized_width"] == 50
    assert info["normalized_height"] == 100
    assert info["exif_orientation"] == 6
    assert info["was_normalized"]
    assert info["image"].shape == (100, 50, 3) # (height, width, channels)

def test_exif_orientation_8(tmp_path):
    # Orientation 8: Rotated 90 CCW. Original (100, 50) becomes (50, 100)
    path = tmp_path / "test8.jpg"
    create_dummy_image(path, (100, 50), orientation=8)
    
    info = decode_image_with_exif(str(path))
    assert info["raw_width"] == 100
    assert info["raw_height"] == 50
    assert info["normalized_width"] == 50
    assert info["normalized_height"] == 100
    assert info["exif_orientation"] == 8
    assert info["was_normalized"]
    assert info["image"].shape == (100, 50, 3)
