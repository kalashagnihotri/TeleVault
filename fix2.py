import re

with open('tests/test_face_engine.py', 'r') as f:
    content = f.read()
content = content.replace('config = test_config()', 'config = test_config')
with open('tests/test_face_engine.py', 'w') as f:
    f.write(content)

with open('tests/test_face_database.py', 'r') as f:
    content = f.read()
content = content.replace('config = test_config()', 'config = test_config')
content = content.replace(
    "conn.execute(\"INSERT INTO media (id, sha256, original_filename, original_path, state) VALUES (1, 'hash', 'file', 'path', 'BACKED_UP')\")",
    "conn.execute(\"INSERT INTO media (id, sha256, short_hash, original_filename, original_path, state) VALUES (1, 'hash', 'hash', 'file', 'path', 'BACKED_UP')\")"
)
with open('tests/test_face_database.py', 'w') as f:
    f.write(content)
