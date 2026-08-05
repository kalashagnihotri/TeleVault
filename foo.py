import sys
import re

path = 'tests/test_face_analysis_diagnostics.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# I will fix the indentation error
c = re.sub(r' +logger\.setLevel\(logging\.DEBUG\)', '        logger.setLevel(logging.DEBUG)', c)
c = c.replace('import sys', 'import sys')

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
