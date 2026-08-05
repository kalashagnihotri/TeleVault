import os

path1 = 'tests/test_face_analysis_dry_run.py'
with open(path1, 'r', encoding='utf-8') as f:
    c1 = f.read()
c1 = c1.replace('decision=UNKNOWN_LOW_SCORE', 'decision=UNKNOWN_AMBIGUOUS')
with open(path1, 'w', encoding='utf-8') as f:
    f.write(c1)
