import re

path = 'tests/test_face_analysis_dry_run.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace manual INSERT with activate_scoped_test_calibration in test_dry_run_analysis_with_known_and_unknown
c1 = '''        with memory_db.connect() as conn:
            from src.hashing import get_calibration_scope_hash
            import hashlib
            base_ref_hash = hashlib.sha256(b"refhash").hexdigest()
            ref_set_hash = get_calibration_scope_hash("modelA", base_ref_hash, mock_engine_config.faces.policy_identity)
            conn.execute(
                "INSERT INTO face_calibrations (model_identity, reference_set_hash, accept_threshold, review_threshold, minimum_margin, individual_strong_support_threshold, positive_pair_count, negative_pair_count, active, generated_at) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 1, ?)",
                ("modelA", ref_set_hash, 0.8, 0.6, 0.1, 0.75, "now")
            )'''
r1 = '''        from tests.conftest import activate_scoped_test_calibration
        activate_scoped_test_calibration(memory_db, mock_engine_config, "modelA", ["refhash"])'''
content = content.replace(c1, r1)

# Also test_stale_calibration_produces_unknown_uncalibrated
c2 = '''            with memory_db.connect() as conn:
                conn.execute(
                    "INSERT INTO face_calibrations (model_identity, reference_set_hash, accept_threshold, review_threshold, minimum_margin, individual_strong_support_threshold, positive_pair_count, negative_pair_count, active, generated_at) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 1, ?)",
                    ("modelA", "wrong_hash", 0.8, 0.6, 0.1, 0.75, "now")
                )'''
r2 = '''            with memory_db.connect() as conn:
                conn.execute(
                    "INSERT INTO face_calibrations (model_identity, reference_set_hash, accept_threshold, review_threshold, minimum_margin, individual_strong_support_threshold, positive_pair_count, negative_pair_count, active, generated_at) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 1, datetime('now'))",
                    ("modelA", "wrong_hash", 0.8, 0.6, 0.1, 0.75)
                )'''
content = content.replace(c2, r2)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
