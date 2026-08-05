import os
import re

path = 'tests/test_face_analysis_diagnostics.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# For test_missing_second_best:
pattern = r'''            with memory_db\.connect\(\) as conn:\n                ref_set_hash = hashlib\.sha256\(b"r1"\)\.hexdigest\(\)\n                conn\.execute\(\n                    "INSERT INTO face_calibrations \(model_identity, reference_set_hash, accept_threshold, review_threshold, minimum_margin, individual_strong_support_threshold, positive_pair_count, negative_pair_count, active, generated_at\) VALUES \(\?, \?, \?, \?, \?, \?, 0, 0, 1, \?\)",\n                    \("modelA", ref_set_hash, 0\.8, 0\.6, 0\.1, 0\.75, "now"\)\n                \)'''

r1 = '''            from tests.conftest import activate_scoped_test_calibration
            activate_scoped_test_calibration(memory_db, mock_engine_config, "modelA", ["r1"])'''

c = re.sub(pattern, r1, c, flags=re.MULTILINE)

# Also check test_group_photo_resilience
pattern2 = r'''            with memory_db\.connect\(\) as conn:\n                conn\.execute\(\n                    "INSERT INTO face_calibrations \(model_identity, reference_set_hash, accept_threshold, review_threshold, minimum_margin, individual_strong_support_threshold, positive_pair_count, negative_pair_count, active, generated_at\) VALUES \(\?, \?, \?, \?, \?, \?, 0, 0, 1, \?\)",\n                    \("modelA", hashlib\.sha256\(b"r1"\)\.hexdigest\(\), 0\.8, 0\.6, 0\.1, 0\.75, "now"\)\n                \)'''

r2 = '''            from tests.conftest import activate_scoped_test_calibration
            activate_scoped_test_calibration(memory_db, mock_engine_config, "modelA", ["r1"])'''

c = re.sub(pattern2, r2, c, flags=re.MULTILINE)

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
