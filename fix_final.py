import os, re

# Fix test_face_analysis_dry_run.py
path1 = 'tests/test_face_analysis_dry_run.py'
with open(path1, 'r', encoding='utf-8') as f:
    c1 = f.read()
c1 = c1.replace('("modelA", "wrong_hash", 0.8, 0.6, 0.1, "now")', '("modelA", "wrong_hash", 0.8, 0.6, 0.1, 0.75, "now")')
with open(path1, 'w', encoding='utf-8') as f:
    f.write(c1)

# Fix test_face_engine.py
path2 = 'tests/test_face_engine.py'
with open(path2, 'r', encoding='utf-8') as f:
    c2 = f.read()
c2 = c2.replace('config.faces.review_threshold = 0.5', 'config.faces.aggregate_review_threshold = 0.5')
c2 = c2.replace('config.faces.minimum_margin = 0.2', 'config.faces.minimum_aggregate_margin = 0.2')
c2 = c2.replace('config.faces.accept_threshold =', 'config.faces.aggregate_accept_threshold =')
c2 = c2.replace('config.faces.review_threshold =', 'config.faces.aggregate_review_threshold =')
c2 = c2.replace('config.faces.minimum_margin =', 'config.faces.minimum_aggregate_margin =')
with open(path2, 'w', encoding='utf-8') as f:
    f.write(c2)

# Fix test_optional_dependencies.py
path3 = 'tests/test_optional_dependencies.py'
with open(path3, 'r', encoding='utf-8') as f:
    c3 = f.read()
c3 = c3.replace('from src.config import Config, AppConfig, FaceConfig, TelegramConfig, SecretsConfig, TopicsConfig', 'from src.config import Config, AppConfig, FaceConfig, TelegramConfig, SecretsConfig\n        from unittest.mock import MagicMock')
c3 = c3.replace('TopicsConfig(face_review=1)', 'MagicMock(face_review=1)')
with open(path3, 'w', encoding='utf-8') as f:
    f.write(c3)
