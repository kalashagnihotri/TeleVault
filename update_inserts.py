import os, re

files_to_fix = [
    'tests/test_face_analysis_dry_run.py',
    'tests/test_face_analysis_diagnostics.py'
]

for path in files_to_fix:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Replace the manual sha256 with get_calibration_scope_hash
    content = content.replace('ref_set_hash = hashlib.sha256(b"refhash").hexdigest()', 
'''from src.hashing import get_calibration_scope_hash
            import hashlib
            base_ref_hash = hashlib.sha256(b"refhash").hexdigest()
            ref_set_hash = get_calibration_scope_hash("modelA", base_ref_hash, mock_engine_config.faces.policy_identity)''')

    # Update INSERT INTO face_calibrations
    content = content.replace(
        'INSERT INTO face_calibrations (model_identity, reference_set_hash, accept_threshold, review_threshold, minimum_margin, positive_pair_count, negative_pair_count, active, generated_at) VALUES (?, ?, ?, ?, ?, 0, 0, 1, ?)',
        'INSERT INTO face_calibrations (model_identity, reference_set_hash, accept_threshold, review_threshold, minimum_margin, individual_strong_support_threshold, positive_pair_count, negative_pair_count, active, generated_at) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 1, ?)'
    )
    
    # Update the parameters tuple
    content = content.replace(
        '("modelA", ref_set_hash, 0.8, 0.6, 0.1, "now")',
        '("modelA", ref_set_hash, 0.8, 0.6, 0.1, 0.75, "now")'
    )
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'Fixed {path}')
