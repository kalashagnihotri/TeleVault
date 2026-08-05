import os

path = 'tests/conftest.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

c = c.replace('return policy_hash', 'print(f"ACTIVATE: base={base_ref_hash} policy={config.faces.policy_identity} ref_set={policy_hash}"); return policy_hash')

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
