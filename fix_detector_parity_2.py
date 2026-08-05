import os

path = 'tests/test_detector_parity.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

c = c.replace('config.faces.minimum_strong_support = 1\n', '')

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
