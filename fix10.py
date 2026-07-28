import re

with open('tests/test_face_database.py', 'r') as f:
    content = f.read()

content = content.replace(
    "conn.execute(\"INSERT INTO media (id, sha256, short_hash, original_filename, original_path, state, media_type, size_bytes, modified_ns, discovered_at, updated_at) VALUES (1, 'hash', 'hash', 'file', 'path', 'BACKED_UP', 'image', 1234, 0, '2026-01-01T00:00:00', '2026-01-01T00:00:00')\")",
    "conn.execute(\"INSERT INTO media (id, sha256, short_hash, original_filename, original_path, state, media_type, size_bytes, modified_ns, discovered_at, updated_at) VALUES (1, 'hash', 'hash', 'file', 'path', 'BACKED_UP', 'image', 1234, 0, '2026-01-01T00:00:00', '2026-01-01T00:00:00')\")\n    db.activate_calibration(\"model_1\", \"ref_hash\", 0.8, 0.7, 0.1, 10, 10, \"{}\")\n    db.activate_calibration(\"model_1\", \"ref_hash2\", 0.8, 0.7, 0.1, 10, 10, \"{}\")"
)

with open('tests/test_face_database.py', 'w') as f:
    f.write(content)
