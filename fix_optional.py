import os

path = 'tests/test_optional_dependencies.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

out = []
in_mock = False
enable_faces = True

for line in lines:
    if 'def mock_load_config():' in line:
        in_mock = True
        out.append(line)
        out.append('        import pathlib, sys, os\n')
        out.append('        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))\n')
        out.append('        from tests.conftest import make_test_config\n')
        if 'test_main_startup_without_cv2' in "".join(out[-20:]): # roughly
            enable_faces = True
        else:
            enable_faces = False
        out.append(f'        c = make_test_config(pathlib.Path(os.getcwd()))\n')
        out.append(f'        c.faces.enabled = {enable_faces}\n')
        out.append('        return c\n')
    elif in_mock:
        if 'src.main.load_config = mock_load_config' in line:
            in_mock = False
            out.append(line)
    else:
        out.append(line)

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(out)
