import os

path = 'tests/test_detector_parity.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

c = c.replace('config.faces.aggregate_top_k = 1', '''mock_config.faces.aggregate_method = "top_k_mean"
    mock_config.faces.aggregate_top_k = 1
    mock_config.faces.minimum_strong_support = 1
    mock_config.faces.policy_identity = "top_k_mean:k=1:strong_support=1:policy_v=1"''')

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
