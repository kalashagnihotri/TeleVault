import os

# Fix test_face_engine.py
path2 = 'tests/test_face_engine.py'
with open(path2, 'r', encoding='utf-8') as f:
    c2 = f.read()
c2 = c2.replace('if config.faces.accept_threshold is not None and config.faces.review_threshold is not None:', 'if config.faces.aggregate_accept_threshold is not None and config.faces.aggregate_review_threshold is not None:')
with open(path2, 'w', encoding='utf-8') as f:
    f.write(c2)

# Fix test_optional_dependencies.py
path3 = 'tests/test_optional_dependencies.py'
with open(path3, 'r', encoding='utf-8') as f:
    c3 = f.read()
c3 = c3.replace('            from unittest.mock import MagicMock', '        from unittest.mock import MagicMock')
with open(path3, 'w', encoding='utf-8') as f:
    f.write(c3)

# Fix test_face_analysis_dry_run.py
path1 = 'tests/test_face_analysis_dry_run.py'
with open(path1, 'r', encoding='utf-8') as f:
    c1 = f.read()
# Let's see what is on line 115.
# Wait, I don't know what is on line 115. Let me just print it.
