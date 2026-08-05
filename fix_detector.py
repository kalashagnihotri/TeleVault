import os
import re

path = 'tests/test_detector_parity.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# Replace the broken config block with proper mock_config assignments
b1 = '''        mock_config.faces.aggregate_method = "top_k_mean"
        mock_config.faces.aggregate_top_k = 1
        mock_config.faces.policy_identity = "top_k_mean:k=1:strong_support=1:policy_v=1"
        config.faces.policy_identity = "mock_policy"
    config.faces.minimum_face_size_px = 100'''
r1 = '''    mock_config.faces.aggregate_method = "top_k_mean"
    mock_config.faces.aggregate_top_k = 1
    mock_config.faces.minimum_strong_support = 1
    mock_config.faces.policy_identity = "top_k_mean:k=1:strong_support=1:policy_v=1"
    mock_config.faces.minimum_face_size_px = 100'''

c = c.replace(b1, r1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
