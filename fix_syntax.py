import os
path = 'tests/test_face_enrollment_dry_run.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('size=128, size=128', 'size=128')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
