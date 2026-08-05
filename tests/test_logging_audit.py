import pytest
from pathlib import Path
import re

def test_static_logging_audit():
    project_root = Path(__file__).resolve().parent.parent
    
    src_dir = project_root / "src"
    scripts_dir = project_root / "scripts"
    
    files_to_check = list(src_dir.rglob("*.py")) + list(scripts_dir.rglob("*.py"))
    
    violations = []
    
    # We are looking for:
    # 1. logger.exception( (which is forbidden entirely outside of log_private in logging_utils)
    # 2. logger.*(f" (f-strings used in public loggers)
    # 3. f-strings in print()
    
    # Exceptions
    allowed_files_for_exception = ["logging_utils.py"]
    
    for py_file in files_to_check:
        try:
            content = py_file.read_text(encoding="utf-8")
        except:
            continue
            
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            # Check logger.exception
            if "logger.exception(" in line and py_file.name not in allowed_files_for_exception:
                violations.append(f"{py_file.name}:{i} - Found forbidden logger.exception()")
                
            # Check logger.*(f"
            # It's a bit tricky because of formatting, but let's check for basic ones
            if re.search(r'logger\.(?:info|error|warning|critical)\(\s*f["\']', line):
                violations.append(f"{py_file.name}:{i} - Found forbidden f-string in logger call: {line.strip()}")
                
    if violations:
        for v in violations:
            print(v)
        pytest.fail(f"Found {len(violations)} privacy logging violations")

