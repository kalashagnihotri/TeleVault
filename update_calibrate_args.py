import os

path = 'tests/test_face_enrollment_dry_run.py'
with open(path, 'r', encoding='utf-8') as file:
    content = file.read()

# Fix mock embedding blobs to be exactly 128-dim float32 (128 * 4 = 512 bytes)
# In python, we can just use b"0" * 512
content = content.replace('b"blob1234"', 'b"0" * 512')
content = content.replace('b"blob3456"', 'b"0" * 512')
content = content.replace('b"blob5678"', 'b"0" * 512')
content = content.replace('b"blob7890"', 'b"0" * 512')
content = content.replace('b"blob"', 'b"0" * 512')
content = content.replace('tobytes=lambda: b"emb"', 'size=128, tobytes=lambda: b"0" * 512')

# Add missing args to args = MagicMock() where cmd_calibrate is called
lines = content.split('\n')
new_lines = []
for i, line in enumerate(lines):
    if 'args = MagicMock()' in line:
        new_lines.append(line)
        # Check if cmd_calibrate is called in the next few lines
        is_calibrate = False
        for j in range(i, min(i+15, len(lines))):
            if 'cmd_calibrate(' in lines[j]:
                is_calibrate = True
                break
        if is_calibrate:
            indent = line[:line.find('args')]
            new_lines.append(f'{indent}args.negatives_dir = None')
            new_lines.append(f'{indent}args.allow_failed_holdout = False')
    else:
        new_lines.append(line)

content = '\n'.join(new_lines)

with open(path, 'w', encoding='utf-8') as out:
    out.write(content)
