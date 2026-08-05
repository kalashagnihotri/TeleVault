import os

files_to_fix = [
    'tests/test_face_analysis_dry_run.py',
    'tests/test_face_analysis_diagnostics.py',
    'tests/test_detector_parity.py'
]

for path in files_to_fix:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    content = content.replace('aggregate_top_k=3', 'aggregate_top_k=1')
    content = content.replace('aggregate_top_k = 3', 'aggregate_top_k = 1')
    content = content.replace('minimum_strong_support=2', 'minimum_strong_support=1')
    content = content.replace('minimum_strong_support = 2', 'minimum_strong_support = 1')
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
