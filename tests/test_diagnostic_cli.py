import pytest
import subprocess
import sys
from pathlib import Path
from PIL import Image

def create_dummy_image(path, size, orientation=None):
    img = Image.new("RGB", size, color="blue")
    if orientation is not None:
        exif = img.getexif()
        exif[0x0112] = orientation
        img.save(path, exif=exif.tobytes())
    else:
        img.save(path)

def test_diagnostic_detection_cli(tmp_path):
    img_path = tmp_path / "test_diag.jpg"
    create_dummy_image(img_path, (100, 50), orientation=6)
    
    # Run the CLI
    result = subprocess.run(
        [sys.executable, "-m", "src.diagnostic_detection", "--source", str(img_path), "--thresholds", "0.90", "0.85", "--verbose-private"],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    output = result.stdout
    
    assert "Raw stored pixel dimensions: 100x50" in output
    assert "EXIF orientation value: 6" in output
    assert "Orientation normalization applied: True" in output
    assert "Orientation-normalized dimensions: 50x100" in output
    
    assert "--- Threshold: 0.90 ---" in output
    assert "--- Threshold: 0.85 ---" in output
    assert "Detector input dimensions: 50x100" in output
    
    # It shouldn't connect to the DB
    assert "ArchiveDatabase" not in output
