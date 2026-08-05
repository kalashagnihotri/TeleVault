import sys

path = 'src/face_analysis.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

import re
print(re.search(r'supporting_count\s*=\s*0', c).group(0))
