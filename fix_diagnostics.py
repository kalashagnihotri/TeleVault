import re

path = 'tests/test_face_analysis_diagnostics.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace manual INSERT with activate_scoped_test_calibration in test_distinct_person_second_best
c1 = '''        with memory_db.connect() as conn:
            ref_hashes = ["r1", "r2", "r3"]
            ref_set_hash = hashlib.sha256("".join(sorted(ref_hashes)).encode()).hexdigest()
            conn.execute(
                "INSERT INTO face_calibrations (model_identity, reference_set_hash, accept_threshold, review_threshold, minimum_margin, individual_strong_support_threshold, positive_pair_count, negative_pair_count, active, generated_at) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 1, ?)",
                ("modelA", ref_set_hash, 0.8, 0.6, 0.1, 0.75, "now")
            )'''
r1 = '''        from tests.conftest import activate_scoped_test_calibration
        ref_hashes = ["r1", "r2", "r3"]
        activate_scoped_test_calibration(memory_db, mock_engine_config, "modelA", ref_hashes)'''
content = content.replace(c1, r1)

# Replace manual INSERT in test_missing_second_best
c2 = '''        with memory_db.connect() as conn:
            conn.execute(
                "INSERT INTO face_calibrations (model_identity, reference_set_hash, accept_threshold, review_threshold, minimum_margin, individual_strong_support_threshold, positive_pair_count, negative_pair_count, active, generated_at) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 1, ?)",
                ("modelA", hashlib.sha256(b"r1").hexdigest(), 0.8, 0.6, 0.1, 0.75, "now")
            )'''
r2 = '''        from tests.conftest import activate_scoped_test_calibration
        activate_scoped_test_calibration(memory_db, mock_engine_config, "modelA", ["r1"])'''
content = content.replace(c2, r2)

# Replace manual INSERT in test_group_photo_resilience
c3 = '''        with memory_db.connect() as conn:
            conn.execute(
                "INSERT INTO face_calibrations (model_identity, reference_set_hash, accept_threshold, review_threshold, minimum_margin, individual_strong_support_threshold, positive_pair_count, negative_pair_count, active, generated_at) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 1, ?)",
                ("modelA", hashlib.sha256(b"r1").hexdigest(), 0.8, 0.6, 0.1, 0.75, "now")
            )'''
r3 = '''        from tests.conftest import activate_scoped_test_calibration
        activate_scoped_test_calibration(memory_db, mock_engine_config, "modelA", ["r1"])'''
content = content.replace(c3, r3)

# Add configure_test_face_policy to mock_engine_config fixture in test_face_analysis_diagnostics.py
c4 = '''def mock_engine_config():
    config = MagicMock()
    config.faces.aggregate_method = "top_k_mean"
    config.faces.aggregate_top_k = 1
    config.faces.minimum_strong_support = 1
    config.faces.policy_identity = "mock_policy"
    config.faces.minimum_face_size_px = 50
    config.faces.minimum_supporting_references = 1
    return config'''
r4 = '''def mock_engine_config():
    config = MagicMock()
    from tests.conftest import configure_test_face_policy
    config.faces.policy_identity = "mock_policy"
    configure_test_face_policy(config, top_k=1, strong_support=1)
    config.faces.minimum_face_size_px = 50
    return config'''
content = content.replace(c4, r4)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
