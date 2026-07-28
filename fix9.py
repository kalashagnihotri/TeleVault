import re

with open('tests/test_face_database.py', 'r') as f:
    content = f.read()

content = content.replace(
    "'photo'",
    "'image'"
)

with open('tests/test_face_database.py', 'w') as f:
    f.write(content)
