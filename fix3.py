import re

with open('tests/test_face_engine.py', 'r') as f:
    content = f.read()

# Add skipif
skipif_dec = "@pytest.mark.skipif(not OPENCV_AVAILABLE, reason=\"requires opencv\")\ndef test_no_fake_production_model_files(mock_config, tmp_path):"
content = content.replace("def test_no_fake_production_model_files(mock_config, tmp_path):", skipif_dec)

with open('tests/test_face_engine.py', 'w') as f:
    f.write(content)

with open('tests/test_face_database.py', 'r') as f:
    content = f.read()

content = content.replace(
    "conn.execute(\"INSERT INTO media (id, sha256, short_hash, original_filename, original_path, state) VALUES (1, 'hash', 'hash', 'file', 'path', 'BACKED_UP')\")",
    "conn.execute(\"INSERT INTO media (id, sha256, short_hash, original_filename, original_path, state, media_type) VALUES (1, 'hash', 'hash', 'file', 'path', 'BACKED_UP', 'photo')\")"
)

with open('tests/test_face_database.py', 'w') as f:
    f.write(content)
