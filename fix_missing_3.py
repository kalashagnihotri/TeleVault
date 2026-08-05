import os

path = 'tests/test_face_analysis_diagnostics.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

out = []
skip = False
for line in lines:
    if 'with memory_db.connect() as conn:' in line:
        # Check if we are inside test_missing_second_best or test_group_photo_resilience
        context = "".join(out[-20:])
        if 'def test_missing_second_best' in context or 'def test_group_photo_resilience' in context:
            skip = True
            out.append('        from tests.conftest import activate_scoped_test_calibration\n')
            out.append('        activate_scoped_test_calibration(memory_db, mock_engine_config, "modelA", ["r1"])\n')
        else:
            out.append(line)
    elif skip:
        if line.strip() == ')' or ')' in line and 'VALUES' not in line:
            # We reached the end of the conn.execute block
            skip = False
    else:
        out.append(line)

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(out)
