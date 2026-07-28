import subprocess
import sys
from pathlib import Path

def test_cli_help_without_numpy(tmp_path):
    script = tmp_path / "run_help.py"
    script.write_text("""
import sys
import os
sys.path.insert(0, os.getcwd())
sys.modules['numpy'] = None
sys.modules['cv2'] = None

import src.face_enrollment
sys.argv = ['face_enrollment', '--help']
try:
    sys.exit(src.face_enrollment.main())
except SystemExit as e:
    sys.exit(e.code)
""")

    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, cwd=str(Path(__file__).parent.parent))
    assert result.returncode == 0
    assert "Face Enrollment CLI" in result.stdout

def test_cli_list_without_numpy(tmp_path):
    script = tmp_path / "run_list.py"
    script.write_text("""
import sys
import os
sys.path.insert(0, os.getcwd())
sys.modules['numpy'] = None
sys.modules['cv2'] = None

import src.face_enrollment
sys.argv = ['face_enrollment', 'list']
try:
    sys.exit(src.face_enrollment.main())
except SystemExit as e:
    sys.exit(e.code)
""")

    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, cwd=str(Path(__file__).parent.parent))
    assert result.returncode == 0

def test_enroll_fails_cleanly(tmp_path):
    script = tmp_path / "run_enroll.py"
    script.write_text("""
import sys
import os
sys.path.insert(0, os.getcwd())
sys.modules['numpy'] = None
sys.modules['cv2'] = None

import src.face_enrollment
sys.argv = ['face_enrollment', 'enroll', '--person-slug', 'test', '--display-name', 'test', '--source', '.']
try:
    sys.exit(src.face_enrollment.main())
except SystemExit as e:
    sys.exit(e.code)
""")
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, cwd=str(Path(__file__).parent.parent))
    assert result.returncode == 1
    assert "Configuration error: Face processing dependency unavailable: install the Phase 5 requirements." in result.stderr

def test_main_startup_without_cv2(tmp_path):
    script = tmp_path / "run_main.py"
    script.write_text("""
import sys
import os
sys.path.insert(0, os.getcwd())
sys.modules['numpy'] = None
sys.modules['cv2'] = None

import asyncio
import src.main
sys.argv = ['main', '--dry-run']

# We must ensure faces.enabled = True to hit the OpenCV check
original_load_config = src.main.load_config
def mock_load_config():
    config = original_load_config()
    config.faces.enabled = True
    return config
src.main.load_config = mock_load_config

try:
    sys.exit(asyncio.run(src.main.main()))
except SystemExit as e:
    sys.exit(e.code)
""")
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, cwd=str(Path(__file__).parent.parent))
    assert result.returncode == 0
    out_err = result.stdout + result.stderr
    assert "OpenCV: unavailable" in out_err
    assert "Configuration error: Face processing dependency unavailable: install the Phase 5 requirements." in out_err

def test_main_startup_with_cv2_faces_disabled(tmp_path):
    script = tmp_path / "run_main_cv2.py"
    script.write_text("""
import sys
import os
sys.path.insert(0, os.getcwd())

import asyncio
import src.main
sys.argv = ['main', '--dry-run']

original_load_config = src.main.load_config
def mock_load_config():
    config = original_load_config()
    config.faces.enabled = False
    return config
src.main.load_config = mock_load_config

try:
    sys.exit(asyncio.run(src.main.main()))
except SystemExit as e:
    sys.exit(e.code)
""")
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, cwd=str(Path(__file__).parent.parent))
    assert result.returncode == 0
    out_err = result.stdout + result.stderr
    
    # Depending on whether cv2 is installed, one of these should be logged
    assert "OpenCV Version:" in out_err or "OpenCV: unavailable" in out_err
    assert "Face analysis disabled; models were not loaded." in out_err
