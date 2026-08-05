import os

path = 'tests/test_face_analysis_diagnostics.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# I will just extract the exact parts and replace them properly.
# But since I messed it up, let's just do a git checkout to restore it first.
