import os

path = 'tests/test_face_analysis_diagnostics.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

bad = '''            with memory_db.connect() as conn:
                ref_set_hash = hashlib.sha256(b"r1").hexdigest()
                conn.execute(
                    "INSERT INTO face_calibrations (model_identity, reference_set_hash, accept_threshold, review_threshold, minimum_margin, individual_strong_support_threshold, positive_pair_count, negative_pair_count, active, generated_at) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 1, ?)",
                    ("modelA", ref_set_hash, 0.8, 0.6, 0.1, 0.75, "now")
                )'''

good = '''            from tests.conftest import activate_scoped_test_calibration
            activate_scoped_test_calibration(memory_db, mock_engine_config, "modelA", ["r1"])'''

c = c.replace(bad, good)
with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
