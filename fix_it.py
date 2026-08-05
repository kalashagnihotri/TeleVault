import os
import re

path = 'tests/test_face_analysis_diagnostics.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# 1. Update mock_engine_config fixture
c1 = '''def mock_engine_config():
    config = MagicMock()
    config.faces.aggregate_method = "top_k_mean"
    config.faces.aggregate_top_k = 3
    config.faces.minimum_strong_support = 2
    config.faces.policy_identity = "mock_policy"
    config.faces.minimum_face_size_px = 50
    config.faces.minimum_supporting_references = 2
    return config'''
r1 = '''def mock_engine_config():
    config = MagicMock()
    from tests.conftest import configure_test_face_policy
    config.faces.policy_identity = "mock_policy"
    configure_test_face_policy(config, top_k=1, strong_support=1)
    config.faces.minimum_face_size_px = 50
    return config'''
c = c.replace(c1, r1)

# 2. Update test_distinct_person_second_best
pattern = r'''        with memory_db.connect\(\) as conn:.*?conn.execute\(.*?\n.*?\)'''
repl_distinct = r'''        from tests.conftest import activate_scoped_test_calibration
        ref_hashes = ["r1", "r2", "r3"]
        activate_scoped_test_calibration(memory_db, mock_engine_config, "modelA", ref_hashes)'''

# Wait, this regex is too greedy. Let's do it manually.
