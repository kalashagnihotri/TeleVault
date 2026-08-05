import os

path = 'tests/conftest.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

c = c.replace('"\n".join(', '"\\n".join(')

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
