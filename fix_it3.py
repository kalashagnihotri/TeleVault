import os

path = 'tests/test_face_analysis_diagnostics.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

def replace_block(lines, method_name):
    out = []
    skip = False
    in_method = False
    for line in lines:
        if f'def {method_name}' in line:
            in_method = True
        
        if in_method and 'with memory_db.connect() as conn:' in line:
            skip = True
            out.append('        from tests.conftest import activate_scoped_test_calibration\n')
            if method_name == 'test_distinct_person_second_best':
                out.append('        ref_hashes = ["r1", "r2", "r3"]\n')
                out.append('        activate_scoped_test_calibration(memory_db, mock_engine_config, "modelA", ref_hashes)\n')
            else:
                out.append('        activate_scoped_test_calibration(memory_db, mock_engine_config, "modelA", ["r1"])\n')
            continue
            
        if skip:
            if 'mock_engine.compare_embeddings' in line:
                skip = False
                in_method = False
                out.append(line)
            continue
            
        out.append(line)
    return out

out_lines = replace_block(lines, 'test_distinct_person_second_best')
out_lines = replace_block(out_lines, 'test_missing_second_best')
out_lines = replace_block(out_lines, 'test_group_photo_resilience')

# Now apply the mock_engine_config fixture fix
content = "".join(out_lines)
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
content = content.replace(c1, r1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
