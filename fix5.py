import re

with open('tests/test_face_database.py', 'r') as f:
    content = f.read()

content = content.replace(
    "conn.execute(\"INSERT INTO media (id, sha256, short_hash, original_filename, original_path, state, media_type, size_bytes, width, height) VALUES (1, 'hash', 'hash', 'file', 'path', 'BACKED_UP', 'photo', 1234, 100, 100)\")",
    "conn.execute(\"INSERT INTO media (id, sha256, short_hash, original_filename, original_path, state, media_type, size_bytes) VALUES (1, 'hash', 'hash', 'file', 'path', 'BACKED_UP', 'photo', 1234)\")"
)

with open('tests/test_face_database.py', 'w') as f:
    f.write(content)
