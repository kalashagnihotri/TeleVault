import re

path = 'tests/test_optional_dependencies.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the block that mocks the config in both tests

def replace_config_mock(c, enable_faces):
    pattern = r'''    def mock_load_config\(\):.*?return c\n    src\.main\.load_config = mock_load_config'''
    
    repl = f'''    def mock_load_config():
        from tests.conftest import make_test_config
        from pathlib import Path
        import sys
        sys.modules["tests.conftest"] = __import__("tests.conftest", fromlist=["make_test_config"])
        c = make_test_config(Path(os.getcwd()))
        c.faces.enabled = {enable_faces}
        return c
    src.main.load_config = mock_load_config'''
    return re.sub(pattern, repl, c, flags=re.DOTALL)

# Let's just do it manually with simple string split/replace since we know there are exactly two tests
tests = content.split('def test_main_startup_with_cv2_faces_disabled(tmp_path):')
if len(tests) == 2:
    # First part is test_main_startup_without_cv2
    # Second part is test_main_startup_with_cv2_faces_disabled
    pattern = r'''    def mock_load_config\(\):.*?return c\n    src\.main\.load_config = mock_load_config'''
    
    repl1 = '''    def mock_load_config():
        import pathlib
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from tests.conftest import make_test_config
        c = make_test_config(pathlib.Path(os.getcwd()))
        c.faces.enabled = True
        return c
    src.main.load_config = mock_load_config'''
    
    repl2 = '''    def mock_load_config():
        import pathlib
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from tests.conftest import make_test_config
        c = make_test_config(pathlib.Path(os.getcwd()))
        c.faces.enabled = False
        return c
    src.main.load_config = mock_load_config'''
    
    p1 = re.sub(pattern, repl1, tests[0], flags=re.DOTALL)
    p2 = re.sub(pattern, repl2, tests[1], flags=re.DOTALL)
    
    new_content = p1 + 'def test_main_startup_with_cv2_faces_disabled(tmp_path):' + p2
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
